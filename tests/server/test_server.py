"""Server: auth, lock, WebSocket fan-out, against the embedded simulator."""

import base64
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from tracks_dsp_controller.protocol.profile import DEFAULT_PROFILE
from tracks_dsp_controller.server.app import AppContext, create_app
from tracks_dsp_controller.server.auth import AuthManager, LoginError, RateLimitedError, clean_name
from tracks_dsp_controller.server.lock import LockManager
from tracks_dsp_controller.server.master import MasterManager, MasterState
from tracks_dsp_controller.server.settings import ServerConfig
from tracks_dsp_controller.simulator import Faults, SimulatedDevice, apply_scenario
from tracks_dsp_controller.state import registry

P = DEFAULT_PROFILE.with_overrides({"timing": {"command_timeout_s": 0.3}})


# --- unit: auth ----------------------------------------------------------------------------------
def test_auth_login_logout_and_rate_limit() -> None:
    now = [0.0]
    auth = AuthManager("1234", clock=lambda: now[0])
    session = auth.login("1234", "  FOH\x00 phone ", "10.0.0.2")
    assert session.name == "FOH phone"
    assert auth.get(session.token) is session
    assert auth.get(None) is None
    for _ in range(5):
        with pytest.raises(LoginError):
            auth.login("0000", None, "10.0.0.3")
    with pytest.raises(RateLimitedError):
        auth.login("1234", None, "10.0.0.3")  # even the right code is refused
    assert auth.login("1234", None, "10.0.0.4").name.startswith("Client")  # other IP is fine
    now[0] = 31.0
    assert auth.login("1234", None, "10.0.0.3")
    assert auth.logout(session.token) is session
    assert auth.get(session.token) is None
    assert clean_name("", "fallback") == "fallback"
    assert len(clean_name("x" * 100, "f")) == 32


# --- unit: lock -----------------------------------------------------------------------------------
def test_lock_activity_and_idle_expiry() -> None:
    now = [0.0]
    lock = LockManager(120, clock=lambda: now[0])
    changes: list[str | None] = []
    lock.on_change(lambda state: changes.append(state.owner_id))
    assert lock.acquire("a", "Alice")
    assert not lock.acquire("b", "Bob")
    assert lock.can_write("a")
    assert not lock.can_write("b")
    now[0] = 100.0
    lock.touch("b")  # not the owner: no effect
    lock.touch("a")
    now[0] = 200.0
    assert not lock.expire()  # 100 s since the last activity
    assert lock.state().idle_expires_at == 220.0
    now[0] = 221.0
    assert lock.expire()
    assert lock.can_write("b")
    assert lock.acquire("b", "Bob")
    assert not lock.release("a")
    assert lock.state().owner_name == "Bob"
    assert lock.release("b")
    assert changes == ["a", None, "b", None]
    with pytest.raises(ValueError, match="idle_timeout"):
        LockManager(0)


# --- unit: master role ----------------------------------------------------------------------------
def test_master_role_block_and_absence() -> None:
    now = [0.0]
    master = MasterManager(300, clock=lambda: now[0])
    states: list[tuple[str | None, bool]] = []
    master.on_change(lambda s: states.append((s.owner_id, s.logins_blocked)))
    assert not master.block_logins("a", True)  # nobody is the master yet
    assert master.acquire("a", "Alice")
    assert master.acquire("a", "Alice")  # already the master: fine, no event
    assert not master.acquire("b", "Bob")
    assert not master.block_logins("b", True)
    assert master.block_logins("a", True)
    assert master.logins_blocked
    # away for a while: a reload or a short network loss keeps the role
    master.presence("a", False)
    now[0] = 200.0
    assert not master.expire()
    master.presence("a", True)
    now[0] = 1000.0
    assert not master.expire()
    # away for too long: the role ends, and the block with it
    master.presence("a", False)
    now[0] = 1301.0
    assert master.expire()
    assert master.state() == MasterState(None, None, False)
    assert master.acquire("b", "Bob")
    assert not master.release("a")
    assert master.release("b")
    assert states == [("a", False), ("a", True), (None, False), ("b", False), (None, False)]
    with pytest.raises(ValueError, match="absent_timeout"):
        MasterManager(0)


def test_server_config_validation() -> None:
    with pytest.raises(ValueError, match="dsp-host"):
        ServerConfig()
    with pytest.raises(ValueError, match="code"):
        ServerConfig(demo=True, pin="")
    with pytest.raises(ValueError, match="lock"):
        ServerConfig(demo=True, lock_idle_timeout_s=0)
    with pytest.raises(ValueError, match="resync"):
        ServerConfig(demo=True, resync_interval_s=-1)
    assert ServerConfig(demo=True).allow_unverified
    assert not ServerConfig(dsp_host="10.0.0.9").allow_unverified


# --- integration -------------------------------------------------------------------------------
def make_app(tmp_path: Path, **overrides: Any) -> tuple[Any, SimulatedDevice]:
    device = SimulatedDevice(P)
    device.timing.default_s = 0.0
    device.timing.recall_s = 0.01
    device.timing.store_s = 0.01
    apply_scenario("demo", device, Faults())
    config = ServerConfig(demo=True, pin="4321", meter_rate_hz=10, **overrides)
    app = create_app(config, P, web_dir=tmp_path, simulated_device=device)
    return app, device


@pytest.fixture
def web_dir(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<!doctype html><title>UI</title>")
    (tmp_path / "app.js").write_text("console.log('ui')")
    return tmp_path


@pytest.fixture
def client(web_dir: Path) -> Iterator[TestClient]:
    app, _ = make_app(web_dir)
    with TestClient(app) as test_client:
        ctx: AppContext = app.state.ctx
        deadline = time.monotonic() + 5
        while ctx.session.status.value != "online" and time.monotonic() < deadline:
            time.sleep(0.02)
        yield test_client


def login(client: TestClient, name: str = "tester") -> None:
    response = client.post("/api/login", json={"pin": "4321", "name": name})
    assert response.status_code == 200, response.text


_BACKLOG: dict[int, list[dict[str, Any]]] = {}


@pytest.fixture(autouse=True)
def _fresh_backlog() -> Iterator[None]:
    """The backlog is keyed by the socket's id(), which a later test's socket can reuse: start
    each test with none, or it would read another test's leftover messages."""
    _BACKLOG.clear()
    yield
    _BACKLOG.clear()


def receive_until(ws: WebSocketTestSession, kind: str, limit: int = 200) -> dict[str, Any]:
    """Next message of ``kind``; messages skipped by ``request`` are looked at first."""
    backlog = _BACKLOG.setdefault(id(ws), [])
    for i, message in enumerate(backlog):
        if message["type"] == kind:
            return backlog.pop(i)
    for _ in range(limit):
        received: dict[str, Any] = ws.receive_json()
        if received["type"] == kind:
            return received
    raise AssertionError(f"no {kind!r} message")


def request(ws: WebSocketTestSession, message: dict[str, Any]) -> dict[str, Any]:
    """Send a request and return its result, keeping other messages for ``receive_until``."""
    ws.send_json(message)
    backlog = _BACKLOG.setdefault(id(ws), [])
    while True:
        received: dict[str, Any] = ws.receive_json()
        if received["type"] == "result" and received["req"] == message.get("req"):
            return received
        if received["type"] != "meters":
            backlog.append(received)


def drain(ws: WebSocketTestSession) -> None:
    for _ in range(100):
        ws.receive_json()


def test_health_and_static(client: TestClient, web_dir: Path) -> None:
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["device_status"] == "online"
    assert client.get("/").text.startswith("<!doctype html><title>UI")
    assert client.get("/app.js").text == "console.log('ui')"
    assert client.get("/presets").text.startswith("<!doctype html><title>UI")  # SPA fallback
    assert "UI" in client.get("/../../etc/passwd").text  # no path traversal


def test_placeholder_without_ui(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    with TestClient(app) as test_client:
        assert "not built" in test_client.get("/").text


def test_login_flow(client: TestClient) -> None:
    assert client.get("/api/session").status_code == 401
    wrong = client.post("/api/login", json={"pin": "0000"})
    assert wrong.status_code == 401
    login(client, "FOH")
    me = client.get("/api/session").json()
    assert me["authenticated"]
    assert me["name"] == "FOH"
    assert client.post("/api/logout").json() == {"ok": True}
    assert client.get("/api/session").status_code == 401


def test_login_rate_limit(client: TestClient) -> None:
    for _ in range(5):
        client.post("/api/login", json={"pin": "bad"})
    response = client.post("/api/login", json={"pin": "4321"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_websocket_requires_login_and_same_origin(client: TestClient) -> None:
    # Accepted, then closed with 4401: a browser only sees the code after the handshake.
    with client.websocket_connect("/ws") as ws, pytest.raises(WebSocketDisconnect) as info:
        ws.receive_json()
    assert info.value.code == 4401
    login(client)
    with (
        pytest.raises(WebSocketDisconnect) as info,
        client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws,
    ):
        ws.receive_json()
    assert info.value.code == 4403


def test_hello_snapshot_and_write(client: TestClient) -> None:
    login(client, "Alice")
    with client.websocket_connect("/ws") as ws:
        hello = receive_until(ws, "hello")
        assert hello["name"] == "Alice"
        assert hello["demo"] is True
        assert hello["profile"]["output_count"] == 8
        assert len(hello["profile"]["slopes"]) == 21
        assert hello["limits"]["threshold_db"] == [-90.0, 20.0]
        assert hello["limits"]["channel_name_length"] == 8
        snapshot = receive_until(ws, "snapshot")
        assert snapshot["state"]["preset_name"] == "Demo 3-way"
        assert receive_until(ws, "device")["status"] == "online"
        assert receive_until(ws, "lock")["owner_id"] is None
        reply = request(ws, {"type": "set", "req": 1, "path": "outputs.0.gain_db", "value": -6.04})
        assert reply == {"type": "result", "req": 1, "ok": True}
        patch = receive_until(ws, "patch")
        assert patch["changes"] == [
            {"path": "outputs.0.gain_db", "value": -6.0},
            {"path": "modified", "value": True},  # the first change since the connection
        ]
        assert patch["origin"] == hello["client_id"]
        assert patch["rev"] > snapshot["rev"]


def test_fast_writes_from_one_client_coalesce(web_dir: Path) -> None:
    """A dragged control: values sent faster than the DSP answers are not replayed one by one."""
    app, device = make_app(web_dir)
    device.timing.default_s = 0.05
    with TestClient(app) as test_client:
        ctx: AppContext = app.state.ctx
        deadline = time.monotonic() + 5
        while ctx.session.status.value != "online" and time.monotonic() < deadline:
            time.sleep(0.02)
        login(test_client)
        with test_client.websocket_connect("/ws") as ws:
            receive_until(ws, "snapshot")
            values = [-1.0 * n for n in range(1, 11)]
            for req, value in enumerate(values, start=1):
                ws.send_json(
                    {"type": "set", "req": req, "path": "outputs.0.gain_db", "value": value}
                )
            results: list[dict[str, Any]] = []
            gains: list[float] = []
            while len(results) < len(values):
                message = ws.receive_json()
                if message["type"] == "result":
                    results.append(message)
                elif message["type"] == "patch":
                    gains += [
                        c["value"] for c in message["changes"] if c["path"] == "outputs.0.gain_db"
                    ]
    assert all(r["ok"] for r in results)
    assert sorted(r["req"] for r in results) == list(range(1, 11))
    assert gains[-1] == values[-1]
    assert len(gains) <= 3  # one in flight, the rest coalesced into the newest


def test_channel_detail_writes(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        receive_until(ws, "lock")
        band = {"gain_db": 3.04, "freq_hz": 1000, "q": 1.4, "type": 0, "bypass": False}
        assert request(ws, {"type": "set", "req": 1, "path": "outputs.2.peq.0", "value": band})[
            "ok"
        ]
        value = receive_until(ws, "patch")["changes"][0]["value"]
        assert value["gain_db"] == 3.0
        assert value["freq_hz"] == pytest.approx(1000, rel=0.02)
        comp = {"ratio": 4, "threshold_db": -20.2}
        assert request(
            ws, {"type": "set", "req": 2, "path": "outputs.2.compressor", "value": comp}
        )["ok"]
        value = receive_until(ws, "patch")["changes"][0]["value"]
        assert value["ratio"] == 4
        assert value["threshold_db"] == -20.0
        bad = request(ws, {"type": "set", "req": 3, "path": "inputs.0.name", "value": "too long!"})
        assert bad["error"] == "invalid"


def test_meters_are_streamed(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        meters = receive_until(ws, "meters")
        assert len(meters["levels"]) == 12
        assert len(meters["limit"]) == 8
        assert len(meters["comp"]) == 8


def test_invalid_requests(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        cases = [
            ({"type": "set", "req": 1, "path": "outputs.0.gain_db", "value": "x"}, "invalid"),
            ({"type": "set", "req": 2, "path": 5, "value": 1}, "invalid"),
            ({"type": "preset.recall", "req": 3, "slot": "1"}, "invalid"),
            ({"type": "preset.recall", "req": 4, "slot": 99}, "invalid"),
            ({"type": "preset.store", "req": 5, "slot": 1, "name": "fifteen chars!!"}, "invalid"),
            ({"type": "preset.store", "req": 6, "slot": 0, "name": "x"}, "invalid"),
            ({"type": "preset.store", "req": 7, "slot": 1}, "invalid"),
            ({"type": "settings.set", "req": 8, "meter_rate_hz": "fast"}, "invalid"),
            ({"type": "lock.release", "req": 9}, "invalid"),
            ({"type": "bogus", "req": 10}, "invalid"),
            ({"type": "rename", "req": 11, "name": "x"}, "invalid"),  # names are set at login
        ]
        for message, error in cases:
            reply = request(ws, message)
            assert reply["ok"] is False, message
            assert reply["error"] == error, (message, reply)
        ws.send_text("not json")
        assert receive_until(ws, "result")["error"] == "invalid"
        ws.send_json([1, 2])
        assert receive_until(ws, "result")["error"] == "invalid"
        ws.send_json({"type": "ping", "req": 99})
        assert receive_until(ws, "pong")["req"] == 99


def test_two_clients_and_the_lock(client: TestClient) -> None:
    ctx: AppContext = client.app.state.ctx  # type: ignore[attr-defined]
    device = ctx.simulator.device if ctx.simulator else None
    assert device is not None
    login(client, "Alice")  # each WebSocket takes the cookie set at connection time
    with client.websocket_connect("/ws") as alice:
        login(client, "Bob")
        with client.websocket_connect("/ws") as bob:
            alice_id = receive_until(alice, "hello")["client_id"]
            receive_until(bob, "hello")
            clients = receive_until(bob, "clients")
            while len(clients["clients"]) < 2:
                clients = receive_until(bob, "clients")
            assert {c["name"] for c in clients["clients"]} == {"Alice", "Bob"}

            # last writer wins, everyone sees every change
            request(alice, {"type": "set", "req": 1, "path": "outputs.1.mute", "value": True})
            patch = receive_until(bob, "patch")
            assert patch["changes"][0]["path"] == "outputs.1.mute"
            assert patch["origin"] == alice_id

            # Alice locks: Bob becomes read-only
            assert request(alice, {"type": "lock.acquire", "req": 2})["ok"]
            lock = receive_until(bob, "lock")
            assert lock["owner_name"] == "Alice"
            assert lock["idle_remaining_s"] == pytest.approx(120, abs=1)
            denied = request(
                bob, {"type": "set", "req": 3, "path": "outputs.1.mute", "value": False}
            )
            assert denied["error"] == "locked"
            assert "Alice" in denied["message"]
            assert request(bob, {"type": "lock.acquire", "req": 4})["error"] == "locked"
            assert request(bob, {"type": "preset.recall", "req": 5, "slot": 2})["error"] == "locked"
            assert request(
                alice, {"type": "set", "req": 6, "path": "outputs.1.mute", "value": False}
            )["ok"]

            # the lock expires after the owner's idle timeout
            ctx.lock.clock = lambda: time.monotonic() + 1000
            ctx.lock.expire()
            assert receive_until(bob, "lock")["owner_id"] is None
            assert request(bob, {"type": "set", "req": 7, "path": "outputs.1.mute", "value": True})[
                "ok"
            ]
            assert device.live.outputs[1].mute


def test_screen_lock(client: TestClient) -> None:
    """A locked screen refuses every request until the access code is typed again."""
    login(client, "FOH")
    with client.websocket_connect("/ws") as ws:
        assert receive_until(ws, "hello")["screen_locked"] is False
        assert request(ws, {"type": "screen.lock", "req": 1})["ok"]
        assert receive_until(ws, "screen_lock")["locked"] is True
        denied = request(ws, {"type": "set", "req": 2, "path": "outputs.0.mute", "value": True})
        assert denied["error"] == "screen_locked"
        assert request(ws, {"type": "lock.acquire", "req": 3})["error"] == "screen_locked"
        wrong = request(ws, {"type": "screen.unlock", "req": 4, "pin": "0000"})
        assert wrong["error"] == "wrong_code"
    # a reload (new WebSocket, same session) stays locked
    with client.websocket_connect("/ws") as ws:
        assert receive_until(ws, "hello")["screen_locked"] is True
        assert request(ws, {"type": "screen.unlock", "req": 5, "pin": "4321"})["ok"]
        assert receive_until(ws, "screen_lock")["locked"] is False
        assert request(ws, {"type": "set", "req": 6, "path": "outputs.0.mute", "value": True})["ok"]


def test_screen_unlock_is_rate_limited(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        receive_until(ws, "hello")
        assert request(ws, {"type": "screen.lock", "req": 1})["ok"]
        for req in range(2, 7):
            assert request(ws, {"type": "screen.unlock", "req": req, "pin": "bad"})["error"] == (
                "wrong_code"
            )
        limited = request(ws, {"type": "screen.unlock", "req": 7, "pin": "4321"})
        assert limited["error"] == "rate_limited"  # even the right code, as for the login


def test_presets_settings_resync(client: TestClient) -> None:
    login(client, "Op")
    with client.websocket_connect("/ws") as ws:
        receive_until(ws, "snapshot")
        assert request(ws, {"type": "preset.store", "req": 1, "slot": 4, "name": "Encore"})["ok"]
        patch = receive_until(ws, "patch")
        assert {"path": "presets.3.name", "value": "Encore"} in patch["changes"]
        assert request(ws, {"type": "preset.recall", "req": 2, "slot": 2})["ok"]
        assert receive_until(ws, "snapshot")["state"]["preset_name"] == "Mono Sub"
        assert request(ws, {"type": "settings.set", "req": 3, "meter_rate_hz": 50})["ok"]
        assert receive_until(ws, "settings")["meter_rate_hz"] == 10
        assert request(ws, {"type": "resync", "req": 5})["ok"]
        assert receive_until(ws, "snapshot")


def test_unverified_parameters_need_experimental_on_real_hardware(
    web_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every current kind is verified; pretend delay is not, to exercise the gate.
    monkeypatch.setattr(registry, "HARDWARE_VERIFIED", registry.HARDWARE_VERIFIED - {"delay_ms"})
    app, _ = make_app(web_dir)
    ctx: AppContext = app.state.ctx
    ctx.config.demo = False  # pretend this is a real DSP without --experimental
    with TestClient(app) as test_client:
        deadline = time.monotonic() + 5
        while ctx.session.status.value != "online" and time.monotonic() < deadline:
            time.sleep(0.02)
        login(test_client)
        with test_client.websocket_connect("/ws") as ws:
            reply = request(ws, {"type": "set", "req": 1, "path": "outputs.0.delay_ms", "value": 1})
            assert reply["error"] == "experimental"
            ok = request(ws, {"type": "set", "req": 2, "path": "outputs.0.gain_db", "value": -1})
            assert ok["ok"]


def test_modified_tracks_unsaved_changes(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        assert receive_until(ws, "snapshot")["state"]["modified"] is None  # unknown at start
        assert request(ws, {"type": "preset.recall", "req": 1, "slot": 1})["ok"]
        assert receive_until(ws, "snapshot")["state"]["modified"] is False
        assert request(ws, {"type": "set", "req": 2, "path": "inputs.0.mute", "value": True})["ok"]
        changes = receive_until(ws, "patch")["changes"]
        assert {"path": "modified", "value": True} in changes
        assert request(ws, {"type": "set", "req": 3, "path": "inputs.0.mute", "value": False})["ok"]
        assert receive_until(ws, "patch")["changes"] == [{"path": "inputs.0.mute", "value": False}]
        assert request(ws, {"type": "resync", "req": 4})["ok"]
        assert receive_until(ws, "snapshot")["state"]["modified"] is True  # still unsaved
        assert request(ws, {"type": "preset.store", "req": 5, "slot": 1, "name": "Saved"})["ok"]
        store = receive_until(ws, "patch")["changes"]
        assert {"path": "modified", "value": False} in store


def test_links(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        state = receive_until(ws, "snapshot")["state"]
        out1, out2 = state["outputs"][0], state["outputs"][1]
        assert out1["linked"] == []
        assert out2["linked"] == []
        link = {"type": "link.set", "req": 1, "side": "outputs", "groups": [[0, 1]]}
        assert request(ws, link)["ok"]
        state = receive_until(ws, "snapshot")["state"]
        assert state["outputs"][0]["linked"] == [1]
        assert state["outputs"][1]["linked"] == [0]
        # Out 2 took Out 1's settings, but kept its name and routing
        assert state["outputs"][1]["crossover"] == out1["crossover"]
        assert state["outputs"][1]["name"] == out2["name"]
        assert state["outputs"][1]["matrix"] == out2["matrix"]
        # a write to one member now changes both
        assert request(ws, {"type": "set", "req": 2, "path": "outputs.1.gain_db", "value": -3})[
            "ok"
        ]
        receive_until(ws, "patch")
        unlink = {"type": "link.set", "req": 3, "side": "outputs", "groups": []}
        reply = request(ws, unlink)
        assert reply["ok"], reply
        state = receive_until(ws, "snapshot")["state"]
        assert state["outputs"][0]["linked"] == []
        assert state["outputs"][0]["gain_db"] == state["outputs"][1]["gain_db"] == -3
        for bad in (
            {"side": "both", "groups": []},
            {"side": "inputs", "groups": [[0, 9]]},
            {"side": "inputs", "groups": "A+B"},
            {"side": "inputs", "groups": [[0, 1], [1, 2]]},
        ):
            reply = request(ws, {"type": "link.set", "req": 9, **bad})
            assert reply["error"] == "invalid", bad


def test_links_need_experimental_when_unverified(
    web_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "HARDWARE_VERIFIED", registry.HARDWARE_VERIFIED - {"link"})
    app, _ = make_app(web_dir)
    ctx: AppContext = app.state.ctx
    ctx.config.demo = False
    with TestClient(app) as test_client:
        deadline = time.monotonic() + 5
        while ctx.session.status.value != "online" and time.monotonic() < deadline:
            time.sleep(0.02)
        login(test_client)
        with test_client.websocket_connect("/ws") as ws:
            link = {"type": "link.set", "req": 1, "side": "inputs", "groups": [[0, 1]]}
            assert request(ws, link)["error"] == "experimental"


def test_logout_closes_websockets_and_releases_lock(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws") as ws:
        assert request(ws, {"type": "lock.acquire", "req": 1})["ok"]
        client.post("/api/logout")
        with pytest.raises(WebSocketDisconnect):
            drain(ws)


def test_master_disconnects_a_client_and_blocks_new_logins(client: TestClient) -> None:
    login(client, "Alice")
    alice_cookie = client.cookies.get("dsp408_session")
    with client.websocket_connect("/ws") as alice:
        login(client, "Bob")
        bob_cookie = client.cookies.get("dsp408_session")
        with client.websocket_connect("/ws") as bob:
            receive_until(alice, "hello")
            bob_id = receive_until(bob, "hello")["client_id"]
            assert receive_until(bob, "master")["owner_id"] is None

            # only the master may disconnect or block
            denied = request(bob, {"type": "client.kick", "req": 1, "client_id": bob_id})
            assert denied["error"] == "not_master"
            assert request(bob, {"type": "logins.block", "req": 2, "blocked": True})["error"] == (
                "not_master"
            )
            assert request(alice, {"type": "master.acquire", "req": 3})["ok"]
            master = receive_until(bob, "master")
            assert master["owner_name"] == "Alice"
            assert request(bob, {"type": "master.acquire", "req": 4})["error"] == "master_taken"

            # Alice blocks new logins: the code is checked, then the login refused
            assert request(alice, {"type": "logins.block", "req": 5, "blocked": True})["ok"]
            assert receive_until(bob, "master")["logins_blocked"]
            refused = client.post("/api/login", json={"pin": "4321", "name": "Carol"})
            assert refused.status_code == 403
            assert refused.json() == {
                "error": "logins_blocked",
                "message": "New connections are blocked by Alice",
            }
            assert client.post("/api/login", json={"pin": "nope"}).status_code == 401

            # Alice disconnects Bob: his session ends, his browser gets the login with a reason
            assert request(alice, {"type": "client.kick", "req": 6, "client_id": bob_id})["ok"]
            with pytest.raises(WebSocketDisconnect) as closed:
                drain(bob)
            assert closed.value.code == 4401
            assert closed.value.reason == "Disconnected by Alice"
        client.cookies.set("dsp408_session", bob_cookie or "")
        assert client.get("/api/session").status_code == 401
        assert request(alice, {"type": "client.kick", "req": 7, "client_id": bob_id})["error"] == (
            "invalid"
        )

        # the block ends with the role
        assert request(alice, {"type": "master.release", "req": 8})["ok"]
        assert not receive_until(alice, "master")["logins_blocked"]
        login(client, "Carol")
        # a master logging out gives the role up
        client.cookies.set("dsp408_session", alice_cookie or "")
        assert request(alice, {"type": "master.acquire", "req": 9})["ok"]
        client.post("/api/logout")
    ctx: AppContext = client.app.state.ctx  # type: ignore[attr-defined]
    assert ctx.master.state().owner_id is None


def test_shutdown_disconnects_the_dsp_then_stops_the_server(client: TestClient) -> None:
    ctx: AppContext = client.app.state.ctx  # type: ignore[attr-defined]
    exits: list[bool] = []
    login(client, "Alice")
    with client.websocket_connect("/ws") as alice:
        login(client, "Bob")
        with client.websocket_connect("/ws") as bob:
            receive_until(alice, "hello")
            receive_until(bob, "hello")
            # not available unless the CLI wired the exit
            assert request(bob, {"type": "server.shutdown", "req": 1})["error"] == "unsupported"
            ctx.hub.request_exit = lambda: exits.append(True)
            # another client has control, or is the master: refused
            assert request(alice, {"type": "lock.acquire", "req": 2})["ok"]
            assert request(bob, {"type": "server.shutdown", "req": 3})["error"] == "locked"
            assert request(alice, {"type": "lock.release", "req": 4})["ok"]
            assert request(alice, {"type": "master.acquire", "req": 5})["ok"]
            assert request(bob, {"type": "server.shutdown", "req": 6})["error"] == "not_master"
            assert not exits
            # the master may: every client is told, the DSP is let go, then the server stops
            assert request(alice, {"type": "server.shutdown", "req": 7})["ok"]
            assert receive_until(bob, "shutdown")["by"] == "Alice"
            assert ctx.session.status.value == "stopped"
            assert exits == [True]


def test_preset_export_and_import(client: TestClient) -> None:
    login(client, "Op")
    with client.websocket_connect("/ws") as ws:
        receive_until(ws, "snapshot")
        exported = request(ws, {"type": "preset.export", "req": 1})
        assert exported["ok"]
        assert exported["filename"] == "Demo 3-way.prs"
        data = base64.b64decode(exported["data"])
        assert data.startswith(b"***DSP408V010***")
        assert exported["notes"] == []
        editor_file = Path(__file__).parent.parent / "fixtures" / "presets" / "dsp408_editor.prs"
        upload = base64.b64encode(editor_file.read_bytes()).decode()
        loaded = request(ws, {"type": "preset.import", "req": 2, "data": upload})
        assert loaded == {
            "type": "result",
            "req": 2,
            "ok": True,
            "name": "FSMXLmGDLsEq",
            "notes": [],
        }
        receive_until(ws, "snapshot")  # the export's config read
        state = receive_until(ws, "snapshot")["state"]
        assert [o["name"] for o in state["outputs"][:4]] == ["Sub", "Kick", "Med", "High"]
        assert state["modified"] is True
        stored = request(
            ws, {"type": "preset.import", "req": 3, "data": upload, "slot": 6, "name": "Club"}
        )
        assert stored["ok"]
        assert stored["name"] == "Club"
        for req, message, error in [
            (4, {"data": 12}, "invalid"),
            (5, {"data": "not base64!"}, "invalid"),
            (6, {"data": base64.b64encode(b"x" * 20000).decode()}, "invalid"),
            (7, {"data": base64.b64encode(b"***DSP408V010***").decode()}, "invalid"),
            (8, {"data": upload, "slot": "1"}, "invalid"),
            (9, {"data": upload, "slot": 1, "name": 3}, "invalid"),
        ]:
            result = request(ws, {"type": "preset.import", "req": req, **message})
            assert result["error"] == error, (req, result)


def test_setup_apply(client: TestClient) -> None:
    login(client, "Op")
    outputs = [
        {"name": "Main", "used": True, "sources": [True, True, False, False]},
        *({"name": f"Out{n}", "used": False, "sources": [False] * 4} for n in range(2, 9)),
    ]
    plan = {"inputs": [{"name": n} for n in ("L", "R", "InC", "InD")], "outputs": outputs}
    with client.websocket_connect("/ws") as ws:
        receive_until(ws, "snapshot")
        applied = request(
            ws, {"type": "setup.apply", "req": 1, "plan": plan, "slot": 4, "name": "Wizard"}
        )
        assert applied == {"type": "result", "req": 1, "ok": True, "name": "Wizard", "notes": []}
        state = receive_until(ws, "snapshot")["state"]
        assert state["outputs"][0]["name"] == "Main"
        assert [i["mute"] for i in state["inputs"]] == [True] * 4
        for req, message in [
            (2, {"plan": {"inputs": []}, "name": "X"}),
            (3, {"plan": plan, "name": 3}),
            (4, {"plan": plan, "name": "X", "slot": "1"}),
            (5, {"plan": {**plan, "outputs": outputs[:2]}, "name": "X"}),
        ]:
            result = request(ws, {"type": "setup.apply", "req": req, **message})
            assert result["error"] == "invalid", (req, result)


def test_pings_are_answered_during_a_long_request(web_dir: Path) -> None:
    """A preset import (or a recall on a slow link) can last longer than the client's 12 s
    silence limit: the server keeps answering pings meanwhile, or the client drops the link."""
    app, device = make_app(web_dir)
    device.timing.store_s = 0.5
    with TestClient(app) as test_client:
        ctx: AppContext = app.state.ctx
        deadline = time.monotonic() + 5
        while ctx.session.status.value != "online" and time.monotonic() < deadline:
            time.sleep(0.02)
        login(test_client)
        with test_client.websocket_connect("/ws") as ws:
            receive_until(ws, "snapshot")
            editor_file = (
                Path(__file__).parent.parent / "fixtures" / "presets" / "dsp408_editor.prs"
            )
            upload = base64.b64encode(editor_file.read_bytes()).decode()
            ws.send_json({"type": "preset.import", "req": 1, "data": upload, "slot": 2})
            ws.send_json({"type": "ping", "req": 2})
            order = []
            while len(order) < 2:
                message = ws.receive_json()
                if message["type"] in ("pong", "result"):
                    order.append((message["type"], message["req"]))
            assert order == [("pong", 2), ("result", 1)]
            assert device.presets[2].preset_name == "FSMXLmGDLsEq"
