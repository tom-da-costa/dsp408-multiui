// Application state (Svelte 5 runes) and the WebSocket connection to the server.

import * as api from "./api";
import { channelColor } from "./colors";
import { setPath } from "./paths";
import type {
  Change,
  DeviceMessage,
  DeviceState,
  Hello,
  MasterMessage,
  LockMessage,
  Meters,
  ResultMessage,
  Settings,
} from "./types";

export interface Toast {
  id: number;
  text: string;
  kind: "error" | "info";
}

interface Pending {
  resolve: (result: ResultMessage) => void;
  timer: ReturnType<typeof setTimeout>;
}

const REQUEST_TIMEOUT_MS = 10_000;
// Preset recall (~3 s) and store (~7.5 s) on a DSP 408, plus re-reading the configuration
// (~50 requests: 23 s in all behind a link with 300 ms of latency, measured).
const SLOW_REQUEST_TIMEOUT_MS = 60_000;
const SLOW_REQUESTS = new Set(["preset.recall", "preset.store", "resync", "link.set"]);
const ACTIVITY_INTERVAL_MS = 10_000;
// Link to the server: a ping every few seconds; with nothing received for a while (not even the
// pong), the link is presumed dead (half-open: Wi-Fi lost, phone asleep) and is dropped at once
// rather than waiting for the browser's own timeout, which can take minutes.
const PING_INTERVAL_MS = 4_000;
const SILENCE_TIMEOUT_MS = 12_000;
const CONNECT_TIMEOUT_MS = 8_000;
const RETRY_MIN_MS = 500;
const RETRY_MAX_MS = 5_000;

class App {
  view = $state<"loading" | "login" | "app" | "shutdown">("loading");
  /** Who shut the server down (the "shutdown" view). */
  shutdownBy = $state("");
  me = $state<api.Me | null>(null);
  hello = $state<Hello | null>(null);
  device = $state<DeviceState | null>(null);
  status = $state<DeviceMessage | null>(null);
  /** Control: the client that alone may write, if any (the `lock` messages). */
  lock = $state<LockMessage | null>(null);
  /** performance.now() deadline of the control's idle release (null when free). */
  lockDeadline = $state<number | null>(null);
  /** Master role (the `master` messages). */
  master = $state<MasterMessage | null>(null);
  /** Why the login screen is shown, e.g. "Disconnected by Alice" (cleared on login). */
  loginNotice = $state("");
  /** Screen lock: this browser is read-only (the screen stays readable) until the access code
   * is typed (kept by the server on the session, so a reload stays locked). */
  screenLocked = $state(false);
  meters = $state.raw<Meters | null>(null);
  clients = $state<{ id: string; name: string }[]>([]);
  settings = $state<Settings | null>(null);
  connected = $state(false);
  /** Number of failed attempts since the link to the server was lost (0 while connected). */
  retries = $state(0);
  toasts = $state<Toast[]>([]);

  rev = 0;
  private ws: WebSocket | null = null;
  private nextReq = 1;
  private pending = new Map<number, Pending>();
  private retryMs = RETRY_MIN_MS;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private lastSeen = 0;
  private lastPing = 0;
  private toastId = 0;
  private lastActivity = 0;
  private stopped = false;
  private listening = false;

  // --- derived helpers ---------------------------------------------------------------------
  get lockedByOther(): boolean {
    return !!this.lock?.owner_id && this.lock.owner_id !== this.hello?.client_id;
  }

  get iAmMaster(): boolean {
    return !!this.master?.owner_id && this.master.owner_id === this.hello?.client_id;
  }

  get iOwnLock(): boolean {
    return !!this.lock?.owner_id && this.lock.owner_id === this.hello?.client_id;
  }

  /** Colour of a channel ("inputs.0" / "outputs.3"); linked channels share their group's. */
  color(path: string): string {
    const [side, n] = path.split(".");
    const channels = side === "outputs" ? this.device?.outputs : this.device?.inputs;
    return channelColor(path, channels?.[Number(n)]?.linked);
  }

  /** True when this client cannot change anything: no server, no DSP, Control or screen lock. */
  get readOnly(): boolean {
    return (
      !this.connected || this.lockedByOther || this.screenLocked || this.status?.status !== "online"
    );
  }

  /** True when the parameter kind has been verified on a real DSP 408. */
  verified(kind: string): boolean {
    return this.hello?.verified_kinds.includes(kind) ?? false;
  }

  /** True when this client may change parameters of this kind right now. */
  editable(kind: string): boolean {
    return !this.readOnly && (this.verified(kind) || !!this.hello?.experimental);
  }

  // --- lifecycle -------------------------------------------------------------------------------
  async start(): Promise<void> {
    const me = await api.currentSession().catch(() => null);
    if (me) {
      this.me = me;
      this.view = "app";
      this.connect();
    } else {
      this.view = "login";
    }
  }

  async login(pin: string, name: string): Promise<void> {
    this.me = await api.login(pin, name);
    this.loginNotice = "";
    this.view = "app";
    this.stopped = false;
    this.connect();
  }

  async logout(): Promise<void> {
    this.stopped = true;
    await api.logout();
    this.drop();
    this.reset();
    this.view = "login";
  }

  private reset(): void {
    this.hello = null;
    this.device = null;
    this.status = null;
    this.lock = null;
    this.master = null;
    this.screenLocked = false;
    this.meters = null;
    this.connected = false;
    this.retries = 0;
    this.rev = 0;
  }

  private connect(): void {
    this.listen();
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws`);
    this.ws = ws;
    this.lastSeen = Date.now();
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.connected = true;
      this.retries = 0;
      this.retryMs = RETRY_MIN_MS;
      this.lastSeen = Date.now();
    };
    ws.onmessage = (event) => {
      if (this.ws !== ws) return;
      this.lastSeen = Date.now();
      this.handle(JSON.parse(event.data as string));
    };
    ws.onclose = (event) => {
      if (this.ws !== ws) return;
      if (event.code === 4401) {
        this.loginNotice = event.reason;
        this.drop();
        this.reset();
        this.view = "login";
        return;
      }
      this.lost();
    };
    if (this.watchdog === null) this.watchdog = setInterval(() => this.check(), 1_000);
  }

  /** Forget the current socket (closing it if still open) and fail the pending requests. */
  private drop(): void {
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = null;
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) ws.close();
    }
    if (this.watchdog !== null) clearInterval(this.watchdog);
    this.watchdog = null;
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.connected = false;
    this.meters = null; // stale levels must not stay on screen
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.resolve({ type: "result", req: null, ok: false, error: "disconnected" });
    }
    this.pending.clear();
  }

  /** The link is gone: drop it and try again after a growing, jittered delay. */
  private lost(): void {
    this.drop();
    if (this.stopped) return;
    this.retries += 1;
    // A server restarted behind a proxy may refuse the socket without the 4401 code: ask once
    // in a while whether the session is still known, and show the login if not.
    if (this.retries % 3 === 0) void this.checkSession();
    // Jitter so that every client of a restarted server does not come back at the same instant.
    const delay = this.retryMs * (0.75 + Math.random() * 0.5);
    this.retryMs = Math.min(this.retryMs * 2, RETRY_MAX_MS);
    this.retryTimer = setTimeout(() => this.connect(), delay);
  }

  private async checkSession(): Promise<void> {
    if ((await api.sessionState()) !== "expired" || this.connected || this.stopped) return;
    this.drop();
    this.reset();
    this.view = "login";
  }

  /** Reconnect now (the "Retry now" button, the page coming back, the network coming back). */
  reconnectNow(): void {
    if (this.stopped || this.view !== "app" || this.connected) return;
    this.drop();
    this.retryMs = RETRY_MIN_MS;
    this.connect();
  }

  /** Start over with a fresh snapshot (a missed update). */
  private reconnect(): void {
    this.drop();
    if (!this.stopped) this.connect();
  }

  /** Watchdog (every second): heartbeat while open, timeouts while connecting or silent. */
  private check(): void {
    const ws = this.ws;
    if (!ws) return;
    const now = Date.now();
    if (ws.readyState === WebSocket.CONNECTING) {
      if (now - this.lastSeen > CONNECT_TIMEOUT_MS) this.lost();
      return;
    }
    if (ws.readyState !== WebSocket.OPEN) return;
    // A hidden tab's timers are throttled (down to once a minute): do not judge the silence
    // there; the check resumes when the page is shown again (see listen()).
    if (document.hidden) return;
    if (now - this.lastSeen > SILENCE_TIMEOUT_MS) {
      this.lost();
      return;
    }
    if (now - this.lastPing >= PING_INTERVAL_MS) {
      this.lastPing = now;
      this.send({ type: "ping" });
    }
  }

  /** Page shown again or network back: reconnect at once, or check the link that looks open. */
  private listen(): void {
    if (this.listening || typeof window === "undefined") return;
    this.listening = true;
    const wake = () => {
      if (document.hidden) return;
      if (!this.connected) {
        this.reconnectNow();
      } else if (this.ws?.readyState === WebSocket.OPEN) {
        // It may be dead after a sleep: ping now and give the answer a few seconds.
        this.lastPing = Date.now();
        this.send({ type: "ping" });
        this.lastSeen = Math.max(this.lastSeen, Date.now() - SILENCE_TIMEOUT_MS + 5_000);
      }
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", wake);
    window.addEventListener("pageshow", wake);
  }

  // --- incoming --------------------------------------------------------------------------------
  private handle(msg: { type: string; [key: string]: unknown }): void {
    switch (msg.type) {
      case "hello":
        this.hello = msg as unknown as Hello;
        this.settings = this.hello.settings;
        this.screenLocked = this.hello.screen_locked;
        break;
      case "snapshot":
        this.device = msg.state as DeviceState;
        this.rev = msg.rev as number;
        break;
      case "patch": {
        const rev = msg.rev as number;
        if (!this.device || rev !== this.rev + 1) {
          this.reconnect(); // missed an update: start over with a fresh snapshot
          return;
        }
        for (const change of msg.changes as Change[]) setPath(this.device, change.path, change.value);
        this.rev = rev;
        break;
      }
      case "meters":
        this.meters = msg as unknown as Meters;
        break;
      case "device":
        this.status = msg as unknown as DeviceMessage;
        if (this.status.status !== "online") this.meters = null; // no stale levels
        // "DSP206" -> "DSP 206": the tab / home-screen title follows the detected model
        if (this.status.model) document.title = this.status.model.replace(/^DSP\s*/, "DSP ");
        break;
      case "lock":
        this.lock = msg as unknown as LockMessage;
        this.lockDeadline =
          this.lock.idle_remaining_s === null
            ? null
            : performance.now() + this.lock.idle_remaining_s * 1000;
        break;
      case "shutdown":
        // The server is going away for good: stop reconnecting.
        this.shutdownBy = String(msg.by ?? "");
        this.stopped = true;
        this.drop();
        this.view = "shutdown";
        break;
      case "master":
        this.master = msg as unknown as MasterMessage;
        break;
      case "screen_lock":
        this.screenLocked = msg.locked as boolean;
        break;
      case "clients":
        this.clients = msg.clients as { id: string; name: string }[];
        break;
      case "pong":
        break; // only proves the link is alive (lastSeen)
      case "settings":
        this.settings = msg as unknown as Settings;
        break;
      case "result": {
        const result = msg as unknown as ResultMessage;
        const pending = result.req === null ? undefined : this.pending.get(result.req);
        if (pending) {
          clearTimeout(pending.timer);
          this.pending.delete(result.req as number);
          pending.resolve(result);
        }
        break;
      }
    }
  }

  // --- outgoing --------------------------------------------------------------------------------
  private send(message: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  request(message: { type: string; [key: string]: unknown }): Promise<ResultMessage> {
    const req = this.nextReq++;
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return Promise.resolve({
        type: "result",
        req,
        ok: false,
        error: "disconnected",
        message: "not connected to the server",
      });
    }
    return new Promise((resolve) => {
      const timeout = SLOW_REQUESTS.has(message.type) ? SLOW_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS;
      const timer = setTimeout(() => {
        this.pending.delete(req);
        resolve({ type: "result", req, ok: false, error: "timeout", message: "no answer" });
      }, timeout);
      this.pending.set(req, { resolve, timer });
      this.send({ ...message, req });
    });
  }

  /** Send a request; show a toast if it fails. Returns true on success. */
  async run(message: { type: string; [key: string]: unknown }): Promise<boolean> {
    this.activity(true);
    const result = await this.request(message);
    if (!result.ok) {
      this.toast(
        result.error === "disconnected"
          ? "Connection to the server lost: check that the change was applied"
          : (result.message ?? result.error ?? "error"),
        "error",
      );
    }
    return result.ok;
  }

  set(path: string, value: unknown): Promise<boolean> {
    return this.run({ type: "set", path, value });
  }

  lockScreen(): Promise<boolean> {
    return this.run({ type: "screen.lock" });
  }

  /** Unlock the screen with the access code; returns the error message, or null on success. */
  async unlockScreen(pin: string): Promise<string | null> {
    const result = await this.request({ type: "screen.unlock", pin });
    return result.ok ? null : (result.message ?? result.error ?? "error");
  }

  /** Report a user interaction (throttled). Resets the local lock countdown when we own it. */
  activity(force = false): void {
    if (this.screenLocked) return; // taps on a locked screen are not activity
    const now = Date.now();
    if (this.iOwnLock && this.lock) {
      this.lockDeadline = performance.now() + this.lock.idle_timeout_s * 1000;
    }
    if (!force && now - this.lastActivity < ACTIVITY_INTERVAL_MS) return;
    this.lastActivity = now;
    if (!force) this.send({ type: "activity" });
  }

  toast(text: string, kind: Toast["kind"] = "info"): void {
    const id = ++this.toastId;
    this.toasts.push({ id, text, kind });
    setTimeout(() => {
      this.toasts = this.toasts.filter((t) => t.id !== id);
    }, 4000);
  }
}

export const app = new App();
