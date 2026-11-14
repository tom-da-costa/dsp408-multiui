// Setup wizard (Setup tab, issue #36): from a description of the sources and of the speaker
// stack to the whole DSP configuration. Pure functions over a draft the wizard edits; the
// server validates and quantises the plan again (state/setup.py), then loads it with the preset
// sequence (outputs muted while it is written, inputs left muted at the end).
//
//   routing      sources take the inputs in order (a stereo source two, linked); the main ways
//                (low to high) then the auxiliary ways take the outputs in order, a stereo way
//                two (linked); any output can be moved by hand
//   crossovers   between two main ways, at √(top of the lower × bottom of the upper range),
//                LR-24; a subsonic high-pass at the bottom of the lowest way, BW-24; the
//                auxiliary ways are filtered to their speakers' range, BW-24
//   limiters     the limiter calculator (lib/limiter.ts) per way, with the totals of one
//                amplifier channel (cabinets in parallel or in series)
//   gains        each way's SPL at its limiter threshold: sensitivity + 10·log10(power per
//                cabinet) + 3 dB per doubling of the cabinets; the output gains then give every
//                main way the same level for the same input (the loudest ways are turned down)

import {
  computeLimiter,
  LIMITER_ABOVE_COMP_DB,
  validate as validateLimiter,
  type LimiterResult,
  type Load,
  type Mode,
  type Rounding,
} from "./limiter";
import amplifierData from "../data/amplifiers.json";
import speakerData from "../data/speakers.json";

const DBU_REF_V = 0.775;
export const DEFAULT_SENSITIVITY_DB = 102;
export const DEFAULT_SHELF_HZ = 100;
export const DEFAULT_SHELF_DB = 3;
export const CHANNEL_NAME_LENGTH = 8;
export const PRESET_NAME_LENGTH = 14;
/** Slopes proposed, by name in the profile's list. */
export const CROSSOVER_SLOPE = "LR-24";
export const PROTECTION_SLOPE = "BW-24";

// --- library -------------------------------------------------------------------------------------

export interface SpeakerSection {
  name: string;
  drivers: string;
  impedance_ohm: number;
  aes_w: number;
  sensitivity_db: number;
  low_hz: number;
  high_hz: number;
  load: Load;
  estimated: string[];
  source: string;
}

export interface SpeakerModel {
  id: string;
  name: string;
  description: string;
  sections: SpeakerSection[];
}

export interface AmplifierModel {
  id: string;
  name: string;
  channels: number;
  power_w: Record<string, number>;
  bridge_power_w: Record<string, number>;
  gains_db: number[];
  rating: string;
}

export const SPEAKERS = speakerData.speakers as SpeakerModel[];
export const AMPLIFIERS = amplifierData.amplifiers as AmplifierModel[];

export function amplifier(id: string | null): AmplifierModel | null {
  return AMPLIFIERS.find((a) => a.id === id) ?? null;
}

/** The amplifier's power per channel into `ohm`: its rating at the nearest listed load at or
 * above `ohm` (the safe side); above every listed load, the highest one scaled at constant
 * voltage. null below its lowest rated load. */
export function ampPowerAt(amp: AmplifierModel, ohm: number): number | null {
  const loads = Object.keys(amp.power_w)
    .map(Number)
    .sort((a, b) => a - b);
  if (loads.length === 0 || ohm < loads[0]! - 0.05) return null;
  const at = loads.find((load) => load >= ohm - 0.05);
  if (at !== undefined) return amp.power_w[String(at)] ?? null;
  const top = loads[loads.length - 1];
  if (top === undefined) return null;
  return Math.round(((amp.power_w[String(top)] ?? 0) * top) / ohm);
}

/** Gain of an amplifier from its input sensitivity: `volts` in gives `powerW` into `ohm`. */
export function gainFromSensitivity(volts: number, powerW: number, ohm: number): number {
  return 20 * Math.log10(Math.sqrt(powerW * ohm) / volts);
}

// --- draft ---------------------------------------------------------------------------------------

/** Number fields stay text while typed (empty = not set). */
export type Num = string;

export interface Source {
  id: number;
  name: string;
  stereo: boolean;
}

export interface SpeakerSpec {
  /** Library speaker and section ("th1821/0"), null when typed in. */
  ref: string | null;
  label: string;
  lowHz: Num;
  highHz: Num;
  aesW: Num;
  impedanceOhm: Num;
  sensitivityDb: Num;
  load: Load;
}

export interface AmpSpec {
  /** Library amplifier, null when typed in. */
  ref: string | null;
  /** Active speakers: no amplifier, no limiter. */
  active: boolean;
  gainMode: "gain" | "sensitivity";
  gainDb: Num;
  sensitivityV: Num;
  sensitivityPowerW: Num;
  sensitivityOhm: Num;
  /** Power per channel at this way's load; empty = not taken into account. */
  powerW: Num;
}

export interface Way {
  id: number;
  name: string;
  stereo: boolean;
  /** Auxiliary output (monitor, fill…): not part of the crossover chain nor of the alignment. */
  aux: boolean;
  /** Ids of the sources it plays. */
  sources: number[];
  speaker: SpeakerSpec;
  /** Cabinets on one amplifier channel, and how they are wired together. */
  cabinets: number;
  wiring: "parallel" | "series";
  /** Amplifier channels fed by one output (several channels, each with its cabinets). */
  ampChannels: number;
  amp: AmpSpec;
  mode: Mode;
  rounding: Rounding;
  phase: boolean;
  /** Outputs chosen by hand (indices, L then R), or null for the automatic order. */
  outputs: number[] | null;
  /** Output gain typed over the computed one. */
  gainDb: Num;
}

export interface FilterSetting {
  enabled: boolean;
  /** Empty = the proposed frequency. */
  freqHz: Num;
  slope: number;
}

export interface Draft {
  sources: Source[];
  ways: Way[];
  lowShelf: { enabled: boolean; freqHz: Num; gainDb: Num };
  /** Crossovers between two main ways, by "lowerId-upperId". */
  crossovers: Record<string, FilterSetting>;
  subsonic: FilterSetting;
  /** Filters of the auxiliary ways, by way id. */
  aux: Record<number, { hpf: FilterSetting; lpf: FilterSetting }>;
  slot: number;
  presetName: string;
  nextId: number;
}

export interface Topology {
  inputs: number;
  outputs: number;
  presets: number;
  slopes: string[];
}

export function slopeIndex(slopes: string[], name: string): number {
  return Math.max(1, slopes.indexOf(name));
}

export function newDraft(slopes: string[]): Draft {
  return {
    sources: [{ id: 1, name: "Mix", stereo: true }],
    ways: [],
    lowShelf: { enabled: false, freqHz: String(DEFAULT_SHELF_HZ), gainDb: String(DEFAULT_SHELF_DB) },
    crossovers: {},
    subsonic: { enabled: true, freqHz: "", slope: slopeIndex(slopes, PROTECTION_SLOPE) },
    aux: {},
    slot: 0,
    presetName: "Setup",
    nextId: 2,
  };
}

export function blankSpeaker(): SpeakerSpec {
  return {
    ref: null,
    label: "",
    lowHz: "",
    highHz: "",
    aesW: "",
    impedanceOhm: "8",
    sensitivityDb: String(DEFAULT_SENSITIVITY_DB),
    load: "open",
  };
}

export function speakerFromLibrary(model: SpeakerModel, index: number): SpeakerSpec {
  const s = model.sections[index]!;
  return {
    ref: `${model.id}/${index}`,
    label: model.sections.length > 1 ? `${model.name} · ${s.name}` : model.name,
    lowHz: String(s.low_hz),
    highHz: String(s.high_hz),
    aesW: String(s.aes_w),
    impedanceOhm: String(s.impedance_ohm),
    sensitivityDb: String(s.sensitivity_db),
    load: s.load,
  };
}

export function librarySection(ref: string | null): SpeakerSection | null {
  if (ref === null) return null;
  const [id, index] = ref.split("/");
  return SPEAKERS.find((m) => m.id === id)?.sections[Number(index)] ?? null;
}

export function blankAmp(): AmpSpec {
  return {
    ref: null,
    active: false,
    gainMode: "gain",
    gainDb: "",
    sensitivityV: "",
    sensitivityPowerW: "",
    sensitivityOhm: "8",
    powerW: "",
  };
}

export function newWay(id: number, name: string, speaker: SpeakerSpec, sources: number[]): Way {
  return {
    id,
    name,
    stereo: false,
    aux: false,
    sources,
    speaker,
    cabinets: 1,
    wiring: "parallel",
    ampChannels: 1,
    amp: blankAmp(),
    mode: "hard",
    rounding: "up",
    phase: false,
    outputs: null,
    gainDb: "",
  };
}

/** A library amplifier on a way: its highest listed gain and its power at the way's load. */
export function useAmplifier(way: Way, amp: AmplifierModel | null): void {
  way.amp.ref = amp?.id ?? null;
  if (amp === null) return;
  way.amp.active = false;
  way.amp.gainMode = "gain";
  way.amp.gainDb = String(Math.max(...amp.gains_db));
  refreshAmpPower(way);
}

/** Re-read the library amplifier's power after the load changed. */
export function refreshAmpPower(way: Way): void {
  const amp = amplifier(way.amp.ref);
  const z = load(way)?.impedanceOhm;
  if (amp === null || z === undefined) return;
  const power = ampPowerAt(amp, z);
  way.amp.powerW = power === null ? "" : String(power);
  way.amp.sensitivityPowerW = String(amp.power_w["8"] ?? "");
}

// --- numbers -------------------------------------------------------------------------------------

export function num(text: Num): number {
  return text.trim() === "" ? NaN : Number(text.replace(",", "."));
}

const positive = (v: number) => Number.isFinite(v) && v > 0;

// --- routing ---------------------------------------------------------------------------------

/** Inputs of each source (indices), in order; a stereo source takes two. */
export function sourceInputs(draft: Draft): Map<number, number[]> {
  const map = new Map<number, number[]>();
  let next = 0;
  for (const source of draft.sources) {
    const count = source.stereo ? 2 : 1;
    map.set(source.id, Array.from({ length: count }, (_, k) => next + k));
    next += count;
  }
  return map;
}

export function inputsNeeded(draft: Draft): number {
  return draft.sources.reduce((sum, s) => sum + (s.stereo ? 2 : 1), 0);
}

/** Centre of a way's range (geometric), to order the ways; unknown ranges go last. */
function centreHz(way: Way): number {
  const low = num(way.speaker.lowHz);
  const high = num(way.speaker.highHz);
  return positive(low) && positive(high) ? Math.sqrt(low * high) : Infinity;
}

/** Main ways from low to high (by the centre of their range, then as listed). */
export function mainWays(draft: Draft): Way[] {
  return draft.ways
    .filter((w) => !w.aux)
    .map((w, order) => ({ w, order, centre: centreHz(w) }))
    .sort((a, b) => (a.centre === b.centre ? a.order - b.order : a.centre - b.centre))
    .map(({ w }) => w);
}

/** Ways in output order: main ways from low to high, then the auxiliary ones. */
export function orderedWays(draft: Draft): Way[] {
  return [...mainWays(draft), ...draft.ways.filter((w) => w.aux)];
}

export function outputsNeeded(draft: Draft): number {
  return draft.ways.reduce((sum, w) => sum + (w.stereo ? 2 : 1), 0);
}

/** Outputs of each way (L then R for a stereo way): chosen by hand, or the next free ones. */
export function wayOutputs(draft: Draft, total: number): Map<number, number[]> {
  const map = new Map<number, number[]>();
  const taken = new Set<number>();
  for (const way of draft.ways) {
    const count = way.stereo ? 2 : 1;
    if (way.outputs !== null && way.outputs.length === count) {
      map.set(way.id, [...way.outputs]);
      way.outputs.forEach((o) => taken.add(o));
    }
  }
  let next = 0;
  for (const way of orderedWays(draft)) {
    if (map.has(way.id)) continue;
    const outs: number[] = [];
    for (let k = 0; k < (way.stereo ? 2 : 1); k++) {
      while (taken.has(next)) next++;
      outs.push(next < total ? next : -1);
      taken.add(next);
      next++;
    }
    map.set(way.id, outs);
  }
  return map;
}

/** Channel names: a way's name, plus " L" / " R" when stereo. */
export function channelNames(base: string, stereo: boolean): string[] {
  return stereo ? [`${base} L`, `${base} R`] : [base];
}

// --- loads, limiters, levels -------------------------------------------------------------------

export interface WayLoad {
  impedanceOhm: number; // on one amplifier channel
  aesW: number; // on one amplifier channel
}

export function load(way: Way): WayLoad | null {
  const z = num(way.speaker.impedanceOhm);
  const aes = num(way.speaker.aesW);
  const n = Math.max(1, Math.round(way.cabinets));
  if (!positive(z) || !positive(aes)) return null;
  return {
    impedanceOhm: way.wiring === "parallel" ? z / n : z * n,
    aesW: aes * n,
  };
}

export function ampGain(way: Way): number {
  const amp = way.amp;
  if (amp.gainMode === "gain") return num(amp.gainDb);
  return gainFromSensitivity(
    num(amp.sensitivityV),
    num(amp.sensitivityPowerW),
    num(amp.sensitivityOhm),
  );
}

export interface WayLevel {
  limiter: LimiterResult | null; // null: active speakers, or the data is incomplete
  error: string | null;
  /** SPL at 1 m of all the way's cabinets at the limiter threshold (per side). */
  splMaxDb: number | null;
  /** SPL for 0 dBu at the DSP output, before the output gain. */
  splAt0Db: number | null;
}

export function wayLevel(way: Way): WayLevel {
  const none = (error: string | null): WayLevel => ({
    limiter: null,
    error,
    splMaxDb: null,
    splAt0Db: null,
  });
  if (way.amp.active) return none(null);
  const l = load(way);
  if (l === null) return none("speaker power and impedance are needed");
  const gain = ampGain(way);
  const power = num(way.amp.powerW);
  const input = {
    speakerAesW: l.aesW,
    impedanceOhm: l.impedanceOhm,
    ampGainDb: gain,
    ampPowerW: positive(power) ? power : null,
    load: way.speaker.load,
    mode: way.mode,
    rounding: way.rounding,
  };
  const error = validateLimiter(input);
  if (error) return none(error);
  const limiter = computeLimiter(input);
  const sensitivity = num(way.speaker.sensitivityDb);
  if (!Number.isFinite(sensitivity)) return { limiter, error: null, splMaxDb: null, splAt0Db: null };
  const n = Math.max(1, Math.round(way.cabinets));
  const cabinets = n * Math.max(1, Math.round(way.ampChannels));
  const splAt = (dbu: number) => {
    const volts = DBU_REF_V * 10 ** ((dbu + gain) / 20);
    const perCabinet = volts ** 2 / l.impedanceOhm / n;
    return sensitivity + 10 * Math.log10(perCabinet) + 10 * Math.log10(cabinets);
  };
  return {
    limiter,
    error: null,
    splMaxDb: splAt(limiter.compThresholdDbu),
    splAt0Db: splAt(0),
  };
}

/** Output gain of each way: the main ways matched to the quietest one, the others at 0 dB;
 * a gain typed by hand wins. */
export function wayGains(draft: Draft): Map<number, { gainDb: number; computed: number }> {
  const levels = new Map(draft.ways.map((w) => [w.id, wayLevel(w)]));
  const aligned = mainWays(draft)
    .map((w) => levels.get(w.id)?.splAt0Db ?? null)
    .filter((v): v is number => v !== null);
  const reference = aligned.length ? Math.min(...aligned) : 0;
  const gains = new Map<number, { gainDb: number; computed: number }>();
  for (const way of draft.ways) {
    const at0 = levels.get(way.id)?.splAt0Db ?? null;
    const computed = !way.aux && at0 !== null ? Math.round((reference - at0) * 10) / 10 : 0;
    const typed = num(way.gainDb);
    gains.set(way.id, { gainDb: Number.isFinite(typed) ? typed : computed, computed });
  }
  return gains;
}

// --- filters -----------------------------------------------------------------------------------

export interface Boundary {
  key: string;
  lower: Way;
  upper: Way;
  proposedHz: number;
  /** The two speakers' ranges do not meet. */
  gap: boolean;
}

/** Crossover proposed between two ranges: the geometric mean of where they meet. */
export function proposeCrossover(lowerTopHz: number, upperBottomHz: number): number {
  return Math.round(Math.sqrt(lowerTopHz * upperBottomHz));
}

export function boundaries(draft: Draft): Boundary[] {
  const ways = mainWays(draft);
  const result: Boundary[] = [];
  for (let i = 0; i + 1 < ways.length; i++) {
    const lower = ways[i]!;
    const upper = ways[i + 1]!;
    const top = num(lower.speaker.highHz);
    const bottom = num(upper.speaker.lowHz);
    result.push({
      key: `${lower.id}-${upper.id}`,
      lower,
      upper,
      proposedHz: positive(top) && positive(bottom) ? proposeCrossover(top, bottom) : 1000,
      gap: positive(top) && positive(bottom) && bottom > top,
    });
  }
  return result;
}

function defaultCrossover(slopes: string[]): FilterSetting {
  return { enabled: true, freqHz: "", slope: slopeIndex(slopes, CROSSOVER_SLOPE) };
}

function defaultAux(slopes: string[]): { hpf: FilterSetting; lpf: FilterSetting } {
  const protection = slopeIndex(slopes, PROTECTION_SLOPE);
  return {
    hpf: { enabled: true, freqHz: "", slope: protection },
    lpf: { enabled: true, freqHz: "", slope: protection },
  };
}

export function crossoverSetting(draft: Draft, key: string, slopes: string[]): FilterSetting {
  return draft.crossovers[key] ?? defaultCrossover(slopes);
}

export function auxSetting(
  draft: Draft,
  way: Way,
  slopes: string[],
): { hpf: FilterSetting; lpf: FilterSetting } {
  return draft.aux[way.id] ?? defaultAux(slopes);
}

/** Give every crossover and auxiliary way its own editable setting (from an event handler:
 * the computations above only read the draft). */
export function ensureFilters(draft: Draft, slopes: string[]): void {
  for (const b of boundaries(draft)) draft.crossovers[b.key] ??= defaultCrossover(slopes);
  for (const way of draft.ways.filter((w) => w.aux)) draft.aux[way.id] ??= defaultAux(slopes);
}

export interface Filter {
  freq_hz: number;
  slope: number;
}

function resolved(setting: FilterSetting, proposedHz: number): Filter | null {
  if (!setting.enabled) return null;
  const typed = num(setting.freqHz);
  return { freq_hz: positive(typed) ? typed : proposedHz, slope: setting.slope };
}

/** The high-pass and low-pass of every way. */
export function wayFilters(
  draft: Draft,
  slopes: string[],
): Map<number, { hpf: Filter | null; lpf: Filter | null }> {
  const filters = new Map<number, { hpf: Filter | null; lpf: Filter | null }>();
  const main = mainWays(draft);
  for (const way of main) filters.set(way.id, { hpf: null, lpf: null });
  const lowest = main[0];
  if (lowest) {
    const bottom = num(lowest.speaker.lowHz);
    filters.get(lowest.id)!.hpf = resolved(draft.subsonic, positive(bottom) ? bottom : 30);
  }
  for (const b of boundaries(draft)) {
    const filter = resolved(crossoverSetting(draft, b.key, slopes), b.proposedHz);
    filters.get(b.lower.id)!.lpf = filter;
    filters.get(b.upper.id)!.hpf = filter;
  }
  for (const way of draft.ways.filter((w) => w.aux)) {
    const setting = auxSetting(draft, way, slopes);
    const bottom = num(way.speaker.lowHz);
    const top = num(way.speaker.highHz);
    filters.set(way.id, {
      hpf: positive(bottom) ? resolved(setting.hpf, bottom) : null,
      lpf: positive(top) && top < 20000 ? resolved(setting.lpf, top) : null,
    });
  }
  return filters;
}

// --- checks --------------------------------------------------------------------------------------

const PRINTABLE = /^[\x20-\x7e]*$/;

export function nameError(name: string, max: number): string {
  if (name.trim() === "") return "a name is required";
  if (name.length > max) return `${max} characters at most`;
  if (!PRINTABLE.test(name)) return "plain ASCII characters only";
  return "";
}

/** Problems that keep the wizard from going on, per step. */
export function inputErrors(draft: Draft, topo: Topology): string[] {
  const errors: string[] = [];
  if (draft.sources.length === 0) errors.push("Add a source.");
  if (inputsNeeded(draft) > topo.inputs)
    errors.push(`The sources need ${inputsNeeded(draft)} inputs, this DSP has ${topo.inputs}.`);
  for (const s of draft.sources) {
    for (const name of channelNames(s.name, s.stereo)) {
      const e = nameError(name, CHANNEL_NAME_LENGTH);
      if (e) errors.push(`Source "${s.name}": ${e} (channel name "${name}").`);
    }
  }
  if (draft.lowShelf.enabled) {
    const f = num(draft.lowShelf.freqHz);
    const g = num(draft.lowShelf.gainDb);
    if (!positive(f)) errors.push("Low shelf: a frequency is needed.");
    if (!Number.isFinite(g) || g < -12 || g > 12) errors.push("Low shelf: gain between −12 and +12 dB.");
  }
  return errors;
}

export function systemErrors(draft: Draft, topo: Topology): string[] {
  const errors: string[] = [];
  if (draft.ways.filter((w) => !w.aux).length === 0) errors.push("Add at least one way.");
  if (outputsNeeded(draft) > topo.outputs)
    errors.push(`The ways need ${outputsNeeded(draft)} outputs, this DSP has ${topo.outputs}.`);
  const seen = new Set<number>();
  for (const [id, outs] of wayOutputs(draft, topo.outputs)) {
    const way = draft.ways.find((w) => w.id === id)!;
    for (const o of outs) {
      if (o < 0 || o >= topo.outputs) continue; // counted above
      if (seen.has(o)) errors.push(`Out ${o + 1} is used twice.`);
      seen.add(o);
    }
    for (const name of channelNames(way.name, way.stereo)) {
      const e = nameError(name, CHANNEL_NAME_LENGTH);
      if (e) errors.push(`Way "${way.name}": ${e} (channel name "${name}").`);
    }
    if (way.sources.length === 0) errors.push(`Way "${way.name}": pick its source.`);
  }
  return errors;
}

export function speakerErrors(draft: Draft): string[] {
  const errors: string[] = [];
  for (const way of draft.ways) {
    const s = way.speaker;
    if (!positive(num(s.lowHz)) || !positive(num(s.highHz)))
      errors.push(`${way.name}: the speaker's frequency range is needed.`);
    else if (num(s.lowHz) >= num(s.highHz))
      errors.push(`${way.name}: the range's bottom must be below its top.`);
    if (way.amp.active) continue;
    if (!positive(num(s.aesW))) errors.push(`${way.name}: the speaker's AES power is needed.`);
    if (!positive(num(s.impedanceOhm))) errors.push(`${way.name}: the speaker's impedance is needed.`);
    if (!Number.isFinite(num(s.sensitivityDb)))
      errors.push(`${way.name}: the speaker's sensitivity is needed.`);
    if (!Number.isFinite(ampGain(way))) errors.push(`${way.name}: the amplifier's gain is needed.`);
    const error = wayLevel(way).error;
    if (error && positive(num(s.aesW))) errors.push(`${way.name}: ${error}.`);
  }
  return errors;
}

export function filterErrors(draft: Draft, slopes: string[]): string[] {
  const errors: string[] = [];
  for (const [id, f] of wayFilters(draft, slopes)) {
    const way = draft.ways.find((w) => w.id === id)!;
    if (f.hpf && f.lpf && f.hpf.freq_hz >= f.lpf.freq_hz)
      errors.push(`${way.name}: the high-pass is above the low-pass.`);
  }
  return errors;
}

export function storeErrors(draft: Draft, topo: Topology): string[] {
  const errors: string[] = [];
  if (!(draft.slot >= 1 && draft.slot <= topo.presets)) errors.push("Pick a preset slot.");
  const e = nameError(draft.presetName, PRESET_NAME_LENGTH);
  if (e) errors.push(`Preset name: ${e}.`);
  return errors;
}

// --- plan ----------------------------------------------------------------------------------------

/** What `setup.apply` sends (state/setup.py SetupPlan). */
export interface SetupPlan {
  inputs: { name: string; gain_db: number; low_shelf: { freq_hz: number; gain_db: number } | null }[];
  outputs: {
    name: string;
    used: boolean;
    sources: boolean[];
    gain_db: number;
    phase: boolean;
    hpf: Filter | null;
    lpf: Filter | null;
    dynamics: { compressor_threshold_db: number; limiter_threshold_db: number } | null;
  }[];
  input_links: number[][];
  output_links: number[][];
}

const letter = (i: number) => String.fromCharCode(65 + i);

export function buildPlan(draft: Draft, topo: Topology): SetupPlan {
  const inputsOf = sourceInputs(draft);
  const shelf = draft.lowShelf.enabled
    ? { freq_hz: num(draft.lowShelf.freqHz), gain_db: num(draft.lowShelf.gainDb) }
    : null;
  const inputs: SetupPlan["inputs"] = Array.from({ length: topo.inputs }, (_, i) => ({
    name: `In${letter(i)}`,
    gain_db: 0,
    low_shelf: null,
  }));
  const inputLinks: number[][] = [];
  for (const source of draft.sources) {
    const ins = inputsOf.get(source.id) ?? [];
    channelNames(source.name, source.stereo).forEach((name, k) => {
      const i = ins[k];
      if (i !== undefined && i < topo.inputs) inputs[i] = { name, gain_db: 0, low_shelf: shelf };
    });
    if (ins.length > 1) inputLinks.push(ins);
  }

  const outputs: SetupPlan["outputs"] = Array.from({ length: topo.outputs }, (_, i) => ({
    name: `Out${i + 1}`,
    used: false,
    sources: Array<boolean>(topo.inputs).fill(false),
    gain_db: 0,
    phase: false,
    hpf: null,
    lpf: null,
    dynamics: null,
  }));
  const outputLinks: number[][] = [];
  const outs = wayOutputs(draft, topo.outputs);
  const filters = wayFilters(draft, topo.slopes);
  const gains = wayGains(draft);
  for (const way of draft.ways) {
    const level = wayLevel(way);
    const assigned = outs.get(way.id) ?? [];
    const names = channelNames(way.name, way.stereo);
    assigned.forEach((o, side) => {
      if (o < 0 || o >= topo.outputs) return;
      const sources = Array<boolean>(topo.inputs).fill(false);
      for (const id of way.sources) {
        const source = draft.sources.find((s) => s.id === id);
        const ins = inputsOf.get(id) ?? [];
        // A stereo way takes the left of a stereo source on its left side, the right on its
        // right; a mono way, or a mono source, sums every input.
        const picked = way.stereo && source?.stereo ? [ins[side]] : ins;
        for (const i of picked) if (i !== undefined && i < topo.inputs) sources[i] = true;
      }
      const f = filters.get(way.id);
      outputs[o] = {
        name: names[side] ?? way.name,
        used: true,
        sources,
        gain_db: gains.get(way.id)?.gainDb ?? 0,
        phase: way.phase,
        hpf: f?.hpf ?? null,
        lpf: f?.lpf ?? null,
        dynamics: level.limiter
          ? {
              compressor_threshold_db: level.limiter.compThresholdDbu,
              limiter_threshold_db: level.limiter.limitThresholdDbu,
            }
          : null,
      };
    });
    const valid = assigned.filter((o) => o >= 0 && o < topo.outputs);
    if (way.stereo && valid.length === 2) outputLinks.push(valid);
  }
  outputLinks.sort((a, b) => a[0]! - b[0]!);
  return { inputs, outputs, input_links: inputLinks, output_links: outputLinks };
}

export { LIMITER_ABOVE_COMP_DB };
