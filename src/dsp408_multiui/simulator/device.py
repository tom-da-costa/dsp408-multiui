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

DEFAULT_IDENTITY = "DSP408 V1.04"  # HYP: the real 0x13 string of a DSP 408 is not documented
EMPTY_PRESET_NAME = "Default Preset"


@dataclass(frozen=True, slots=True)
class Reply:
    response: rsp.Response | None  # None: the device stays silent
    delay_s: float = 0.0
    crash: bool = False  # the device drops the connection (firmware crash)


@dataclass(slots=True)
class Timing:
    """Response delays. Recall/store are slow on the real device (~1-2 s)."""

    default_s: float = 0.002
    recall_s: float = 1.2
    store_s: float = 1.8


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
    # Not stored in the config blob (location unknown): kept here, per live state only.
    peq_band_bypass: dict[tuple[int, int], bool] = field(init=False, default_factory=dict)
    peq_channel_bypass: dict[int, bool] = field(init=False, default_factory=dict)
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
        self.peq_band_bypass.clear()
        self.peq_channel_bypass.clear()

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
                return self._reply(rsp.HandshakeReply(bytes((self.profile.preset_count,))))
            case cmd.GetDeviceInfo():
                return self._reply(rsp.DeviceInfo(self.identity))
            case cmd.GetStatus():
                return self._reply(rsp.Status(bytes.fromhex("00 27 0f 00 00 00 00")))
            case cmd.GetPresetHeader():
                return self._reply(rsp.PresetHeader(b"\xff\xff" + bytes(28)))
            case cmd.GetActivePreset():
                return self._reply(rsp.ActivePreset(self.active_slot))
            case cmd.GetPresetName(index=index):
                return self._reply(rsp.PresetName(index, self.presets[index + 1].preset_name))
            case cmd.Activate():
                return self._ack()
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
                return self._ack()
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
        """Apply a parameter write to the live config."""
        match r:
            case cmd.SetGain(channel=ch, raw=raw):
                self._update(ch, gain=raw)
            case cmd.SetMute(channel=ch, on=on):
                self._update(ch, mute=on)
            case cmd.SetPhase(channel=ch, on=on):
                self._update(ch, phase=on)
            case cmd.SetDelay(channel=ch, raw=raw):
                self._update(ch, delay=raw)
            case cmd.SetChannelName(channel=ch, name=name):
                self._update(ch, name=name)
            case cmd.SetMatrix(channel=ch, mask=mask):
                self._update(ch, matrix=mask)
            case cmd.SetHighPass(channel=ch, freq=freq, slope=slope):
                x = self._channel(ch).crossover
                self._update(ch, crossover=replace(x, hpf_freq=freq, hpf_slope=slope))
            case cmd.SetLowPass(channel=ch, freq=freq, slope=slope):
                x = self._channel(ch).crossover
                self._update(ch, crossover=replace(x, lpf_freq=freq, lpf_slope=slope))
            case cmd.SetPeqBand() as b:
                bands = list(self._channel(b.channel).peq)
                bands[b.band] = cm.RawPeqBand(b.gain, b.freq, b.q, b.type)
                self._update(b.channel, peq=tuple(bands))
                self.peq_band_bypass[(b.channel, b.band)] = b.bypass
            case cmd.SetPeqBypass(channel=ch, on=on):
                self.peq_channel_bypass[ch] = on
            case cmd.SetGeqBand(channel=ch, band=band, raw=raw):
                geq = list(self.live.inputs[ch].geq)
                geq[band] = raw
                self._update(ch, geq=tuple(geq))
            case cmd.SetCompressor() as c:
                comp = cm.RawCompressor(c.ratio, c.attack, c.release, c.knee, c.threshold)
                self._update(c.channel, compressor=comp)
            case cmd.SetLimiter() as lim:
                limiter = cm.RawLimiter(lim.attack, lim.release, lim.reserved, lim.threshold)
                self._update(lim.channel, limiter=limiter)
            case cmd.SetGate() as g:
                self._update(g.channel, gate=cm.RawGate(g.attack, g.release, g.hold, g.threshold))
            case _:  # pragma: no cover - every request type is handled above
                raise AssertionError(f"unhandled request {r!r}")

    def _channel(self, ch: int) -> cm.RawInput | cm.RawOutput:
        if self.profile.is_input(ch):
            return self.live.inputs[ch]
        return self.live.outputs[ch - self.profile.input_count]

    def _update(self, ch: int, **changes: object) -> None:
        """Replace fields of one channel and mark the live config as modified."""
        if self.profile.is_input(ch):
            inputs = list(self.live.inputs)
            inputs[ch] = replace(inputs[ch], **changes)  # type: ignore[arg-type]
            live = replace(self.live, inputs=tuple(inputs))
        else:
            outputs = list(self.live.outputs)
            idx = ch - self.profile.input_count
            outputs[idx] = replace(outputs[idx], **changes)  # type: ignore[arg-type]
            live = replace(self.live, outputs=tuple(outputs))
        self.live = replace(live, marker=cm.MARKER_MODIFIED)
