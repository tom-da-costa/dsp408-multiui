// Limiter threshold calculator, after Marc.O's "Intelligent limiter threshold" calculator
// (hornplans.free.fr/limiteur.html, dBu mode). All levels are in dBu, the unit of the DSP 408's
// dynamics thresholds.
//
//   speaker threshold = 20·log10(√(P_AES / k · Z) / 0.775) − amp gain
//                       k = 1.5625 for an open load (horn, vented box), 2.34375 for a closed box
//   amp threshold     = 20·log10(√(P_amp / 2 · Z) / 0.775) − amp gain   (amp at half its power)
//   threshold         = the lower of the two, rounded down to 0.1 dB (Hornplans' result)
//
// Hornplans' result is the hard limiter: the open / closed load factor already keeps the speaker
// 1.9 / 3.7 dB under its AES power. A soft limiter sits 2 dB higher on the speaker side (the
// amplifier limit stays a ceiling). This matches another calculator the owner uses: 1700 W AES,
// 8 ohm, 40.5 dB -> hard open 1.1, hard closed -0.7, soft open 3.1 dBu. The compressor gets
// that value on the DSP's 0.5 dB step, rounded down by default (never above the computed limit)
// or up on request (up to 0.5 dB above it); the limiter goes 6 dB above it.

export type Load = "open" | "closed";
export type Mode = "hard" | "soft";
/** How the threshold goes onto the DSP's 0.5 dB step: down is the safe side. */
export type Rounding = "down" | "up";

export const LOAD_FACTOR: Record<Load, number> = { open: 1.5625, closed: 2.34375 };
/** dB added on the speaker side: hard = Hornplans, soft = 2 dB above. */
export const SOFT_EXTRA_DB: Record<Mode, number> = { hard: 0, soft: 2 };
export const LIMITER_ABOVE_COMP_DB = 6;
export const THRESHOLD_RANGE_DBU: [number, number] = [-90, 20];
const DBU_REF_V = 0.775;
const THRESHOLD_STEP = 0.5;

export interface LimiterInput {
  speakerAesW: number; // total AES power of the speakers on the amp channel
  impedanceOhm: number; // total impedance on that channel
  ampGainDb: number;
  ampPowerW: number | null; // amp power at that impedance (RMS); null = not taken into account
  load: Load;
  mode: Mode;
  rounding?: Rounding; // default "down"
}

export interface LimiterResult {
  speakerDbu: number;
  ampDbu: number | null;
  limitedBy: "speaker" | "amp";
  hornplansDbu: number; // Hornplans' result = the hard threshold (rounded down to 0.1)
  extraDb: number; // soft: +2 dB on the speaker side
  thresholdDbu: number; // the hard or soft threshold (rounded down to 0.1), before the DSP step
  compThresholdDbu: number; // what is applied (0.5 dB steps, clamped to the DSP range)
  rounding: Rounding;
  limitThresholdDbu: number;
  clamped: boolean; // the result was outside the DSP's threshold range
}

/** Level in dBu of `watts` into `ohms`, as seen at the amp input for an amp of `gainDb`. */
export function inputDbu(watts: number, ohms: number, gainDb: number): number {
  return 20 * Math.log10(Math.sqrt(watts * ohms) / DBU_REF_V) - gainDb;
}

/** Excel ROUNDDOWN / ROUNDUP as the original sheet uses them: toward the lower value. */
function floorTo(value: number, step: number): number {
  return Math.floor(value / step + 1e-9) * step;
}

/** Toward the higher value; a value already on the step stays as it is. */
function ceilTo(value: number, step: number): number {
  return Math.ceil(value / step - 1e-9) * step;
}

function clamp(value: number): number {
  return Math.min(THRESHOLD_RANGE_DBU[1], Math.max(THRESHOLD_RANGE_DBU[0], value));
}

export function validate(input: LimiterInput): string | null {
  if (!(input.speakerAesW > 0)) return "Speaker power must be > 0";
  if (!(input.impedanceOhm > 0)) return "Impedance must be > 0";
  if (!Number.isFinite(input.ampGainDb)) return "Amplifier gain is required";
  if (input.ampPowerW !== null && !(input.ampPowerW > 0)) return "Amplifier power must be > 0";
  return null;
}

export function computeLimiter(input: LimiterInput): LimiterResult {
  const speakerDbu = inputDbu(
    input.speakerAesW / LOAD_FACTOR[input.load],
    input.impedanceOhm,
    input.ampGainDb,
  );
  const ampDbu =
    input.ampPowerW === null ? null : inputDbu(input.ampPowerW / 2, input.impedanceOhm, input.ampGainDb);
  const lower = (speaker: number) => (ampDbu !== null && ampDbu < speaker ? ampDbu : speaker);
  const hornplansDbu = Number(floorTo(lower(speakerDbu), 0.1).toFixed(1));
  const extraDb = SOFT_EXTRA_DB[input.mode];
  const level = lower(speakerDbu + extraDb);
  const thresholdDbu = Number(floorTo(level, 0.1).toFixed(1));
  const rounding = input.rounding ?? "down";
  const wanted = (rounding === "up" ? ceilTo : floorTo)(thresholdDbu, THRESHOLD_STEP);
  const compThresholdDbu = clamp(wanted);
  const limitThresholdDbu = clamp(compThresholdDbu + LIMITER_ABOVE_COMP_DB);
  return {
    speakerDbu,
    ampDbu,
    limitedBy: ampDbu !== null && ampDbu < speakerDbu + extraDb ? "amp" : "speaker",
    hornplansDbu,
    extraDb,
    thresholdDbu,
    compThresholdDbu,
    rounding,
    limitThresholdDbu,
    clamped: compThresholdDbu !== wanted,
  };
}

/** Compressor and limiter settings applied by the calculator (besides the thresholds). */
export const APPLIED = {
  compressor: { attack_ms: 1, release_ms: 1000, knee_db: 0 }, // ratio: "Limit"
  limiter: { attack_ms: 1, release_ms: 1000 },
} as const;
