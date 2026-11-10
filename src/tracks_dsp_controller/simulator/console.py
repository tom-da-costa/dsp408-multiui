"""Interactive console of the standalone simulator: change faults and signals while it runs.

Type ``help`` at the ``sim>`` prompt. Each command is one line; ``Console.execute`` returns the
text to print, so the commands are testable without a terminal.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
import threading
from collections.abc import Callable

from tracks_dsp_controller.protocol.codecs import gain_raw_to_db
from tracks_dsp_controller.simulator.device import SimulatedDevice
from tracks_dsp_controller.simulator.meters import Shape, Source
from tracks_dsp_controller.simulator.server import SecondClient, SimulatorServer

HELP = """\
status                          device, connections and active faults
presets                         list the user presets
recall N                        change the preset as from the front panel (0 = F00)
kick                            drop every client connection
offline SECONDS                 stop answering on the network for a while (cable unplugged)
latency MS                      extra delay before each response
drop RATE | corrupt RATE        share of responses dropped / sent with a bad checksum (0-1)
nan RATE                        share of meter frames without data (0-1)
disconnect-after N | off        close each connection after N requests
second-client accept|refuse|kick
signal CH|all SHAPE [DB]        input CH (A-D, or A-B on a 206/204): music|steady|noise|silence
help | quit"""

SIGNAL_CHANNELS = "ABCD"


class ConsoleError(ValueError):
    pass


def _rate(value: str) -> float:
    rate = float(value)
    if not 0.0 <= rate <= 1.0:
        raise ConsoleError("a rate is between 0 and 1")
    return rate


class Console:
    def __init__(self, server: SimulatorServer, stop: Callable[[], None]) -> None:
        self.server = server
        self.stop = stop
        self._offline: asyncio.Task[None] | None = None

    @property
    def device(self) -> SimulatedDevice:
        return self.server.device

    # --- commands -------------------------------------------------------------------------------
    def execute(self, line: str) -> str:
        try:
            words = shlex.split(line)
        except ValueError as exc:
            return f"error: {exc}"
        if not words:
            return ""
        name, args = words[0].lower(), words[1:]
        handler = getattr(self, "cmd_" + name.replace("-", "_"), None)
        if handler is None:
            return f"unknown command {name!r}, type 'help'"
        try:
            result: str = handler(*args)
        except TypeError:
            return f"wrong arguments for {name!r}, type 'help'"
        except ValueError as exc:  # includes ConsoleError
            return f"error: {exc}"
        return result

    def cmd_help(self) -> str:
        return HELP

    def cmd_quit(self) -> str:
        self.stop()
        return "stopping"

    cmd_exit = cmd_quit

    def cmd_status(self) -> str:
        d, f, s = self.device, self.server.faults, self.server
        peers = ", ".join(s.peers()) or "none"
        signals = ", ".join(
            f"{SIGNAL_CHANNELS[i]}={src.shape}"
            + (f" {src.level_db:g} dB" if src.shape is not Shape.SILENCE else "")
            for i, src in enumerate(d.meters.sources)
        )
        return "\n".join(
            (
                f"model           DSP {d.model.key}, identity {d.identity}",
                f"network         {'online' if s.running else 'OFFLINE'}"
                + (f" on {s.host}:{s.bound_port}" if s.running else ""),
                f"clients         {peers} (second client: {s.second_client})",
                f"active preset   {_slot(d.active_slot)} {d.live.preset_name!r}",
                f"input signals   {signals}",
                f"faults          latency {f.extra_latency_s * 1000:g} ms, drop {f.drop_rate:g},"
                f" corrupt {f.corrupt_rate:g}, nan meters {f.nan_meter_rate:g},"
                f" disconnect after {f.disconnect_after or 'never'}",
                f"requests        {d.requests_handled}",
            )
        )

    def cmd_presets(self) -> str:
        d = self.device
        lines = []
        for slot in range(1, d.profile.preset_count + 1):
            mark = "*" if slot == d.active_slot else " "
            lines.append(f"{mark} {_slot(slot)}  {d.presets[slot].preset_name}")
        return "\n".join(lines)

    def cmd_recall(self, slot: str) -> str:
        n = int(slot)
        if not 0 <= n <= self.device.profile.preset_count:
            raise ConsoleError(f"slot must be within 0..{self.device.profile.preset_count}")
        self.device.recall(n)
        live = self.device.live
        gains = ", ".join(f"{gain_raw_to_db(o.gain):g}" for o in live.outputs)
        return f"recalled {_slot(n)} {live.preset_name!r} (output gains dB: {gains})"

    def cmd_kick(self) -> str:
        return f"dropped {self.server.kick()} connection(s)"

    def cmd_offline(self, seconds: str) -> str:
        duration = float(seconds)
        if duration <= 0:
            raise ConsoleError("the duration must be > 0")
        if self._offline is not None and not self._offline.done():
            raise ConsoleError("already offline")
        self._offline = asyncio.get_running_loop().create_task(self._go_offline(duration))
        return f"offline for {duration:g} s"

    async def _go_offline(self, duration: float) -> None:
        port = self.server.bound_port
        await self.server.stop()
        await asyncio.sleep(duration)
        self.server.port = port
        await self.server.start()
        _print("\nback online")

    def cmd_latency(self, ms: str) -> str:
        value = float(ms)
        if value < 0:
            raise ConsoleError("the latency must be >= 0")
        self.server.faults.extra_latency_s = value / 1000
        return f"latency {value:g} ms"

    def cmd_drop(self, rate: str) -> str:
        self.server.faults.drop_rate = _rate(rate)
        return f"drop rate {self.server.faults.drop_rate:g}"

    def cmd_corrupt(self, rate: str) -> str:
        self.server.faults.corrupt_rate = _rate(rate)
        return f"corrupt rate {self.server.faults.corrupt_rate:g}"

    def cmd_nan(self, rate: str) -> str:
        self.server.faults.nan_meter_rate = _rate(rate)
        return f"nan meter rate {self.server.faults.nan_meter_rate:g}"

    def cmd_disconnect_after(self, count: str) -> str:
        if count.lower() == "off":
            self.server.faults.disconnect_after = None
            return "disconnect-after off"
        n = int(count)
        if n < 1:
            raise ConsoleError("N must be >= 1")
        self.server.faults.disconnect_after = n
        return f"each connection closes after {n} requests"

    def cmd_second_client(self, mode: str) -> str:
        self.server.second_client = SecondClient(mode.lower())
        return f"second client: {self.server.second_client}"

    def cmd_signal(self, channel: str, shape: str, level: str | None = None) -> str:
        sources = self.device.meters.sources
        if channel.lower() == "all":
            indices = list(range(len(sources)))
        elif len(channel) == 1 and channel.upper() in SIGNAL_CHANNELS[: len(sources)]:
            indices = [SIGNAL_CHANNELS.index(channel.upper())]
        else:
            last = SIGNAL_CHANNELS[len(sources) - 1]
            raise ConsoleError(f"channel must be A-{last} or all")
        new_shape = Shape(shape.lower())
        for i in indices:
            old = sources[i]
            db = float(level) if level is not None else old.level_db
            sources[i] = Source(new_shape, db, old.depth_db, old.period_s)
        return f"signal {channel.upper()}: {new_shape}" + (
            f" {float(level):g} dB" if level is not None else ""
        )

    # --- terminal loop ----------------------------------------------------------------------------
    async def run(self) -> None:
        """Read commands from stdin until EOF or ``quit``."""
        lines = _stdin_lines()
        _print("Type 'help' for the console commands.")
        while True:
            _print("sim> ", end="")
            line = await lines.get()
            if line is None:  # EOF: keep the simulator running without a console
                _print("")
                return
            out = self.execute(line)
            if out:
                _print(out)
            if line.strip().lower() in ("quit", "exit"):
                return


def _stdin_lines() -> asyncio.Queue[str | None]:
    """Lines of stdin, read by a daemon thread (so that exiting never waits for a keypress)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def reader() -> None:
        for line in sys.stdin:
            loop.call_soon_threadsafe(queue.put_nowait, line)
        loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=reader, name="sim-console", daemon=True).start()
    return queue


def _slot(slot: int) -> str:
    return "F00" if slot == 0 else f"U{slot:02d}"


def _print(text: str, end: str = "\n") -> None:
    print(text, end=end, flush=True)
