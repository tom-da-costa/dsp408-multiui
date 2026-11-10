// Limiter threshold calculator, after Marc.O's "Intelligent limiter threshold" calculator
// (hornplans.free.fr/limiteur.html, dBu mode). All levels are in dBu, the unit of the DSP 408's
// dynamics thresholds.
//
//   speaker threshold = 20·log10(√(P_AES / k · Z) / 0.775) − amp gain
//                       k = 1.5625 for an open load (horn, vented box), 2.34375 for a closed box
//   amp threshold     = 20·log10(√(P_amp / 2 · Z) / 0.775) − amp gain   (amp at half its power)
//   threshold         = the lower of the two, rounded down to 0.1 dB (Hornplans' result)
//
// Then this app subtracts the margin (hard limiter: 2 dB, soft: 0 dB), rounds down to the DSP's
// 0.5 dB step for the compressor, and puts the limiter 6 dB above it.

export type Load = "open" | "closed";
export type Mode = "hard" | "soft";

export const LOAD_FACTOR: Record<Load, number> = { open: 1.5625, closed: 2.34375 };
export const MARGIN_DB: Record<Mode, number> = { hard: 2, soft: 0 };
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
}

export interface LimiterResult {
  speakerDbu: number;
  ampDbu: number | null;
  limitedBy: "speaker" | "amp";
  hornplansDbu: number; // the calculator's own result (lower of the two, rounded down to 0.1)
  marginDb: number;
  afterMarginDbu: number; // Hornplans' result minus the margin, before the DSP's 0.5 dB step
  compThresholdDbu: number; // what is applied (0.5 dB steps, clamped to the DSP range)
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
  const lowest = ampDbu !== null && ampDbu < speakerDbu ? ampDbu : speakerDbu;
  const hornplansDbu = Number(floorTo(lowest, 0.1).toFixed(1));
  const marginDb = MARGIN_DB[input.mode];
  const wanted = floorTo(hornplansDbu - marginDb, THRESHOLD_STEP);
  const compThresholdDbu = clamp(wanted);
  const limitThresholdDbu = clamp(compThresholdDbu + LIMITER_ABOVE_COMP_DB);
  return {
    speakerDbu,
    ampDbu,
    limitedBy: ampDbu !== null && ampDbu < speakerDbu ? "amp" : "speaker",
    hornplansDbu,
    marginDb,
    afterMarginDbu: Number((hornplansDbu - marginDb).toFixed(1)),
    compThresholdDbu,
    limitThresholdDbu,
    clamped: compThresholdDbu !== wanted,
  };
}

/** Compressor and limiter settings applied by the calculator (besides the thresholds). */
export const APPLIED = {
  compressor: { attack_ms: 1, release_ms: 1000, knee_db: 0 }, // ratio: "Limit"
  limiter: { attack_ms: 1, release_ms: 1000 },
} as const;
