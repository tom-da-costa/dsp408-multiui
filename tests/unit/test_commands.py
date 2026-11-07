import pytest

from dsp408_multiui.protocol import commands as cmd
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P

H = bytes.fromhex

# Every request with its exact payload (opcode first).
VECTORS: list[tuple[cmd.Request, str]] = [
    (cmd.Handshake(), "10"),
    (cmd.GetDeviceInfo(), "13"),
    (cmd.GetStatus(), "2c"),
    (cmd.GetPresetHeader(), "22"),
    (cmd.GetActivePreset(), "14"),
    (cmd.Activate(), "12"),
    (cmd.PollMeters(), "40"),
    (cmd.GetPresetName(19), "29 13"),
    (cmd.RecallPreset(1), "20 01"),
    (cmd.RecallPreset(0), "20 00"),
    (cmd.SetPresetName("Forest"), "26" + b"Forest        ".hex()),
    (cmd.StorePreset(20), "21 14"),
    (cmd.ReadConfigPage(28), "27 1c"),
    (cmd.SetGain(0, 248), "34 00 f8 00"),  # In A -3.2 dB
    (cmd.SetGain(4, 280), "34 04 18 01"),
    (cmd.SetMute(8, True), "35 08 01"),
    (cmd.SetPhase(11, False), "36 0b 00"),
    (cmd.SetPeqBypass(5, True), "3c 05 01"),
    (cmd.SetMatrix(4, 0x03), "3a 04 03"),  # dsp-408-ui: Out 1 <- In A + In B
    (cmd.SetGeqBand(0, 30, 240), "48 00 1e f0 00"),
    (cmd.SetPeqBand(4, 0, 120, 31, 35, 0, False), "33 04 00 78 00 1f 00 23 00 00"),
    (cmd.SetPeqBand(6, 8, 150, 300, 100, 8, True), "33 06 08 96 00 2c 01 64 08 01"),
    (cmd.SetHighPass(4, 11, 8), "32 04 0b 00 08"),
    (cmd.SetLowPass(4, 61, 8), "31 04 3d 00 08"),
    (cmd.SetDelay(4, 96), "38 04 60 00"),
    (cmd.SetCompressor(4, 15, 49, 499, 3, 220), "30 04 0f 00 31 00 f3 01 03 00 dc 00"),
    (cmd.SetLimiter(4, 49, 499, 0, 220), "3f 04 31 00 f3 01 00 00 dc 00"),
    (cmd.SetGate(2, 0, 99, 99, 0), "3e 02 00 00 63 00 63 00 00 00"),
    (cmd.SetChannelName(6, "AUSGANG3"), "3d 06 41 55 53 47 41 4e 47 33"),
    (cmd.SubmitPin("7654"), "2d 00 37 36 35 34"),
]


@pytest.mark.parametrize(("request_", "payload"), VECTORS)
def test_encode(request_: cmd.Request, payload: str) -> None:
    assert request_.encode(P) == H(payload)


@pytest.mark.parametrize(("request_", "payload"), VECTORS)
def test_decode_roundtrip(request_: cmd.Request, payload: str) -> None:
    assert cmd.decode_request(H(payload), P) == request_


def test_compressor_narrow_layout() -> None:
    from dsp408_multiui.protocol.profile import CompressorLayout

    narrow = P.with_overrides({"codecs": {"compressor_layout": CompressorLayout.NARROW.value}})
    request = cmd.SetCompressor(4, 15, 49, 499, 3, 220)
    payload = request.encode(narrow)
    assert payload == H("30 04 0f 03 31 00 f3 01 dc 00")
    assert cmd.decode_request(payload, narrow) == request


@pytest.mark.parametrize(
    "request_",
    [
        cmd.StorePreset(0),  # F00 is read-only
        cmd.StorePreset(21),
        cmd.RecallPreset(21),
        cmd.GetPresetName(20),
        cmd.ReadConfigPage(29),
        cmd.SetGain(12, 280),
        cmd.SetGain(0, 401),
        cmd.SetMatrix(0, 1),  # matrix needs an output
        cmd.SetMatrix(4, 0x10),
        cmd.SetGeqBand(4, 0, 120),  # GEQ needs an input
        cmd.SetGeqBand(0, 31, 120),
        cmd.SetPeqBand(0, 8, 120, 0, 0, 0, False),  # inputs have 8 bands
        cmd.SetPeqBand(4, 0, 120, 301, 0, 0, False),
        cmd.SetPeqBand(4, 0, 120, 0, 0, 9, False),
        cmd.SetHighPass(4, 0, 21),
        cmd.SetDelay(4, 65281),
        cmd.SetCompressor(0, 0, 0, 0, 0, 0),  # outputs only
        cmd.SetCompressor(4, 16, 0, 0, 0, 0),
        cmd.SetLimiter(4, 0, 0, 0, 221),
        cmd.SetGate(4, 0, 0, 0, 0),  # inputs only
        cmd.SetPresetName("fifteen chars!!"),
        cmd.SetChannelName(0, "too long!"),
        cmd.SubmitPin("12a4"),
    ],
)
def test_invalid_requests_are_refused(request_: cmd.Request) -> None:
    with pytest.raises(cmd.CommandError):
        request_.encode(P)


@pytest.mark.parametrize(
    "payload",
    ["", "ff", "21 00", "34 00 18", "35 00 02", "26 41", "3d 00 41", "2d 00 31", "10 00"],
)
def test_malformed_payloads_are_refused(payload: str) -> None:
    with pytest.raises(cmd.CommandError):
        cmd.decode_request(H(payload), P)


def test_no_builder_for_dangerous_opcodes() -> None:
    with pytest.raises(cmd.CommandError, match="unknown"):
        cmd.decode_request(H("39 03 11"), P)  # test tone
    with pytest.raises(cmd.CommandError, match="unknown"):
        cmd.decode_request(H("2f 31 32 33 34"), P)  # set device PIN


def test_coalesce_keys() -> None:
    assert cmd.SetGain(4, 1).coalesce_key == cmd.SetGain(4, 2).coalesce_key
    assert cmd.SetGain(4, 1).coalesce_key != cmd.SetGain(5, 1).coalesce_key
    assert cmd.SetGain(4, 1).coalesce_key != cmd.SetMute(4, True).coalesce_key
    band = cmd.SetPeqBand(4, 1, 120, 0, 0, 0, False)
    assert band.coalesce_key == (0x33, 4, 1)
    assert cmd.PollMeters().coalesce_key is None
    assert cmd.RecallPreset(1).SLOW
    assert not cmd.SetGain(0, 0).SLOW
