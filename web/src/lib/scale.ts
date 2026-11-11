// Fader and meter scales: piecewise-linear dB <-> position (0 = bottom, 1 = top).

export const GAIN_MIN = -60;
export const GAIN_MAX = 12;

const POINTS: [number, number][] = [
  [0, -60],
  [0.2, -40],
  [0.45, -20],
  [0.75, 0],
  [1, 12],
];

export function dbToPos(db: number): number {
  if (db <= GAIN_MIN) return 0;
  if (db >= GAIN_MAX) return 1;
  for (let i = 1; i < POINTS.length; i++) {
    const [p1, d1] = POINTS[i]!;
    const [p0, d0] = POINTS[i - 1]!;
    if (db <= d1) return p0 + ((db - d0) / (d1 - d0)) * (p1 - p0);
  }
  return 1;
}

export function posToDb(pos: number): number {
  if (pos <= 0) return GAIN_MIN;
  if (pos >= 1) return GAIN_MAX;
  for (let i = 1; i < POINTS.length; i++) {
    const [p1, d1] = POINTS[i]!;
    const [p0, d0] = POINTS[i - 1]!;
    if (pos <= p1) return d0 + ((pos - p0) / (p1 - p0)) * (d1 - d0);
  }
  return GAIN_MAX;
}

/** Device resolution: 0.5 dB below -20 dB, 0.1 dB above. */
export function quantizeGain(db: number): number {
  const clamped = Math.min(GAIN_MAX, Math.max(GAIN_MIN, db));
  return clamped < -20 ? Math.round(clamped * 2) / 2 : Math.round(clamped * 10) / 10;
}

export function formatDb(db: number | null | undefined, digits = 1): string {
  if (db === null || db === undefined || !Number.isFinite(db)) return "—";
  if (db <= GAIN_MIN) return "-∞";
  return `${db > 0 ? "+" : ""}${db.toFixed(digits)}`;
}

export function formatHz(hz: number): string {
  // Enough digits that one device step (about 2.3 %) always shows.
  if (hz >= 1000) return `${(hz / 1000).toFixed(hz >= 10000 ? 1 : 2)}k`;
  return hz >= 100 ? `${Math.round(hz)}` : hz.toFixed(1);
}

/** Meter position for a level relative to the meter range (linear in dB, for level bars). */
export function meterPos(db: number | null, floor: number, top = 20): number {
  if (db === null || db <= floor) return 0;
  return Math.min(1, (db - floor) / (top - floor));
}

// Vertical meters: levels in dBu (like the dynamics thresholds), full scale (CLIP) = +20 dBu.
const METER_POINTS: [number, number][] = [
  [0, -60],
  [0.2, -40],
  [0.45, -20],
  [0.7, 0],
  [1, 20],
];

/** Meter colour zones (dBu): green up to 0, yellow up to +6, orange up to +12, red above. */
export const METER_ZONES = { yellow: 0, orange: 6, red: 12 } as const;
export const METER_COLORS = {
  green: "#2bbf7f",
  yellow: "#ffd23f",
  orange: "#ff8c1a",
  red: "#ff4d5e",
} as const;

/** Compressor and limiter colours: those of the Live view's CMP and LIM indicators. */
export const COMP_COLOR = METER_COLORS.orange;
export const LIMIT_COLOR = "#d9480f"; // dark orange (CMP is orange, CLIP red)

/** Opacity of the dimmed zone colours drawn behind the level. */
export const METER_BACKGROUND_OPACITY = 0.2;

/** Fill of a meter's level: the limiter's colour when it acts (it prevails over the
 * compressor), then the compressor's, else the colour zones. CLIP (all red) is handled by the
 * meters themselves and prevails over everything. */
export function meterFill(zones: string, limit?: boolean | null, comp?: boolean | null): string {
  if (limit) return LIMIT_COLOR;
  if (comp) return COMP_COLOR;
  return zones;
}

/** Hard-stop gradient of the meter zones, for a bar whose positions come from `pos`. */
export function meterGradient(direction: string, pos: (db: number) => number): string {
  const [y, o, r] = [METER_ZONES.yellow, METER_ZONES.orange, METER_ZONES.red].map(
    (db) => `${(pos(db) * 100).toFixed(2)}%`,
  );
  const c = METER_COLORS;
  return `linear-gradient(${direction}, ${c.green} 0 ${y}, ${c.yellow} ${y} ${o}, ${c.orange} ${o} ${r}, ${c.red} ${r} 100%)`;
}

/** Position of a level on a vertical meter (0 = bottom, 1 = full scale). */
export function meterDbToPos(db: number): number {
  const [first, last] = [METER_POINTS[0]!, METER_POINTS[METER_POINTS.length - 1]!];
  if (db <= first[1]) return 0;
  if (db >= last[1]) return 1;
  for (let i = 1; i < METER_POINTS.length; i++) {
    const [p1, d1] = METER_POINTS[i]!;
    const [p0, d0] = METER_POINTS[i - 1]!;
    if (db <= d1) return p0 + ((db - d0) / (d1 - d0)) * (p1 - p0);
  }
  return 1;
}

// --- one device step (the − / + buttons) ----------------------------------------------------------

export type Direction = 1 | -1;

/** Channel gain: 0.5 dB steps below -20 dB, 0.1 dB steps from -20 dB up (GAIN_MIN..GAIN_MAX). */
export function gainStep(db: number, dir: Direction): number {
  const next = dir > 0 ? db + (db < -20 ? 0.5 : 0.1) : db - (db > -20 ? 0.1 : 0.5);
  return Number(Math.min(GAIN_MAX, Math.max(GAIN_MIN, next)).toFixed(1));
}

/** A value stored as a raw index 0..steps on a log scale from min to max (Hz, Q). */
export function logIndexStep(
  value: number,
  min: number,
  max: number,
  steps: number,
  dir: Direction,
): number {
  const index = Math.round((Math.log(value / min) / Math.log(max / min)) * steps);
  const next = Math.min(steps, Math.max(0, index + dir));
  return min * (max / min) ** (next / steps);
}

/** Nearest value a raw index 0..steps on a log scale from min to max can hold (clamped). */
export function logSnap(value: number, min: number, max: number, steps: number): number {
  const clamped = Math.min(max, Math.max(min, value));
  const index = Math.round((Math.log(clamped / min) / Math.log(max / min)) * steps);
  return min * (max / min) ** (index / steps);
}

/** A delay stored in samples: one sample more or less. */
export function sampleStep(ms: number, sampleRateHz: number, dir: Direction): number {
  const samples = Math.max(0, Math.round((ms * sampleRateHz) / 1000) + dir);
  return (samples * 1000) / sampleRateHz;
}

// --- generic control scales (sliders) ------------------------------------------------------------

/** How a slider maps a value to its position: linear, logarithmic, or square root (fine near 0). */
export type Scale = "lin" | "log" | "sqrt";

export function toPos(value: number, min: number, max: number, scale: Scale = "lin"): number {
  let pos: number;
  if (scale === "log") pos = Math.log(value / min) / Math.log(max / min);
  else if (scale === "sqrt") pos = Math.sqrt(Math.max(0, value - min) / (max - min));
  else pos = (value - min) / (max - min);
  return Number.isFinite(pos) ? Math.min(1, Math.max(0, pos)) : 0;
}

export function fromPos(pos: number, min: number, max: number, scale: Scale = "lin"): number {
  const p = Math.min(1, Math.max(0, pos));
  if (scale === "log") return min * (max / min) ** p;
  if (scale === "sqrt") return min + p * p * (max - min);
  return min + p * (max - min);
}

/** Round to a multiple of `resolution` (if given) and clamp to [min, max]. */
export function snap(value: number, min: number, max: number, resolution?: number): number {
  let v = Math.min(max, Math.max(min, value));
  if (resolution) v = Math.min(max, Math.max(min, Math.round(v / resolution) * resolution));
  return Number(v.toFixed(6));
}

/** Parse a typed number: accepts a comma as decimal separator and a "k" suffix (1.5k = 1500). */
export function parseNumber(text: string): number | null {
  const match = /^\s*([+-]?\d*[.,]?\d+)\s*(k)?\s*$/i.exec(text);
  if (!match) return null;
  const value = Number(match[1]!.replace(",", ".")) * (match[2] ? 1000 : 1);
  return Number.isFinite(value) ? value : null;
}

export function formatQ(q: number): string {
  return q >= 10 ? q.toFixed(1) : q.toFixed(2);
}

/** ISO 1/3-octave centre frequencies of the 31-band graphic EQ. */
export const GEQ_FREQS = [
  20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600,
  2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
];

export function formatGeqFreq(hz: number): string {
  if (hz >= 1000) return `${Number((hz / 1000).toFixed(2))}k`;
  return `${hz}`;
}
