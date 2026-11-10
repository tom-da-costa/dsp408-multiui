"""End to end: ``tracks-dsp-sim`` and ``tracks-dsp-controller`` run as two separate programs.

The simulator listens on TCP like a DSP 408; the app connects to it with ``--dsp-host``. The
tests then drive the app as the browser does (HTTP login, WebSocket) and check the effect on the
simulated DSP over TCP, as a second client of it.

Run with ``uv run pytest -m e2e`` (or ``make e2e``); excluded from the default run.
The programs default to ``python -m …``; ``DSP408_E2E_SIM_CMD`` / ``DSP408_E2E_APP_CMD`` select
other commands, e.g. the built executables. ``DSP408_E2E_LOG_DIR`` keeps the programs' output.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.asyncio.client import ClientConnection, connect

from tracks_dsp_controller.device.transport import DspConnection
from tracks_dsp_controller.protocol import config_map as cm
from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE as P
from tracks_dsp_controller.simulator.storage import preset_file
from tracks_dsp_controller.tools import probe

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[2]
U08 = ROOT / "tests" / "fixtures" / "config" / "dsp408_u08.bin"
PIN = "2468"
STARTUP_S = 30.0
Message = dict[str, Any]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def command(env: str, module: str) -> list[str]:
    custom = os.environ.get(env)
    return shlex.split(custom) if custom else [sys.executable, "-m", module]


@dataclass
class Stack:
    log_dir: Path
    state_dir: Path
    sim_port: int = field(default_factory=free_port)
    app_port: int = field(default_factory=free_port)
    sim: subprocess.Popen[bytes] | None = None
    app: subprocess.Popen[bytes] | None = None
    starts: int = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.app_port}"

    def _spawn(self, name: str, argv: list[str]) -> subprocess.Popen[bytes]:
        self.starts += 1
        with (self.log_dir / f"{self.starts:02d}-{name}.log").open("wb") as log:
            # the child keeps its own copy of the file descriptor
            return subprocess.Popen(
                argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )

    def start_sim(self) -> None:
        self.sim = self._spawn(
            "tracks-dsp-sim",
            [
                *command("DSP408_E2E_SIM_CMD", "tracks_dsp_controller.simulator"),
                "--host", "127.0.0.1", "--port", str(self.sim_port),
                "--state-dir", str(self.state_dir), "--fast", "--console", "off",
                *(["--preset", f"8={U08}"] if self.starts == 0 else []),
            ],
        )  # fmt: skip

    def start_app(self) -> None:
        self.app = self._spawn(
            "tracks-dsp-controller",
            [
                *command("DSP408_E2E_APP_CMD", "tracks_dsp_controller"),
                "--dsp-host", "127.0.0.1", "--dsp-port", str(self.sim_port),
                "--host", "127.0.0.1", "--port", str(self.app_port), "--pin", PIN,
                "--meter-rate", "10",
            ],
        )  # fmt: skip

    def stop_sim(self) -> None:
        _stop(self.sim)
        self.sim = None

    def stop(self) -> None:
        _stop(self.app)
        self.stop_sim()

    def health(self) -> Message | None:
        try:
            reply = httpx.get(f"{self.base_url}/api/health", timeout=2)
        except httpx.HTTPError:
            return None
        data: Message = reply.json()
        return data

    def wait_device(self, status: str, timeout: float = STARTUP_S) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for proc in (self.sim, self.app):
                if proc is not None and proc.poll() is not None:
                    raise AssertionError(f"{proc.args[:3]} exited with {proc.returncode}")
            health = self.health()
            if health is not None and health["device_status"] == status:
                return
            time.sleep(0.2)
        raise AssertionError(f"device not {status} after {timeout} s: {self.health()}")

    def login(self, name: str) -> str:
        reply = httpx.post(f"{self.base_url}/api/login", json={"pin": PIN, "name": name})
        reply.raise_for_status()
        return reply.cookies["dsp408_session"]


def _stop(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    base = tmp_path_factory.mktemp("e2e")
    log_dir = Path(os.environ.get("DSP408_E2E_LOG_DIR") or base / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    s = Stack(log_dir=log_dir, state_dir=base / "sim-state")
    s.start_sim()
    s.start_app()  # in parallel: the app retries until the simulated DSP answers
    try:
        s.wait_device("online")
        yield s
    finally:
        s.stop()
        for log in sorted(log_dir.glob("*.log")):
            print(f"--- {log.name}\n{log.read_text(errors='replace')[-3000:]}")


# --- WebSocket helpers ------------------------------------------------------------------------
class Client:
    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.req = 0

    async def recv_until(self, match: Callable[[Message], bool], timeout: float = 10) -> Message:
        async with asyncio.timeout(timeout):
            while True:
                message: Message = json.loads(await self.ws.recv())
                if match(message):
                    return message

    async def request(self, message: Message) -> Message:
        self.req += 1
        req = self.req
        await self.ws.send(json.dumps({**message, "req": req}))
        return await self.recv_until(lambda m: m["type"] == "result" and m["req"] == req)


def ws_connect(stack: Stack, cookie: str) -> Any:
    return connect(
        f"ws://127.0.0.1:{stack.app_port}/ws",
        additional_headers={"Cookie": f"dsp408_session={cookie}", "Origin": stack.base_url},
    )


async def read_dsp_config(stack: Stack) -> cm.RawConfig:
    """Read the simulated DSP's live config directly, as a second TCP client of it."""
    async with DspConnection("127.0.0.1", stack.sim_port, P) as conn:
        await probe.read_info(conn)  # init sequence
        return cm.decode_config(await probe.read_config_blob(conn))


def is_type(kind: str) -> Callable[[Message], bool]:
    return lambda m: m["type"] == kind


def has_change(path: str) -> Callable[[Message], bool]:
    return lambda m: m["type"] == "patch" and any(c["path"] == path for c in m["changes"])


# --- tests ----------------------------------------------------------------------------------------
def test_health_and_login(stack: Stack) -> None:
    health = stack.health()
    assert health is not None
    assert health["device_status"] == "online"
    assert health["demo"] is False
    wrong = httpx.post(f"{stack.base_url}/api/login", json={"pin": "0000"})
    assert wrong.status_code == 401
    assert httpx.get(f"{stack.base_url}/").status_code == 200  # the UI is served


async def test_state_mirrors_the_simulated_dsp(stack: Stack) -> None:
    async with ws_connect(stack, stack.login("Alice")) as ws:
        alice = Client(ws)
        hello = await alice.recv_until(is_type("hello"))
        assert hello["demo"] is False
        assert hello["name"] == "Alice"
        state = (await alice.recv_until(is_type("snapshot")))["state"]
        assert state["info"]["model"] == "DSP408"
        assert state["active_slot"] == 8
        assert state["preset_name"] == "Pas touché svp"
        assert state["outputs"][0]["linked"] == [4]
        meters = await alice.recv_until(lambda m: m["type"] == "meters" and m["levels"])
        assert len(meters["levels"]) == 12


async def test_write_lock_and_fan_out(stack: Stack) -> None:
    async with (
        ws_connect(stack, stack.login("Alice")) as ws_a,
        ws_connect(stack, stack.login("Bob")) as ws_b,
    ):
        alice, bob = Client(ws_a), Client(ws_b)
        for client in (alice, bob):
            await client.recv_until(is_type("snapshot"))

        result = await alice.request({"type": "set", "path": "outputs.0.gain_db", "value": -6.0})
        assert result["ok"], result
        patch = await bob.recv_until(has_change("outputs.0.gain_db"))
        changes = {c["path"]: c["value"] for c in patch["changes"]}
        assert changes["outputs.0.gain_db"] == -6.0
        assert changes["outputs.4.gain_db"] == -6.0  # Out1 and Out5 are linked on U08
        dsp = await read_dsp_config(stack)
        assert dsp.outputs[0].gain == dsp.outputs[4].gain == 220  # -6 dB on the DSP

        assert (await alice.request({"type": "lock.acquire"}))["ok"]
        refused = await bob.request({"type": "set", "path": "inputs.0.mute", "value": True})
        assert refused == {**refused, "ok": False, "error": "locked"}
        assert (await alice.request({"type": "lock.release"}))["ok"]

        invalid = await bob.request({"type": "set", "path": "outputs.9.gain_db", "value": 0})
        assert invalid["error"] == "invalid"


async def test_store_preset_is_kept_by_the_dsp(stack: Stack) -> None:
    async with ws_connect(stack, stack.login("Alice")) as ws:
        alice = Client(ws)
        await alice.recv_until(is_type("snapshot"))
        result = await alice.request({"type": "preset.store", "slot": 4, "name": "CI stored"})
        assert result["ok"], result
    stored = cm.decode_config(preset_file(stack.state_dir, 4).read_bytes())
    assert stored.preset_name == "CI stored"
    assert stored.outputs[0].gain == 220


async def test_dsp_restart_reconnects_and_keeps_presets(stack: Stack) -> None:
    async with ws_connect(stack, stack.login("Alice")) as ws:
        alice = Client(ws)
        await alice.recv_until(is_type("snapshot"))
        stack.stop_sim()  # the DSP goes away (power cycle)
        await alice.recv_until(lambda m: m["type"] == "device" and m["status"] != "online")
        result = await alice.request({"type": "set", "path": "inputs.0.gain_db", "value": -1.0})
        assert result["error"] == "device_offline"

        stack.start_sim()  # same port and state directory, no --preset this time
        # The app reconnects by itself, reads the config (snapshot), then reports online.
        state = (await alice.recv_until(is_type("snapshot"), 30))["state"]
        stack.wait_device("online")
        assert state["active_slot"] == 4
        assert state["preset_name"] == "CI stored"
        assert state["presets"][3]["name"] == "CI stored"
        assert state["presets"][7]["name"] == "Pas touché svp"
        assert (await alice.request({"type": "set", "path": "inputs.0.gain_db", "value": -1.0}))[
            "ok"
        ]
