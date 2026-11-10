// Application state (Svelte 5 runes) and the WebSocket connection to the server.

import * as api from "./api";
import { channelColor } from "./colors";
import { setPath } from "./paths";
import type {
  Change,
  DeviceMessage,
  DeviceState,
  Hello,
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
// Preset recall (~3 s) and store (~7.5 s) on a DSP 408, plus re-reading the configuration.
const SLOW_REQUEST_TIMEOUT_MS = 30_000;
const SLOW_REQUESTS = new Set(["preset.recall", "preset.store", "resync", "link.set"]);
const ACTIVITY_INTERVAL_MS = 10_000;

class App {
  view = $state<"loading" | "login" | "app">("loading");
  me = $state<api.Me | null>(null);
  hello = $state<Hello | null>(null);
  device = $state<DeviceState | null>(null);
  status = $state<DeviceMessage | null>(null);
  lock = $state<LockMessage | null>(null);
  /** performance.now() deadline of the lock's idle release (null when free). */
  lockDeadline = $state<number | null>(null);
  meters = $state.raw<Meters | null>(null);
  clients = $state<{ id: string; name: string }[]>([]);
  settings = $state<Settings | null>(null);
  connected = $state(false);
  toasts = $state<Toast[]>([]);

  rev = 0;
  private ws: WebSocket | null = null;
  private nextReq = 1;
  private pending = new Map<number, Pending>();
  private retryMs = 500;
  private toastId = 0;
  private lastActivity = 0;
  private stopped = false;

  // --- derived helpers ---------------------------------------------------------------------
  get lockedByOther(): boolean {
    return !!this.lock?.owner_id && this.lock.owner_id !== this.hello?.client_id;
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

  get readOnly(): boolean {
    return this.lockedByOther || this.status?.status !== "online";
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
    this.view = "app";
    this.stopped = false;
    this.connect();
  }

  async logout(): Promise<void> {
    this.stopped = true;
    await api.logout();
    this.ws?.close();
    this.reset();
    this.view = "login";
  }

  private reset(): void {
    this.hello = null;
    this.device = null;
    this.status = null;
    this.lock = null;
    this.meters = null;
    this.connected = false;
    this.rev = 0;
  }

  private connect(): void {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws`);
    this.ws = ws;
    ws.onopen = () => {
      this.connected = true;
      this.retryMs = 500;
    };
    ws.onmessage = (event) => this.handle(JSON.parse(event.data as string));
    ws.onclose = (event) => {
      if (this.ws !== ws) return;
      this.connected = false;
      for (const [, p] of this.pending) {
        clearTimeout(p.timer);
        p.resolve({ type: "result", req: null, ok: false, error: "disconnected" });
      }
      this.pending.clear();
      if (event.code === 4401) {
        this.reset();
        this.view = "login";
        return;
      }
      if (!this.stopped) {
        setTimeout(() => this.connect(), this.retryMs);
        this.retryMs = Math.min(this.retryMs * 2, 5000);
      }
    };
  }

  private reconnect(): void {
    this.ws?.close();
  }

  // --- incoming --------------------------------------------------------------------------------
  private handle(msg: { type: string; [key: string]: unknown }): void {
    switch (msg.type) {
      case "hello":
        this.hello = msg as unknown as Hello;
        this.settings = this.hello.settings;
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
      case "clients":
        this.clients = msg.clients as { id: string; name: string }[];
        break;
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
    if (!result.ok && result.error !== "disconnected") {
      this.toast(result.message ?? result.error ?? "error", "error");
    }
    return result.ok;
  }

  set(path: string, value: unknown): Promise<boolean> {
    return this.run({ type: "set", path, value });
  }

  /** Report a user interaction (throttled). Resets the local lock countdown when we own it. */
  activity(force = false): void {
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
