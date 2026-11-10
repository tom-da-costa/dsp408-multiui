"""Channel link groups → the request sequence that sets them (docs/PROTOCOL.md §5.3).

Verified on a DSP 408: ``2a master slave`` copies every setting of the master except the name
and the routing onto the slave; ``3b channel mask`` writes the channel's link mask (the master
holds the bits of all members, the others 0, an unlinked channel its own bit); the editor then
sends ``12``. The caller re-reads the configuration afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence

from tracks_dsp_controller.protocol import commands as cmd
from tracks_dsp_controller.protocol.config_map import link_group


class LinkError(ValueError):
    """Raised for invalid link groups."""


def normalise(groups: Sequence[Sequence[int]], count: int) -> list[tuple[int, ...]]:
    """Validate groups of channel indices (0..count-1); drop single members; sort."""
    seen: set[int] = set()
    result: list[tuple[int, ...]] = []
    for group in groups:
        members = tuple(sorted(set(group)))
        for m in members:
            if not 0 <= m < count:
                raise LinkError(f"channel index out of range: {m}")
            if m in seen:
                raise LinkError(f"channel {m} is in two groups")
            seen.add(m)
        if len(members) > 1:
            result.append(members)
    return sorted(result)


def masks_for(groups: Sequence[tuple[int, ...]], count: int) -> list[int]:
    """Link mask of every channel for these groups."""
    masks = [1 << i for i in range(count)]
    for group in groups:
        for m in group[1:]:
            masks[m] = 0
        masks[group[0]] = sum(1 << m for m in group)
    return masks


def link_requests(
    masks: Sequence[int], groups: Sequence[Sequence[int]], first_channel: int
) -> list[cmd.Request]:
    """Requests that turn the current link ``masks`` (inputs or outputs) into ``groups``.

    ``first_channel`` is the protocol channel of index 0 (0 for inputs, the input count for
    outputs). The master of a group is its lowest channel: joining a group copies the master's
    settings onto the new member. Returns an empty list when nothing changes.
    """
    count = len(masks)
    wanted = normalise(groups, count)
    target = masks_for(wanted, count)
    now = {i: link_group(masks, i) for i in range(count)}
    requests: list[cmd.Request] = []
    for group in wanted:
        master = group[0]
        for slave in group[1:]:
            if now[slave] != group or now[master] != group:
                requests.append(cmd.PrepareLink(first_channel + master, first_channel + slave))
    changed = [i for i in range(count) if target[i] != masks[i] and not _same(masks, target, i)]
    requests += [cmd.SetLink(first_channel + i, target[i]) for i in changed]
    if requests:
        requests.append(cmd.Activate())
    return requests


def _same(masks: Sequence[int], target: Sequence[int], i: int) -> bool:
    """An unlinked channel may hold 0 or its own bit: both mean "not linked"."""
    return masks[i] in (0, 1 << i) and target[i] == 1 << i and link_group(masks, i) == (i,)
