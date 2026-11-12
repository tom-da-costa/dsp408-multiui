// How the meters are drawn (Settings › Meters, remembered in this browser): the bottom and the
// top of every meter scale, in dBu, and the segment size (an LED-style ladder of 1, 2, 5 or
// 10 dB, or a continuous bar). Display only: the levels, CLIP (+12 dBu) and the colour zones
// stay in absolute dBu.

const STORAGE_KEY = "dsp408.meterRange";

export const METER_MIN_DEFAULT = -40;
export const METER_MAX_DEFAULT = 20; // full scale of the DSP
/** Ranges offered in Settings; they do not overlap, so the bottom is always below the top. */
export const METER_MIN_RANGE = [-90, -20] as const;
export const METER_MAX_RANGE = [0, 40] as const;
export const METER_RANGE_STEP = 10; // the graduations are every 10 dB too
/** Segment sizes offered in Settings, in dB; 0 = a continuous bar. */
export const METER_SEGMENTS = [0, 1, 2, 5, 10] as const;
/** Colour of the gaps between segments: the meters' background. */
const GAP_COLOR = "#0b0c0f";

/** Within its range and on the 10 dB grid. */
function clamp(db: number, [lo, hi]: readonly [number, number]): number {
  const onGrid = Math.round(db / METER_RANGE_STEP) * METER_RANGE_STEP;
  return Math.min(hi, Math.max(lo, onGrid));
}

function isSegment(value: unknown): value is number {
  return METER_SEGMENTS.some((step) => step === value);
}

function load(): { min: number; max: number; segment: number } {
  const fallback = { min: METER_MIN_DEFAULT, max: METER_MAX_DEFAULT, segment: 0 };
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as {
      min?: unknown;
      max?: unknown;
      segment?: unknown;
    } | null;
    return {
      min: typeof saved?.min === "number" ? clamp(saved.min, METER_MIN_RANGE) : fallback.min,
      max: typeof saved?.max === "number" ? clamp(saved.max, METER_MAX_RANGE) : fallback.max,
      segment: isSegment(saved?.segment) ? saved.segment : fallback.segment,
    };
  } catch {
    return fallback;
  }
}

class MeterRange {
  min = $state(METER_MIN_DEFAULT);
  max = $state(METER_MAX_DEFAULT);
  /** Segment size in dB; 0 = continuous. */
  segment = $state(0);

  constructor() {
    const saved = load();
    this.min = saved.min;
    this.max = saved.max;
    this.segment = saved.segment;
  }

  setSegment(step: number): void {
    if (!isSegment(step)) return;
    this.segment = step;
    this.save();
  }

  setMin(db: number): void {
    this.min = clamp(db, METER_MIN_RANGE);
    this.save();
  }

  setMax(db: number): void {
    this.max = clamp(db, METER_MAX_RANGE);
    this.save();
  }

  reset(): void {
    this.min = METER_MIN_DEFAULT;
    this.max = METER_MAX_DEFAULT;
    this.save();
  }

  get isDefault(): boolean {
    return this.min === METER_MIN_DEFAULT && this.max === METER_MAX_DEFAULT;
  }

  private save(): void {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ min: this.min, max: this.max, segment: this.segment }),
      );
    } catch {
      // not persisted: fine
    }
  }
}

export const meterRange = new MeterRange();

/** Graduations every `every` dB from `min` to `max` (both included when on the grid). */
export function meterTicks(min: number, max: number, every = 10): number[] {
  const ticks: number[] = [];
  for (let db = Math.floor(max / every) * every; db >= min; db -= every) ticks.push(db);
  return ticks;
}

// --- segments ---------------------------------------------------------------------------------
// Segments start at the bottom of the scale (a multiple of 10 dB, which every size divides).

/** The level drawn: up to the top of the segment it reaches (unchanged when continuous). */
export function segmentLevel(db: number, bottom: number, step: number): number {
  if (!step) return db;
  return bottom + Math.ceil((db - bottom) / step - 1e-9) * step;
}

/** Where a colour zone starting above `db` begins: at the bottom of the first segment whose top
 * passes it, so that each segment has one colour, the one of its top (as on an LED meter). */
export function segmentZoneStart(db: number, bottom: number, step: number): number {
  if (!step) return db;
  return bottom + Math.floor((db - bottom) / step + 1e-9) * step;
}

/** Thin gaps between the segments, drawn over the bar; null when continuous. */
export function segmentGaps(
  direction: "to top" | "to right",
  bottom: number,
  top: number,
  step: number,
): string | null {
  if (!step || top <= bottom) return null;
  const size = ((step / (top - bottom)) * 100).toFixed(4);
  return `repeating-linear-gradient(${direction}, transparent 0 calc(${size}% - 1px), ${GAP_COLOR} calc(${size}% - 1px) ${size}%)`;
}
