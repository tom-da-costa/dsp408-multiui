// SIG indicator: lit while a channel's level is above a threshold (Settings › Display, −60 dBu by
// default, remembered in this browser), and for a short hold after it drops, so that it does not
// flicker between meter frames. Computed from the meters already received.

const STORAGE_KEY = "dsp408.signalThreshold";

export const SIGNAL_DEFAULT_DB = -60;
/** Range offered in Settings. An unconnected input reads about −86 dBu (ADC noise floor). */
export const SIGNAL_RANGE_DB = [-80, -20] as const;
export const SIGNAL_HOLD_MS = 300;
export const SIGNAL_COLOR = "var(--accent)";

function clamp(db: number): number {
  return Math.min(SIGNAL_RANGE_DB[1], Math.max(SIGNAL_RANGE_DB[0], Math.round(db)));
}

function load(): number {
  try {
    const saved = Number(localStorage.getItem(STORAGE_KEY));
    return localStorage.getItem(STORAGE_KEY) !== null && Number.isFinite(saved)
      ? clamp(saved)
      : SIGNAL_DEFAULT_DB;
  } catch {
    return SIGNAL_DEFAULT_DB;
  }
}

class SignalSettings {
  threshold = $state(load());

  setThreshold(db: number): void {
    this.threshold = clamp(db);
    try {
      localStorage.setItem(STORAGE_KEY, String(this.threshold));
    } catch {
      // not persisted: fine
    }
  }
}

export const signal = new SignalSettings();

/** True when `level` (dBu, null = no data) is above `threshold`. */
export function hasSignal(level: number | null, threshold: number): boolean {
  return level !== null && level > threshold;
}

/**
 * The SIG state of one meter, held for SIGNAL_HOLD_MS after the level drops. Call it while a
 * component initialises: it sets up effects.
 */
export function signalLit(level: () => number | null): { readonly lit: boolean } {
  let until = $state(0);
  let now = $state(0);
  $effect(() => {
    const above = hasSignal(level(), signal.threshold);
    now = performance.now();
    if (above) until = now + SIGNAL_HOLD_MS;
  });
  $effect(() => {
    if (until <= now) return;
    const timer = setTimeout(() => (now = performance.now()), until - now + 10);
    return () => clearTimeout(timer);
  });
  return {
    get lit() {
      return hasSignal(level(), signal.threshold) || until > now;
    },
  };
}
