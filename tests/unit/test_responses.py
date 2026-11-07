import pytest

from dsp408_multiui.protocol import responses as r

H = bytes.fromhex

VECTORS: list[tuple[r.Response, str]] = [
    (r.Ack(), "01"),
    (r.HandshakeReply(H("1e")), "10 1e"),
    (r.Status(H("00 27 0f 00 00 00 00")), "2c 00 27 0f 00 00 00 00"),
    (r.PresetHeader(H("ff ff") + bytes(28)), "22 ff ff" + "00" * 28),
    (r.DeviceInfo("DSP408 V1.04"), "13" + b"DSP408 V1.04".hex()),
    (r.ActivePreset(2), "14 02"),
    (r.PresetName(1, "DIY Mon offset"), "29 01" + b"DIY Mon offset".hex()),
    (r.ConfigPage(3, bytes(range(50))), "24 03" + bytes(range(50)).hex()),
    (r.PinResult(True), "2d 00 01"),
    (r.PinResult(False), "2d 00 00"),
    (r.MeterFrame(bytes(38)), "40" + "00" * 38),
]


@pytest.mark.parametrize(("response", "payload"), VECTORS)
def test_roundtrip(response: r.Response, payload: str) -> None:
    assert response.encode() == H(payload)
    assert r.decode_response(H(payload)) == response


def test_device_info_fields() -> None:
    info = r.decode_response(b"\x13" + b"4x4MINI V010\x00")
    assert isinstance(info, r.DeviceInfo)
    assert (info.model, info.firmware) == ("4x4MINI", "V010")
    assert (r.DeviceInfo("").model, r.DeviceInfo("X").firmware) == ("", "")


def test_preset_name_is_space_trimmed() -> None:
    reply = r.decode_response(H("29 00") + b"DIY Mon       ")
    assert reply == r.PresetName(0, "DIY Mon")


def test_unknown_opcode_is_kept() -> None:
    reply = r.decode_response(H("77 01 02"))
    assert reply == r.Unknown(0x77, H("01 02"))
    assert reply.encode() == H("77 01 02")


@pytest.mark.parametrize("payload", ["", "01 00", "14", "14 01 02", "2d 01", "29", "24"])
def test_malformed(payload: str) -> None:
    with pytest.raises(r.ResponseError):
        r.decode_response(H(payload))
