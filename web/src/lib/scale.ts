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
  return hz >= 1000 ? `${(hz / 1000).toFixed(hz >= 10000 ? 1 : 2)}k` : `${Math.round(hz)}`;
}

/** Meter position for a level relative to the meter range. */
export function meterPos(db: number | null, floor: number, top = 12): number {
  if (db === null || db <= floor) return 0;
  return Math.min(1, (db - floor) / (top - floor));
}
