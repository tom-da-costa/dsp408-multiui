// Mirrors src/dsp408_multiui/state/models.py and the WebSocket messages of docs/SPEC.md §5.

export interface PeqBand {
  gain_db: number;
  freq_hz: number;
  q: number;
  type: number;
  bypass: boolean;
}

export interface Filter {
  freq_hz: number;
  slope: number;
  enabled: boolean;
}

export interface Crossover {
  hpf: Filter;
  lpf: Filter;
}

export interface Gate {
  attack_ms: number;
  release_ms: number;
  hold_ms: number;
  threshold_db: number;
}

export interface Compressor {
  ratio: number;
  attack_ms: number;
  release_ms: number;
  knee_db: number;
  threshold_db: number;
}

export interface Limiter {
  attack_ms: number;
  release_ms: number;
  threshold_db: number;
}

export interface Channel {
  index: number;
  name: string;
  gain_db: number;
  mute: boolean;
  phase: boolean;
  peq: PeqBand[];
  peq_bypass: boolean;
  crossover: Crossover;
  delay_ms: number;
  /** Other members of the link group (indices among inputs or outputs). */
  linked: number[];
}

export interface InputChannel extends Channel {
  geq: number[];
  gate: Gate;
}

export interface OutputChannel extends Channel {
  matrix: boolean[];
  crosspoints_db: number[];
  compressor: Compressor;
  limiter: Limiter;
}

export interface Preset {
  slot: number;
  name: string;
}

export interface DeviceState {
  info: { identity: string; model: string; firmware: string };
  presets: Preset[];
  active_slot: number;
  preset_name: string;
  inputs: InputChannel[];
  outputs: OutputChannel[];
}

export interface Profile {
  input_count: number;
  output_count: number;
  preset_count: number;
  peq_types: string[];
  slopes: string[];
  ratios: string[];
  freq_min_hz: number;
  freq_max_hz: number;
  freq_steps: number;
  q_min: number;
  q_max: number;
  q_steps: number;
  delay_sample_rate_hz: number;
  delay_max_ms: number;
  meter_floor_db: number;
  meter_clip_db: number;
}

/** Control ranges sent by the server (it still clamps every value it receives). */
export interface Limits {
  gain_db: [number, number];
  eq_gain_db: [number, number];
  attack_ms: [number, number];
  release_ms: [number, number];
  gate_release_ms: [number, number];
  hold_ms: [number, number];
  threshold_db: [number, number];
  gate_threshold_db: [number, number];
  knee_db: [number, number];
  channel_name_length: number;
  preset_name_length: number;
  speed_of_sound_m_s: number;
}

export interface Hello {
  type: "hello";
  client_id: string;
  name: string;
  server_version: string;
  demo: boolean;
  experimental: boolean;
  verified_kinds: string[];
  profile: Profile;
  limits: Limits;
  settings: Settings;
}

export interface Settings {
  meter_rate_hz: number;
  lock_idle_timeout_s: number;
}

export interface Meters {
  seq: number;
  levels: (number | null)[] | null;
  clip?: boolean[];
  limit?: boolean[] | null;
  comp?: boolean[] | null;
  input_clip?: boolean | null;
}

export type DeviceStatus = "stopped" | "connecting" | "initialising" | "online" | "offline";

export interface DeviceMessage {
  status: DeviceStatus;
  error: string | null;
  model: string;
  firmware: string;
  identity: string;
}

export interface LockMessage {
  owner_id: string | null;
  owner_name: string | null;
  idle_remaining_s: number | null;
  idle_timeout_s: number;
}

export interface Change {
  path: string;
  value: unknown;
}

export interface ResultMessage {
  type: "result";
  req: number | null;
  ok: boolean;
  error?: string;
  message?: string;
}
