"""Simulated DSP state machine (no I/O): a DSP 408, 206 or 204 (``simulator.models``).

``SimulatedDevice.handle`` takes one request payload and returns what the device answers, how
long it takes, and whether it "crashes" (closes the connection). The TCP server in
``simulator.server`` wraps it.

Behaviour follows docs/PROTOCOL.md. Where the real device's behaviour is unknown (for example
how it reacts to an invalid request), the simulator does the conservative thing: no answer,
which the host sees as a timeout.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol import responses as rsp
from tracks_dsp_controller.protocol.codecs import PRESET_NAME_LENGTH, encode_stored_name
from tracks_dsp_controller.protocol.profile import ProtocolProfile
from tracks_dsp_controller.simulator.meters import MeterSimulator
from tracks_dsp_controller.simulator.models import DEFAULT_MODEL, SIM_MODELS, SimModel

log = logging.getLogger(__name__)

DEFAULT_IDENTITY = SIM_MODELS[DEFAULT_MODEL].identity  # "DSP408 V0104P"
EMPTY_PRESET_NAME = "Default Preset"


@dataclass(frozen=True, slots=True)
class Reply:
    response: rsp.Response | None  # None: the device stays silent
    delay_s: float = 0.0
    crash: bool = False  # the device drops the connection (firmware crash)


@dataclass(slots=True)
class Timing:
    """Response delays, as measured on a DSP 408 (recall ~3.2 s, store ~7.4 s)."""

    default_s: float = 0.002
    recall_s: float = 3.2
    store_s: float = 7.4
    # A connection left without any request for this long stops answering reads until the next
    # handshake; writes still work (HW: between 5 and 7 s on a DSP 408, PROTOCOL.md §1).
    idle_expiry_s: float = 6.0


@dataclass(slots=True)
class Link:
    """One host connection. The 408 serves config pages and meters on a connection only after
    the init sequence was sent on it (which request of it unlocks them is not known; the
    simulator uses the handshake). Several connections each have their own state."""

    ready: bool = False
    expired: bool = False  # idle too long: reads unanswered until the next handshake
    last_request: float | None = None


@dataclass
class SimulatedDevice:
    profile: ProtocolProfile
    model: SimModel = SIM_MODELS[DEFAULT_MODEL]
    identity: str = ""  # 0x13 reply; empty = the model's
    timing: Timing = field(default_factory=Timing)
    clock: Callable[[], float] | None = None  # for meters; defaults to time.monotonic
    # Called after a preset recall or store (the standalone simulator persists presets with it).
    on_preset_change: Callable[[], None] | None = None

    presets: list[cm.RawConfig] = field(init=False)
    live: cm.RawConfig = field(init=False)
    active_slot: int = field(init=False, default=0)
    pending_name: str = field(init=False, default=EMPTY_PRESET_NAME)
    # Used by ``handle()`` calls without a link (tests, demo scenarios): already initialised.
    default_link: Link = field(init=False, default_factory=lambda: Link(ready=True))
    meters: MeterSimulator = field(init=False)
    requests_handled: int = field(init=False, default=0)

    layout: cm.ConfigLayout = field(init=False)

    def __post_init__(self) -> None:
        self.layout = cm.check_layout(self.profile)
        self.identity = self.identity or self.model.identity
        factory = cm.default_config(EMPTY_PRESET_NAME, self.layout)
        self.presets = [factory] * (self.profile.preset_count + 1)
        self.live = factory
        self.meters = MeterSimulator(self.profile, clock=self.clock)

    # --- public API used by scenarios and tests -----------------------------------------------
    def set_preset(self, slot: int, config: cm.RawConfig) -> None:
        if not 0 <= slot <= self.profile.preset_count:
            raise ValueError(f"slot out of range: {slot}")
        if cm.config_layout(config) != self.layout:
            raise ValueError(
                f"a {len(config.inputs)}x{len(config.outputs)} config does not fit a "
                f"{self.layout.inputs}x{self.layout.outputs} device"
            )
        self.presets[slot] = config

    def load(self, slot: int) -> None:
        self.live = self.presets[slot]
        self.active_slot = slot

    def recall(self, slot: int) -> None:
        """Recall a preset (over the network, or from the front panel)."""
        self.load(slot)
        self._preset_changed()

    @property
    def config_blob(self) -> bytes:
        return cm.encode_config(self.live)

    # --- request handling -----------------------------------------------------------------------
    def handle(self, payload: bytes, link: Link | None = None) -> Reply:
        """Answer one request received on ``link`` (a TCP connection)."""
        self.requests_handled += 1
        if link is not None:
            now = (self.clock or time.monotonic)()
            if (
                link.last_request is not None
                and now - link.last_request > self.timing.idle_expiry_s
            ):
                link.expired = True
            link.last_request = now
        if (
            payload[:1] == bytes((cmd.Opcode.SET_PRESET_NAME,))
            and len(payload) - 1 > PRESET_NAME_LENGTH
        ):
            log.warning("preset name longer than 14 bytes: simulating a firmware crash")
            return Reply(None, crash=True)
        try:
            request = cmd.decode_request(payload, self.profile)
        except cmd.CommandError as exc:
            log.warning("ignoring invalid request %s: %s", payload.hex(" "), exc)
            return Reply(None, self.timing.default_s)
        return self._dispatch(request, link or self.default_link)

    def _ack(self, delay: float | None = None) -> Reply:
        return Reply(rsp.Ack(), self.timing.default_s if delay is None else delay)

    def _reply(self, response: rsp.Response) -> Reply:
        return Reply(response, self.timing.default_s)

    def _dispatch(self, r: cmd.Request, link: Link) -> Reply:
        if link.expired and isinstance(r, _READS):
            return Reply(None)  # the 408 stays silent until the next handshake
        match r:
            case cmd.Handshake():
                link.ready = True
                link.expired = False
                return self._reply(rsp.HandshakeReply(self.model.handshake))
            case cmd.GetDeviceInfo():
                return self._reply(rsp.DeviceInfo(self.identity))
            case cmd.GetStatus():
                return self._reply(rsp.Status(self.model.status))
            case cmd.GetPresetHeader():
                return self._reply(rsp.PresetHeader(self.model.preset_header))
            case cmd.GetActivePreset():
                return self._reply(rsp.ActivePreset(self.active_slot))
            case cmd.GetPresetName(index=index):
                return self._reply(rsp.PresetName(index, self.presets[index + 1].preset_name))
            case cmd.Activate():
                return self._ack()
            case cmd.PollMeters() | cmd.ReadConfigPage() if not link.ready:
                return Reply(None)  # the 408 stays silent before the init sequence
            case cmd.PollMeters():
                return self._reply(rsp.MeterFrame(self.meters.render(self.live)))
            case cmd.ReadConfigPage(page=page):
                pages = cm.split_pages(self.config_blob, self.profile)
                return self._reply(rsp.ConfigPage(page, pages[page]))
            case cmd.RecallPreset(slot=slot):
                self.recall(slot)
                return self._ack(self.timing.recall_s)
            case cmd.SetPresetName(name=name):
                self.pending_name = name
                # 408 / 206: the ACK echoes the name
                echo = self.model.name_ack + encode_stored_name(name, PRESET_NAME_LENGTH, b" ")
                return Reply(rsp.Ack(echo), self.timing.default_s)
            case cmd.StorePreset(slot=slot):
                stored = replace(
                    self.live, marker=cm.MARKER_MODIFIED, preset_name=self.pending_name
                )
                stored = replace(stored, image=cm.encode_config(stored))
                self.presets[slot] = stored
                self.live = stored
                self.active_slot = slot
                self._preset_changed()
                return self._ack(self.timing.store_s)
            case cmd.SubmitPin():
                return self._reply(rsp.PinResult(True))  # the simulated device is never locked
            case _:
                self._apply(r)
                return self._ack()

    def _preset_changed(self) -> None:
        if self.on_preset_change is not None:
            self.on_preset_change()

    def _apply(self, r: cmd.Request) -> None:
        """Apply a parameter write to the live config (and to linked channels, like the 408)."""
        match r:
            case cmd.SetGain(channel=ch, raw=raw):
                self._update(ch, lambda c: {"gain": raw})
            case cmd.SetMute(channel=ch, on=on):
                self._update(ch, lambda c: {"mute": on})
            case cmd.SetPhase(channel=ch, on=on):
                self._update(ch, lambda c: {"phase": on})
            case cmd.SetDelay(channel=ch, raw=raw):
                self._update(ch, lambda c: {"delay": raw})
            case cmd.SetChannelName(channel=ch, name=name):
                self._update(ch, lambda c: {"name": name}, linked=False)
            case cmd.SetMatrix(channel=ch, mask=mask):
                self._update(ch, lambda c: {"matrix": mask}, linked=False)
            case cmd.SetHighPass(channel=ch, freq=freq, slope=slope):
                self._update(
                    ch,
                    lambda c: {"crossover": replace(c.crossover, hpf_freq=freq, hpf_slope=slope)},
                )
            case cmd.SetLowPass(channel=ch, freq=freq, slope=slope):
                self._update(
                    ch,
                    lambda c: {"crossover": replace(c.crossover, lpf_freq=freq, lpf_slope=slope)},
                )
            case cmd.SetPeqBand() as b:
                band = cm.RawPeqBand(b.gain, b.freq, b.q, b.type, b.bypass)
                self._update(
                    b.channel,
                    lambda c: {"peq": (*c.peq[: b.band], band, *c.peq[b.band + 1 :])},
                )
            case cmd.SetPeqBypass(channel=ch, on=on):
                self._update(ch, lambda c: {"peq_bypass": on})
            case cmd.PrepareLink(master=master, slave=slave):
                self._copy_settings(master, slave)
            case cmd.SetLink(channel=ch, mask=mask):
                self._update(ch, lambda c: {"link": mask}, linked=False)
            case cmd.SetGeqBand(channel=ch, band=n, raw=raw):
                self._update(ch, lambda c: {"geq": (*c.geq[:n], raw, *c.geq[n + 1 :])})  # type: ignore[union-attr]
            case cmd.SetCompressor() as k:
                comp = cm.RawCompressor(k.ratio, k.attack, k.release, k.knee, k.threshold)
                self._update(k.channel, lambda c: {"compressor": comp})
            case cmd.SetLimiter() as lim:
                limiter = cm.RawLimiter(lim.attack, lim.release, lim.reserved, lim.threshold)
                self._update(lim.channel, lambda c: {"limiter": limiter})
            case cmd.SetGate() as g:
                gate = cm.RawGate(g.attack, g.release, g.hold, g.threshold)
                self._update(g.channel, lambda c: {"gate": gate})
            case _:  # pragma: no cover - every request type is handled above
                raise AssertionError(f"unhandled request {r!r}")

    # Settings that 2a (PrepareLink) does not copy: identity and routing (HW, 408).
    _NOT_COPIED = ("name", "link", "matrix", "crosspoints")

    def _copy_settings(self, master: int, slave: int) -> None:
        """2a: the slave takes every setting of the master except its name and routing."""
        is_input = self.profile.is_input(master)
        group = self.live.inputs if is_input else self.live.outputs
        base = 0 if is_input else self.profile.input_count
        source, target = group[master - base], group[slave - base]
        keep = {k: getattr(target, k) for k in self._NOT_COPIED if hasattr(target, k)}
        self._update(slave, lambda c: {**_fields(source), **keep}, linked=False)

    def _update(
        self,
        ch: int,
        changes: Callable[[cm.RawInput | cm.RawOutput], dict[str, object]],
        *,
        linked: bool = True,
    ) -> None:
        """Change one channel (and its linked group) and mark the live config as modified."""
        inputs, outputs = list(self.live.inputs), list(self.live.outputs)
        is_input = self.profile.is_input(ch)
        group: list[cm.RawInput] | list[cm.RawOutput] = inputs if is_input else outputs
        index = ch if is_input else ch - self.profile.input_count
        members = cm.link_group([c.link for c in group], index) if linked else (index,)
        for m in members:
            group[m] = replace(group[m], **changes(group[m]))  # type: ignore[arg-type,assignment]
        live = replace(self.live, inputs=tuple(inputs), outputs=tuple(outputs))
        self.live = replace(live, marker=cm.MARKER_MODIFIED)


def _fields(channel: cm.RawInput | cm.RawOutput) -> dict[str, object]:
    return {name: getattr(channel, name) for name in channel.__slots__}


# Requests answered with data (not an ACK): unanswered on a connection left idle too long.
_READS = (
    cmd.GetDeviceInfo,
    cmd.GetStatus,
    cmd.GetPresetHeader,
    cmd.GetActivePreset,
    cmd.GetPresetName,
    cmd.PollMeters,
    cmd.ReadConfigPage,
)
