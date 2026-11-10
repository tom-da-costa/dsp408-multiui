import pytest

from tracks_dsp_controller.protocol import commands as c
from tracks_dsp_controller.protocol.links import LinkError, link_requests, masks_for, normalise
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P

OWNER_OUTPUTS = [0x11, 0x22, 0x44, 0x88, 0, 0, 0, 0]  # Out 1+5, 2+6, 3+7, 4+8


def wire(requests: list[c.Request]) -> list[str]:
    return [r.encode(P).hex(" ") for r in requests]


def test_sequences_verified_on_the_408() -> None:
    # unlink Out 4+8 (hardware: 3b 07 08, 3b 0b 80, 12)
    groups = [[0, 4], [1, 5], [2, 6]]
    assert wire(link_requests(OWNER_OUTPUTS, groups, 4)) == ["3b 07 08", "3b 0b 80", "12"]
    # link In C+D again (hardware: 2a 02 03, 3b 02 0c, 3b 03 00, 12; In D already holds 0)
    assert wire(link_requests([0x03, 0, 0x04, 0x08], [[0, 1], [2, 3]], 0)) == [
        "2a 02 03",
        "3b 02 0c",
        "3b 03 00",
        "12",
    ]


def test_nothing_to_do() -> None:
    assert link_requests([0x03, 0, 0x0C, 0], [[0, 1], [3, 2]], 0) == []
    assert link_requests([0x01, 0, 0x04, 0x08], [], 0) == []  # 0 and own bit both mean unlinked


def test_regrouping_copies_onto_the_newcomers_only() -> None:
    # Out 1 leaves Out 5 and joins Out 2+6: Out 1 becomes the master of 1+2+6, so Out 2 and
    # Out 6 take its settings; Out 5 is left alone with its own bit.
    requests = link_requests(OWNER_OUTPUTS, [[0, 1, 5], [2, 6], [3, 7]], 4)
    assert wire(requests) == [
        "2a 04 05",
        "2a 04 09",
        "3b 04 23",
        "3b 05 00",
        "3b 08 10",
        "12",
    ]


def test_masks_and_validation() -> None:
    assert masks_for(normalise([[1, 0], [3]], 4), 4) == [0b11, 0, 0b100, 0b1000]
    with pytest.raises(LinkError, match="two groups"):
        normalise([[0, 1], [1, 2]], 4)
    with pytest.raises(LinkError, match="out of range"):
        normalise([[0, 4]], 4)


def test_requests_validate() -> None:
    assert c.PrepareLink(4, 8).encode(P) == bytes.fromhex("2a 04 08")
    with pytest.raises(c.CommandError, match="itself"):
        c.PrepareLink(4, 4).encode(P)
    with pytest.raises(c.CommandError, match="input and an output"):
        c.PrepareLink(0, 4).encode(P)
    with pytest.raises(c.CommandError, match="mask"):
        c.SetLink(0, 0x10).encode(P)  # inputs have 4 bits
    assert c.SetLink(11, 0x80).encode(P) == bytes.fromhex("3b 0b 80")
    assert c.decode_request(bytes.fromhex("3b 0b 80"), P) == c.SetLink(11, 0x80)
