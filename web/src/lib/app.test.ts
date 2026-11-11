// The link to the server: heartbeat, dead-link detection, reconnection, no writes while down.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class FakeSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static all: FakeSocket[] = [];
  readyState = FakeSocket.CONNECTING;
  sent: { type: string; [key: string]: unknown }[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = FakeSocket.CLOSED;
  }
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
  receive(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  static last(): FakeSocket {
    return FakeSocket.all[FakeSocket.all.length - 1]!;
  }
}

const listeners = new Map<string, () => void>();
const fakeDocument = {
  hidden: false,
  title: "",
  addEventListener: (name: string, fn: () => void) => listeners.set(name, fn),
};

async function freshApp() {
  vi.resetModules();
  const { app } = await import("./app.svelte");
  app.view = "app";
  app.reconnectNow();
  return app;
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeSocket.all = [];
  listeners.clear();
  fakeDocument.hidden = false;
  vi.stubGlobal("WebSocket", FakeSocket);
  vi.stubGlobal("location", { protocol: "http:", host: "dsp.test" });
  vi.stubGlobal("document", fakeDocument);
  vi.stubGlobal("window", {
    addEventListener: (name: string, fn: () => void) => listeners.set(name, fn),
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("link to the server", () => {
  it("is read-only and refuses requests while not connected", async () => {
    const app = await freshApp();
    expect(app.readOnly).toBe(true);
    const result = await app.request({ type: "set", path: "outputs.0.gain_db", value: 0 });
    expect(result).toMatchObject({ ok: false, error: "disconnected" });
    expect(FakeSocket.last().sent).toEqual([]);
  });

  it("sends a heartbeat while open", async () => {
    const app = await freshApp();
    const ws = FakeSocket.last();
    ws.open();
    expect(app.connected).toBe(true);
    vi.advanceTimersByTime(4_000);
    ws.receive({ type: "pong", req: null });
    vi.advanceTimersByTime(4_000);
    expect(ws.sent.filter((m) => m.type === "ping").length).toBeGreaterThanOrEqual(2);
    expect(app.connected).toBe(true);
  });

  it("drops a silent (half-open) link and reconnects", async () => {
    const app = await freshApp();
    const ws = FakeSocket.last();
    ws.open();
    vi.advanceTimersByTime(5_000);
    const pending = app.request({ type: "set", path: "outputs.0.gain_db", value: 0 });
    vi.advanceTimersByTime(8_000);
    expect(app.connected).toBe(false);
    expect(app.retries).toBe(1);
    expect(await pending).toMatchObject({ ok: false, error: "disconnected" });
    vi.advanceTimersByTime(1_000); // first retry after ~0.5 s (jittered)
    expect(FakeSocket.all.length).toBe(2);
    FakeSocket.last().open();
    expect(app.connected).toBe(true);
    expect(app.retries).toBe(0);
  });

  it("gives up on a connection attempt that hangs", async () => {
    await freshApp();
    vi.advanceTimersByTime(9_000);
    expect(FakeSocket.all[0]!.readyState).toBe(FakeSocket.CLOSED);
    vi.advanceTimersByTime(1_000);
    expect(FakeSocket.all.length).toBe(2);
  });

  it("does not judge the silence of a hidden tab, checks it when shown again", async () => {
    const app = await freshApp();
    const ws = FakeSocket.last();
    ws.open();
    fakeDocument.hidden = true;
    vi.advanceTimersByTime(60_000);
    expect(app.connected).toBe(true);
    fakeDocument.hidden = false;
    listeners.get("visibilitychange")?.();
    expect(ws.sent.at(-1)?.type).toBe("ping");
    vi.advanceTimersByTime(6_000); // no answer within ~5 s: dropped
    expect(app.connected).toBe(false);
  });

  it("reconnects at once when the network comes back", async () => {
    const app = await freshApp();
    FakeSocket.last().onclose?.({ code: 1006 });
    expect(app.connected).toBe(false);
    const before = FakeSocket.all.length;
    listeners.get("online")?.();
    expect(FakeSocket.all.length).toBe(before + 1);
  });

  it("clears the meters when the DSP goes offline", async () => {
    const app = await freshApp();
    const ws = FakeSocket.last();
    ws.open();
    ws.receive({ type: "meters", seq: 1, levels: [-10] });
    expect(app.meters).not.toBeNull();
    ws.receive({ type: "device", status: "offline", error: "timed out", model: "DSP408" });
    expect(app.meters).toBeNull();
  });
});
