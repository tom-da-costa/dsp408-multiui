"""Command pipeline against a scripted fake connection."""

import asyncio

import pytest

from dsp408_multiui.device.pipeline import (
    CommandPipeline,
    CommandTimeoutError,
    PipelineClosedError,
)
from dsp408_multiui.device.transport import TransportError, TransportTimeoutError
from dsp408_multiui.protocol import commands as c
from dsp408_multiui.protocol import responses as r
from dsp408_multiui.protocol.profile import DEFAULT_PROFILE as P


class FakeConn:
    profile = P

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.sent: list[c.Request] = []
        self.timeouts_left = 0
        self.fail_with: Exception | None = None

    async def request(self, request: c.Request, timeout: float | None = None) -> r.Response:
        self.sent.append(request)
        await asyncio.sleep(self.delay)
        if self.fail_with is not None:
            raise self.fail_with
        if self.timeouts_left:
            self.timeouts_left -= 1
            raise TransportTimeoutError("timeout")
        if isinstance(request, c.PollMeters):
            return r.MeterFrame(bytes(38))
        return r.Ack()


def writes(conn: FakeConn) -> list[c.Request]:
    return [q for q in conn.sent if not isinstance(q, c.PollMeters)]


async def test_coalescing_keeps_only_the_latest_value() -> None:
    conn = FakeConn(delay=0.01)
    acks: list[int] = []
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=lambda d: None)
    pipe.start()
    await asyncio.sleep(0.005)  # first poll in flight
    tasks = [
        asyncio.create_task(pipe.submit(c.SetGain(4, v), on_ack=lambda v=v: acks.append(v)))
        for v in range(200)
    ]
    other = asyncio.create_task(pipe.submit(c.SetMute(4, True)))
    results = await asyncio.gather(*tasks, other)
    assert all(isinstance(res, r.Ack) for res in results)
    sent = writes(conn)
    assert sent == [c.SetGain(4, 199), c.SetMute(4, True)] or len(sent) <= 3
    assert sent[-2:] in (
        [c.SetGain(4, 199), c.SetMute(4, True)],
        [c.SetMute(4, True), c.SetGain(4, 199)],
    )
    assert acks[-1] == 199
    assert pipe.stats.coalesced >= 198
    await pipe.stop()


async def test_meter_rate_holds_under_write_load() -> None:
    conn = FakeConn(delay=0.005)
    frames: list[bytes | None] = []
    pipe = CommandPipeline(conn, meter_interval=0.05, on_meters=frames.append)
    pipe.start()

    async def hammer() -> None:
        for i in range(60):
            await pipe.submit(c.SetGain(i % 12, i))

    await asyncio.gather(hammer(), hammer())
    await pipe.stop()
    # ~0.6 s of saturated writes: polls must still have run at about 20 Hz
    assert len(frames) >= 6
    assert all(f is not None for f in frames)


async def test_timeout_is_retried_then_reported() -> None:
    conn = FakeConn()
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=lambda d: None, max_failures=5)
    pipe.start()
    await asyncio.sleep(0.01)
    conn.timeouts_left = 1
    assert await pipe.submit(c.SetMute(0, True)) == r.Ack()  # retried once
    conn.timeouts_left = 2
    with pytest.raises(CommandTimeoutError):
        await pipe.submit(c.SetMute(0, False))
    assert pipe.stats.timeouts == 3
    assert not pipe.closed
    await pipe.stop()


async def test_consecutive_failures_close_the_pipeline() -> None:
    conn = FakeConn()
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=lambda d: None, max_failures=2)
    pipe.start()
    await asyncio.sleep(0.01)
    conn.timeouts_left = 100
    with pytest.raises(CommandTimeoutError):
        await pipe.submit(c.SetMute(0, True))
    with pytest.raises(PipelineClosedError):
        await pipe.submit(c.SetMute(1, True))
    reason = await asyncio.wait_for(pipe.wait_closed(), 1)
    assert "consecutive" in str(reason)
    with pytest.raises(PipelineClosedError):
        await pipe.submit(c.SetMute(2, True))


async def test_transport_error_fails_everything() -> None:
    conn = FakeConn(delay=0.02)
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=lambda d: None)
    pipe.start()
    await asyncio.sleep(0.005)
    conn.fail_with = TransportError("cable pulled")
    tasks = [asyncio.create_task(pipe.submit(c.SetGain(i, 0))) for i in range(3)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(res, PipelineClosedError) for res in results)
    assert isinstance(await pipe.wait_closed(), TransportError)


async def test_exclusive_pauses_the_worker() -> None:
    conn = FakeConn()
    pipe = CommandPipeline(conn, meter_interval=0.01, on_meters=lambda d: None)
    pipe.start()
    await asyncio.sleep(0.03)
    async with pipe.exclusive() as direct:
        before = len(conn.sent)
        await asyncio.sleep(0.05)
        assert len(conn.sent) == before  # no polls while exclusive
        await direct.request(c.Handshake())
    await asyncio.sleep(0.03)
    assert len(conn.sent) > before + 1
    await pipe.stop()
    with pytest.raises(PipelineClosedError):
        async with pipe.exclusive():
            pass


async def test_poll_timeout_reports_none() -> None:
    conn = FakeConn()
    frames: list[bytes | None] = []
    conn.timeouts_left = 2
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=frames.append)
    pipe.start()
    await asyncio.sleep(0.02)
    assert frames == [None]
    await pipe.stop()


async def test_on_ack_errors_are_contained() -> None:
    conn = FakeConn()
    pipe = CommandPipeline(conn, meter_interval=100, on_meters=lambda d: None)
    pipe.start()

    def boom() -> None:
        raise RuntimeError("listener bug")

    assert await pipe.submit(c.SetMute(0, True), on_ack=boom) == r.Ack()
    assert pipe.queue_depth == 0
    await pipe.stop()
