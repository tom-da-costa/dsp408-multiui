"""Server: auth, lock, WebSocket fan-out, against the embedded simulator."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from dsp408_multiui.protocol.profile import DEFAULT_PROFILE
from dsp408_multiui.server.app import AppContext, create_app
from dsp408_multiui.server.auth import AuthManager, LoginError, RateLimitedError, clean_name
from dsp408_multiui.server.lock import LockManager
from dsp408_multiui.server.settings import ServerConfig
from dsp408_multiui.simulator import Faults, SimulatedDevice, apply_scenario
from dsp408_multiui.state import registry

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
    assert auth.rename(session.token, "Stage") is session
    assert session.name == "Stage"
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
    lock.rename("b", "Bobby")
    assert lock.state().owner_name == "Bobby"
    assert lock.release("b")
    assert changes == ["a", None, "b", "b", None]
    with pytest.raises(ValueError, match="idle_timeout"):
        LockManager(0)


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
    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect("/ws") as ws:
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
            ({"type": "rename", "req": 11, "name": 3}, "invalid"),
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


def test_presets_settings_rename_resync(client: TestClient) -> None:
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
        assert request(ws, {"type": "rename", "req": 4, "name": "Monitor desk"})["ok"]
        assert receive_until(ws, "self")["name"] == "Monitor desk"
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
