// Frequency response of a channel's filters and equalisers, for the response graph.
//
// Computed from analogue prototypes evaluated at s = jω (the DSP runs at 96 kHz, so the audio
// band is far from Nyquist and the digital filters match their analogue models closely). How
// the 408 implements each filter is not documented; these are the textbook definitions:
//   - crossover: Butterworth (BW), Bessel (BL, -3 dB at the cut-off) and Linkwitz-Riley (LR =
//     two cascaded Butterworth of half the order, -6 dB at the cut-off), 6 dB/oct per order;
//   - PEQ: peak and shelves (RBJ "audio EQ cookbook" prototypes, with the band's Q), first and
//     second order low / high pass, all-pass (flat magnitude);
//   - GEQ: 31 one-third-octave peaking bands (Q ≈ 4.32).

import { GEQ_FREQS } from "./scale";
import type { Channel, Filter, PeqBand } from "./types";

type Complex = [number, number];

const mul = (a: Complex, b: Complex): Complex => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
const div = (a: Complex, b: Complex): Complex => {
  const d = b[0] * b[0] + b[1] * b[1];
  return [(a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d];
};
const abs = (a: Complex) => Math.hypot(a[0], a[1]);
const db = (magnitude: number) => 20 * Math.log10(Math.max(magnitude, 1e-12));

/** Polynomial with real coefficients (highest power first) evaluated at s = jw (Horner). */
function poly(coefficients: number[], w: number): Complex {
  let result: Complex = [0, 0];
  for (const c of coefficients) {
    const [re, im] = mul(result, [0, w]);
    result = [re + c, im];
  }
  return result;
}

// --- crossover filters --------------------------------------------------------------------------

/** Reverse Bessel polynomials θn(s), highest power first. */
const BESSEL: Record<number, number[]> = {
  1: [1, 1],
  2: [1, 3, 3],
  3: [1, 6, 15, 15],
  4: [1, 10, 45, 105, 105],
  5: [1, 15, 105, 420, 945, 945],
  6: [1, 21, 210, 1260, 4725, 10395, 10395],
  7: [1, 28, 378, 3150, 17325, 62370, 135135, 135135],
  8: [1, 36, 630, 6930, 51975, 270270, 945945, 2027025, 2027025],
};

/** Normalised Bessel low-pass magnitude at w (rad/s), before the -3 dB scaling. */
function besselRaw(order: number, w: number): number {
  const p = BESSEL[order]!;
  return p[p.length - 1]! / abs(poly(p, w));
}

const besselScale = new Map<number, number>();

/** Frequency factor that puts a Bessel filter's -3 dB point at w = 1. */
function besselW3(order: number): number {
  const cached = besselScale.get(order);
  if (cached !== undefined) return cached;
  let lo = 0.01;
  let hi = 100;
  for (let i = 0; i < 80; i++) {
    const mid = Math.sqrt(lo * hi);
    if (besselRaw(order, mid) > Math.SQRT1_2) lo = mid;
    else hi = mid;
  }
  besselScale.set(order, lo);
  return lo;
}

/** Butterworth low-pass magnitude at the normalised frequency x = f / fc. */
const butterworth = (order: number, x: number) => 1 / Math.sqrt(1 + x ** (2 * order));

export interface SlopeSpec {
  family: "BW" | "BL" | "LR";
  dbPerOctave: number;
}

/** "LR-24" → { family: "LR", dbPerOctave: 24 }; null for "Off" or an unknown name. */
export function parseSlope(name: string): SlopeSpec | null {
  const match = /^(BW|BL|LR)-(\d+)$/.exec(name.trim());
  if (!match) return null;
  return { family: match[1] as SlopeSpec["family"], dbPerOctave: Number(match[2]) };
}

/** Low-pass magnitude at x = f / fc for a slope; a high-pass is the same at 1 / x. */
export function lowPassMagnitude(slope: SlopeSpec, x: number): number {
  const order = Math.max(1, Math.round(slope.dbPerOctave / 6));
  if (slope.family === "LR") return butterworth(Math.max(1, order / 2), x) ** 2;
  if (slope.family === "BL") {
    const n = Math.min(8, order);
    return besselRaw(n, x * besselW3(n));
  }
  return butterworth(order, x);
}

function crossoverDb(filter: Filter, kind: "hpf" | "lpf", slopes: string[], f: number): number {
  if (!filter.enabled) return 0;
  const slope = parseSlope(slopes[filter.slope] ?? "");
  if (!slope) return 0;
  const x = f / filter.freq_hz;
  return db(lowPassMagnitude(slope, kind === "lpf" ? x : 1 / x));
}

// --- parametric and graphic EQ ------------------------------------------------------------------

/** Whether a PEQ band type has a gain (peak and shelves; not the pass and all-pass filters). */
export function usesGain(typeName: string): boolean {
  return /peak|shelf/i.test(typeName);
}

/** Magnitude in dB of one PEQ band at f, by type name. */
export function peqBandDb(band: PeqBand, typeName: string, f: number): number {
  if (band.bypass) return 0;
  const w = f / band.freq_hz; // normalised: s = jw
  const q = Math.max(band.q, 0.05);
  const a = 10 ** (band.gain_db / 40);
  const name = typeName.toLowerCase();
  const ratio = (num: number[], den: number[]) => db(abs(div(poly(num, w), poly(den, w))));
  if (name.startsWith("peak")) return ratio([1, a / q, 1], [1, 1 / (a * q), 1]);
  if (name.includes("low shelf")) {
    const k = Math.sqrt(a) / q;
    return db(a) + ratio([1, k, a], [a, k, 1]);
  }
  if (name.includes("high shelf")) {
    const k = Math.sqrt(a) / q;
    return db(a) + ratio([a, k, 1], [1, k, a]);
  }
  if (name.startsWith("lp")) return /12/.test(name) ? ratio([1], [1, 1 / q, 1]) : ratio([1], [1, 1]);
  if (name.startsWith("hp")) {
    return /12/.test(name) ? ratio([1, 0, 0], [1, 1 / q, 1]) : ratio([1, 0], [1, 1]);
  }
  return 0; // all-pass and unknown types: flat magnitude
}

const GEQ_Q = 1 / (2 * Math.sinh((Math.LN2 / 2) * (1 / 3))); // one-third octave ≈ 4.32

function geqDb(gains: number[], f: number): number {
  let total = 0;
  gains.forEach((gain, n) => {
    if (gain === 0) return;
    total += peqBandDb(
      { gain_db: gain, freq_hz: GEQ_FREQS[n] ?? 1000, q: GEQ_Q, type: 0, bypass: false },
      "Peak",
      f,
    );
  });
  return total;
}

// --- whole channel ------------------------------------------------------------------------------

export const F_MIN = 20;
export const F_MAX = 20000;

/** `count` log-spaced frequencies from F_MIN to F_MAX. */
export function frequencies(count = 240): number[] {
  return Array.from({ length: count }, (_, i) => F_MIN * (F_MAX / F_MIN) ** (i / (count - 1)));
}

export interface ChannelResponse {
  freqs: number[];
  total: number[]; // dB
  crossover: number[];
  peq: { band: number; curve: number[] }[]; // active bands only
  geq: number[] | null; // inputs with a non-flat GEQ
}

export function channelResponse(
  channel: Channel & { geq?: number[] },
  peqTypes: string[],
  slopes: string[],
  freqs = frequencies(),
): ChannelResponse {
  const crossover = freqs.map(
    (f) =>
      crossoverDb(channel.crossover.hpf, "hpf", slopes, f) +
      crossoverDb(channel.crossover.lpf, "lpf", slopes, f),
  );
  const peq = channel.peq_bypass
    ? []
    : channel.peq
        .map((band, n) => ({ band: n, b: band }))
        .filter(({ b }) => !b.bypass)
        .map(({ band, b }) => ({
          band,
          curve: freqs.map((f) => peqBandDb(b, peqTypes[b.type] ?? "Peak", f)),
        }))
        .filter(({ curve }) => curve.some((v) => Math.abs(v) > 0.01));
  const geqGains = channel.geq;
  const geq = geqGains && geqGains.some((g) => g !== 0) ? freqs.map((f) => geqDb(geqGains, f)) : null;
  const total = freqs.map(
    (_, i) =>
      crossover[i]! + peq.reduce((sum, p) => sum + p.curve[i]!, 0) + (geq ? geq[i]! : 0),
  );
  return { freqs, total, crossover, peq, geq };
}
