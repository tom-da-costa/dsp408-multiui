"""Simulated DSP 408 state machine (no I/O).

``SimulatedDevice.handle`` takes one request payload and returns what the device answers, how
long it takes, and whether it "crashes" (closes the connection). The TCP server in
``simulator.server`` wraps it.

Behaviour follows docs/PROTOCOL.md. Where the real device's behaviour is unknown (for example
how it reacts to an invalid request), the simulator does the conservative thing: no answer,
which the host sees as a timeout.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol import config_map as cm
from dsp408_multiui.protocol import responses as rsp
from dsp408_multiui.protocol.codecs import PRESET_NAME_LENGTH
from dsp408_multiui.protocol.profile import ProtocolProfile
from dsp408_multiui.simulator.meters import MeterSimulator

log = logging.getLogger(__name__)

DEFAULT_IDENTITY = "DSP408 V0104P"  # 408: identity string of firmware V0104P
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


@dataclass
class SimulatedDevice:
    profile: ProtocolProfile
    identity: str = DEFAULT_IDENTITY
    timing: Timing = field(default_factory=Timing)
    clock: Callable[[], float] | None = None  # for meters; defaults to time.monotonic

    presets: list[cm.RawConfig] = field(init=False)
    live: cm.RawConfig = field(init=False)
    active_slot: int = field(init=False, default=0)
    pending_name: str = field(init=False, default=EMPTY_PRESET_NAME)
    # The 408 serves config pages and meters only after the init sequence on the connection
    # (which request of it unlocks them is not known; the simulator uses the handshake).
    # True by default so that direct ``handle()`` calls work; the TCP server resets it.
    session_ready: bool = field(init=False, default=True)
    meters: MeterSimulator = field(init=False)
    requests_handled: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        cm.check_layout(self.profile)
        factory = cm.default_config(EMPTY_PRESET_NAME)
        self.presets = [factory] * (self.profile.preset_count + 1)
        self.live = factory
        self.meters = MeterSimulator(self.profile, clock=self.clock)

    # --- public API used by scenarios and tests -----------------------------------------------
    def set_preset(self, slot: int, config: cm.RawConfig) -> None:
        if not 0 <= slot <= self.profile.preset_count:
            raise ValueError(f"slot out of range: {slot}")
        self.presets[slot] = config

    def load(self, slot: int) -> None:
        self.live = self.presets[slot]
        self.active_slot = slot

    def on_connect(self) -> None:
        """A new TCP connection: config pages and meters wait for the init sequence again."""
        self.session_ready = False

    @property
    def config_blob(self) -> bytes:
        return cm.encode_config(self.live)

    # --- request handling -----------------------------------------------------------------------
    def handle(self, payload: bytes) -> Reply:
        self.requests_handled += 1
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
        return self._dispatch(request)

    def _ack(self, delay: float | None = None) -> Reply:
        return Reply(rsp.Ack(), self.timing.default_s if delay is None else delay)

    def _reply(self, response: rsp.Response) -> Reply:
        return Reply(response, self.timing.default_s)

    def _dispatch(self, r: cmd.Request) -> Reply:
        match r:
            case cmd.Handshake():
                self.session_ready = True
                return self._reply(rsp.HandshakeReply(bytes((self.profile.preset_count,))))
            case cmd.GetDeviceInfo():
                return self._reply(rsp.DeviceInfo(self.identity))
            case cmd.GetStatus():
                return self._reply(rsp.Status(bytes.fromhex("00 27 0f 00 00 00")))
            case cmd.GetPresetHeader():
                return self._reply(rsp.PresetHeader(b"\xff\xff" + bytes(28)))
            case cmd.GetActivePreset():
                return self._reply(rsp.ActivePreset(self.active_slot))
            case cmd.GetPresetName(index=index):
                return self._reply(rsp.PresetName(index, self.presets[index + 1].preset_name))
            case cmd.Activate():
                return self._ack()
            case cmd.PollMeters() | cmd.ReadConfigPage() if not self.session_ready:
                return Reply(None)  # the 408 stays silent before the init sequence
            case cmd.PollMeters():
                return self._reply(rsp.MeterFrame(self.meters.render(self.live)))
            case cmd.ReadConfigPage(page=page):
                pages = cm.split_pages(self.config_blob, self.profile)
                return self._reply(rsp.ConfigPage(page, pages[page]))
            case cmd.RecallPreset(slot=slot):
                self.load(slot)
                return self._ack(self.timing.recall_s)
            case cmd.SetPresetName(name=name):
                self.pending_name = name
                # 408: the ACK echoes the name
                echo = b"\x01" + name.encode("ascii").ljust(PRESET_NAME_LENGTH, b" ")
                return Reply(rsp.Ack(echo), self.timing.default_s)
            case cmd.StorePreset(slot=slot):
                stored = replace(
                    self.live, marker=cm.MARKER_MODIFIED, preset_name=self.pending_name
                )
                stored = replace(stored, image=cm.encode_config(stored))
                self.presets[slot] = stored
                self.live = stored
                self.active_slot = slot
                return self._ack(self.timing.store_s)
            case cmd.SubmitPin():
                return self._reply(rsp.PinResult(True))  # the simulated device is never locked
            case _:
                self._apply(r)
                return self._ack()

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
