// Displayed range of the meters (Settings › Meters, remembered in this browser): the bottom and
// the top of every meter scale, in dBu. Display only: the levels, CLIP (+12 dBu) and the colour
// zones stay in absolute dBu whatever range is shown.

const STORAGE_KEY = "dsp408.meterRange";

export const METER_MIN_DEFAULT = -60;
export const METER_MAX_DEFAULT = 20; // full scale of the DSP
/** Ranges offered in Settings; they do not overlap, so the bottom is always below the top. */
export const METER_MIN_RANGE = [-90, -20] as const;
export const METER_MAX_RANGE = [0, 40] as const;
export const METER_RANGE_STEP = 10; // the graduations are every 10 dB too

/** Within its range and on the 10 dB grid. */
function clamp(db: number, [lo, hi]: readonly [number, number]): number {
  const onGrid = Math.round(db / METER_RANGE_STEP) * METER_RANGE_STEP;
  return Math.min(hi, Math.max(lo, onGrid));
}

function load(): { min: number; max: number } {
  const fallback = { min: METER_MIN_DEFAULT, max: METER_MAX_DEFAULT };
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as {
      min?: unknown;
      max?: unknown;
    } | null;
    return {
      min: typeof saved?.min === "number" ? clamp(saved.min, METER_MIN_RANGE) : fallback.min,
      max: typeof saved?.max === "number" ? clamp(saved.max, METER_MAX_RANGE) : fallback.max,
    };
  } catch {
    return fallback;
  }
}

class MeterRange {
  min = $state(METER_MIN_DEFAULT);
  max = $state(METER_MAX_DEFAULT);

  constructor() {
    const saved = load();
    this.min = saved.min;
    this.max = saved.max;
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
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ min: this.min, max: this.max }));
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
