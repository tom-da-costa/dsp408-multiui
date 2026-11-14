// Setup wizard (Setup tab, issue #36): from the sources and a plan of the system (the DSP's
// outputs wired to amplifier channels, the channels to speakers) to the whole DSP
// configuration. Pure functions over a draft the wizard edits; the server validates and
// quantises the plan again (state/setup.py), then loads it with the preset sequence (outputs
// muted while it is written, inputs left muted at the end).
//
//   ways         deduced from the wiring: the outputs that drive the same section of the same
//                speaker model form one way (two outputs to four subs: one "Sub" way, two
//                outputs, linked); an output drives one kind of speaker only
//   routing      each output plays a source's left, right or both (L+R, the default)
//   crossovers   between two main ways, at √(top of the lower × bottom of the upper range),
//                LR-24; a subsonic high-pass at the bottom of the lowest way, BW-24; the
//                auxiliary ways are filtered to their speakers' range, BW-24
//   limiters     the limiter calculator (lib/limiter.ts) per amplifier channel, with the
//                cabinets wired to it (in parallel); a way takes its lowest threshold (its
//                outputs are linked)
//   gains        each way's SPL for the same mono programme: the cabinets' powers added up
//                (sensitivity + 10·log10(power per cabinet), +6 dB on an output that sums both
//                sides of a stereo source); the output gains turn the louder main ways down to
//                the quietest

import {
  computeLimiter,
  validate as validateLimiter,
  type Load,
  type LimiterResult,
  type Mode,
  type Rounding,
} from "./limiter";
import amplifierData from "../data/amplifiers.json";
import speakerData from "../data/speakers.json";

const DBU_REF_V = 0.775;
const SUM_DB = 20 * Math.log10(2); // L + R of a mono programme
export const DEFAULT_SENSITIVITY_DB = 102;
export const DEFAULT_SHELF_HZ = 100;
export const DEFAULT_SHELF_DB = 3;
export const CHANNEL_NAME_LENGTH = 8;
export const PRESET_NAME_LENGTH = 14;
export const RATED_LOADS = ["8", "4", "2"] as const;
/** Slopes proposed, by name in the profile's list. */
export const CROSSOVER_SLOPE = "LR-24";
export const PROTECTION_SLOPE = "BW-24";

// --- library -------------------------------------------------------------------------------------

export interface LibrarySection {
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
  sections: LibrarySection[];
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

export function amplifierModel(id: string | null): AmplifierModel | null {
  return AMPLIFIERS.find((a) => a.id === id) ?? null;
}

export function speakerModel(id: string | null): SpeakerModel | null {
  return SPEAKERS.find((m) => m.id === id) ?? null;
}

/** Power per channel into `ohm`, from the ratings by load: the rating at the nearest listed load
 * at or above `ohm` (the safe side); above every listed load, the highest one scaled at constant
 * voltage. null below the lowest rated load, or with no rating. */
export function ampPowerAt(ratings: Record<string, number>, ohm: number): number | null {
  const rated = (load: number) => ratings[String(load)] ?? NaN;
  const loads = Object.keys(ratings)
    .map(Number)
    .filter((load) => rated(load) > 0)
    .sort((a, b) => a - b);
  const lowest = loads[0];
  if (lowest === undefined || ohm < lowest - 0.05) return null;
  const at = loads.find((load) => load >= ohm - 0.05);
  if (at !== undefined) return rated(at);
  const top = loads[loads.length - 1]!;
  return Math.round((rated(top) * top) / ohm);
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

/** One section of a speaker model: a way of the system once it is wired. */
export interface Section {
  /** Channel name of its outputs (" L", " R" or a number is added when there are several). */
  name: string;
  lowHz: Num;
  highHz: Num;
  aesW: Num;
  impedanceOhm: Num;
  sensitivityDb: Num;
  load: Load;
  /** Auxiliary (monitor, fill…): outside the crossover chain and the level matching. */
  aux: boolean;
  phase: boolean;
  mode: Mode;
  rounding: Rounding;
  /** Output gain typed over the computed one. */
  gainDb: Num;
}

/** A speaker model of the plan; every cabinet of that model shares it. */
export interface Kind {
  id: number;
  /** Library speaker, null for a generic one. */
  ref: string | null;
  model: string;
  sections: Section[];
}

export interface SpeakerNode {
  id: number;
  kind: number;
  x: number;
  y: number;
}

export interface AmpNode {
  id: number;
  /** Library amplifier, null for a generic one. */
  ref: string | null;
  model: string;
  channels: number;
  gainMode: "gain" | "sensitivity";
  gainDb: Num;
  sensitivityV: Num;
  sensitivityPowerW: Num;
  sensitivityOhm: Num;
  /** Power per channel by load ("8", "4", "2" Ω). */
  powerW: Record<string, Num>;
  x: number;
  y: number;
}

export type Side = "L" | "R" | "LR";

export interface Route {
  source: number | null;
  side: Side;
}

/** A link of the plan: DSP output → amplifier channel, amplifier channel → speaker section, or
 * DSP output → section of an active speaker. */
export type Wire =
  | { type: "feed"; output: number; amp: number; channel: number }
  | { type: "drive"; amp: number; channel: number; speaker: number; section: number }
  | { type: "direct"; output: number; speaker: number; section: number };

export interface FilterSetting {
  enabled: boolean;
  /** Empty = the proposed frequency. */
  freqHz: Num;
  slope: number;
}

export interface Draft {
  sources: Source[];
  kinds: Kind[];
  speakers: SpeakerNode[];
  amps: AmpNode[];
  wires: Wire[];
  /** What each DSP output plays, by output index. */
  routes: Record<number, Route>;
  lowShelf: { enabled: boolean; freqHz: Num; gainDb: Num };
  /** Crossovers between two main ways, by "lowerKey|upperKey". */
  crossovers: Record<string, FilterSetting>;
  subsonic: FilterSetting;
  /** Filters of the auxiliary ways, by way key. */
  aux: Record<string, { hpf: FilterSetting; lpf: FilterSetting }>;
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
    sources: [{ id: 1, name: "Main", stereo: true }],
    kinds: [],
    speakers: [],
    amps: [],
    wires: [],
    routes: {},
    lowShelf: { enabled: false, freqHz: String(DEFAULT_SHELF_HZ), gainDb: String(DEFAULT_SHELF_DB) },
    crossovers: {},
    subsonic: { enabled: true, freqHz: "", slope: slopeIndex(slopes, PROTECTION_SLOPE) },
    aux: {},
    slot: 0,
    presetName: "Setup",
    nextId: 2,
  };
}

function blankSection(name: string): Section {
  return {
    name,
    lowHz: "",
    highHz: "",
    aesW: "",
    impedanceOhm: "8",
    sensitivityDb: String(DEFAULT_SENSITIVITY_DB),
    load: "open",
    aux: false,
    phase: false,
    mode: "hard",
    rounding: "up",
    gainDb: "",
  };
}

export function newSection(index: number): Section {
  return blankSection(index === 0 ? "Spk" : `Spk${index + 1}`);
}

function librarySectionSpec(s: LibrarySection): Section {
  return {
    ...blankSection(s.name.slice(0, 6)),
    lowHz: String(s.low_hz),
    highHz: String(s.high_hz),
    aesW: String(s.aes_w),
    impedanceOhm: String(s.impedance_ohm),
    sensitivityDb: String(s.sensitivity_db),
    load: s.load,
  };
}

export function librarySection(kind: Kind, index: number): LibrarySection | null {
  return speakerModel(kind.ref)?.sections[index] ?? null;
}

/** Place a cabinet: of a library model (its kind is shared with the cabinets of the same model
 * already placed), or generic (a new kind). Returns the new node. */
export function addSpeaker(draft: Draft, ref: string | null, x: number, y: number): SpeakerNode {
  const model = speakerModel(ref);
  let kind = model ? draft.kinds.find((k) => k.ref === model.id) : undefined;
  if (!kind) {
    kind = {
      id: draft.nextId++,
      ref: model?.id ?? null,
      model: model?.name ?? "Generic",
      sections: model ? model.sections.map(librarySectionSpec) : [newSection(0)],
    };
    draft.kinds.push(kind);
  }
  const node = { id: draft.nextId++, kind: kind.id, x, y };
  draft.speakers.push(node);
  return node;
}

/** Another cabinet of the same model. */
export function duplicateSpeaker(draft: Draft, node: SpeakerNode): SpeakerNode {
  const copy = { id: draft.nextId++, kind: node.kind, x: node.x + 24, y: node.y + 24 };
  draft.speakers.push(copy);
  return copy;
}

export function addAmp(draft: Draft, ref: string | null, x: number, y: number): AmpNode {
  const model = amplifierModel(ref);
  const node: AmpNode = {
    id: draft.nextId++,
    ref: model?.id ?? null,
    model: model?.name ?? "Generic",
    channels: model?.channels ?? 2,
    gainMode: "gain",
    gainDb: model ? String(Math.max(...model.gains_db)) : "",
    sensitivityV: "",
    sensitivityPowerW: model?.power_w["8"] ? String(model.power_w["8"]) : "",
    sensitivityOhm: "8",
    powerW: Object.fromEntries(
      RATED_LOADS.map((load) => [load, model?.power_w[load] ? String(model.power_w[load]) : ""]),
    ),
    x,
    y,
  };
  draft.amps.push(node);
  return node;
}

export function removeNode(draft: Draft, type: "amp" | "speaker", id: number): void {
  if (type === "amp") {
    draft.amps = draft.amps.filter((a) => a.id !== id);
    draft.wires = draft.wires.filter((w) => w.type === "direct" || w.amp !== id);
  } else {
    const node = draft.speakers.find((s) => s.id === id);
    draft.speakers = draft.speakers.filter((s) => s.id !== id);
    draft.wires = draft.wires.filter((w) => w.type === "feed" || w.speaker !== id);
    if (node && !draft.speakers.some((s) => s.kind === node.kind))
      draft.kinds = draft.kinds.filter((k) => k.id !== node.kind);
  }
}

/** Fewer channels on an amplifier: the wires of the channels gone go too. */
export function setAmpChannels(draft: Draft, amp: AmpNode, channels: number): void {
  amp.channels = Math.max(1, Math.min(16, Math.round(channels) || 1));
  draft.wires = draft.wires.filter((w) => w.type === "direct" || w.amp !== amp.id || w.channel < amp.channels);
}

/** Fewer sections on a generic speaker: the wires of the sections gone go too. */
export function removeSection(draft: Draft, kind: Kind, index: number): void {
  if (kind.sections.length <= 1) return;
  kind.sections.splice(index, 1);
  const ids = new Set(draft.speakers.filter((s) => s.kind === kind.id).map((s) => s.id));
  draft.wires = draft.wires
    .filter((w) => w.type === "feed" || !ids.has(w.speaker) || w.section !== index)
    .map((w) => (w.type !== "feed" && ids.has(w.speaker) && w.section > index ? { ...w, section: w.section - 1 } : w));
}

export function removeSource(draft: Draft, id: number): void {
  draft.sources = draft.sources.filter((s) => s.id !== id);
  for (const route of Object.values(draft.routes)) if (route.source === id) route.source = null;
}

export function routeOf(draft: Draft, output: number): Route {
  return draft.routes[output] ?? { source: draft.sources[0]?.id ?? null, side: "LR" };
}

// --- ports and wiring ----------------------------------------------------------------------

/** A connection point of the plan. */
export type Port =
  | { node: "dsp"; port: number } // a DSP output
  | { node: "amp-in"; id: number; port: number }
  | { node: "amp-out"; id: number; port: number }
  | { node: "spk"; id: number; port: number };

export function portKey(p: Port): string {
  return p.node === "dsp" ? `dsp:${p.port}` : `${p.node}:${p.id}:${p.port}`;
}

export function parsePort(key: string): Port | null {
  const [node, a, b] = key.split(":");
  if (node === "dsp" && a !== undefined) return { node, port: Number(a) };
  if ((node === "amp-in" || node === "amp-out" || node === "spk") && a !== undefined && b !== undefined)
    return { node, id: Number(a), port: Number(b) };
  return null;
}

/** The wire joining two ports (in either order), or null when they cannot be joined. */
export function wireBetween(a: Port, b: Port): Wire | null {
  for (const [x, y] of [
    [a, b],
    [b, a],
  ] as const) {
    if (x.node === "dsp" && y.node === "amp-in")
      return { type: "feed", output: x.port, amp: y.id, channel: y.port };
    if (x.node === "amp-out" && y.node === "spk")
      return { type: "drive", amp: x.id, channel: x.port, speaker: y.id, section: y.port };
    if (x.node === "dsp" && y.node === "spk")
      return { type: "direct", output: x.port, speaker: y.id, section: y.port };
  }
  return null;
}

/** Add a wire; an amplifier input or a speaker section takes one signal: its previous wire
 * goes. A newly used output plays the first source, L+R. */
export function connect(draft: Draft, wire: Wire): void {
  draft.wires = draft.wires.filter((w) => {
    if (wire.type === "feed") return !(w.type === "feed" && w.amp === wire.amp && w.channel === wire.channel);
    if (w.type === "feed") return true;
    return !(w.speaker === wire.speaker && w.section === wire.section);
  });
  draft.wires.push(wire);
  if (wire.type !== "drive" && draft.routes[wire.output] === undefined)
    draft.routes[wire.output] = routeOf(draft, wire.output);
}

export function sameWire(a: Wire, b: Wire): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function disconnect(draft: Draft, wire: Wire): void {
  draft.wires = draft.wires.filter((w) => !sameWire(w, wire));
}

// --- ways ------------------------------------------------------------------------------------

export function num(text: Num): number {
  return text.trim() === "" ? NaN : Number(text.replace(",", "."));
}

const positive = (v: number) => Number.isFinite(v) && v > 0;

/** One amplifier channel (or an active speaker's direct feed) of a way's output. */
export interface ChannelLoad {
  output: number;
  amp: AmpNode | null; // null: active speakers, fed directly
  channel: number;
  cabinets: number;
}

export interface WayInfo {
  key: string; // "kindId/section"
  kind: Kind;
  index: number;
  section: Section;
  outputs: number[];
  channels: ChannelLoad[];
  cabinets: number;
  active: boolean;
}

export interface Wiring {
  ways: WayInfo[];
  /** Way key of each used output. */
  wayOf: Map<number, string>;
  errors: string[];
}

const wayKey = (kind: number, section: number) => `${kind}/${section}`;

/** The ways the plan's wiring makes, and what is wrong with it. */
export function wiring(draft: Draft, topo: Topology): Wiring {
  const errors: string[] = [];
  const kindOf = new Map(draft.speakers.map((s) => [s.id, s.kind]));
  const kinds = new Map(draft.kinds.map((k) => [k.id, k]));
  const amps = new Map(draft.amps.map((a) => [a.id, a]));
  // What each amplifier channel drives.
  const driven = new Map<string, { key: string; count: number }[]>();
  for (const w of draft.wires) {
    if (w.type !== "drive") continue;
    const kind = kindOf.get(w.speaker);
    if (kind === undefined) continue;
    const list = driven.get(`${w.amp}:${w.channel}`) ?? [];
    const key = wayKey(kind, w.section);
    const entry = list.find((e) => e.key === key);
    if (entry) entry.count++;
    else list.push({ key, count: 1 });
    driven.set(`${w.amp}:${w.channel}`, list);
  }
  for (const [ch, list] of driven) {
    if (list.length > 1) {
      const [ampId = 0, channel = 0] = ch.split(":").map(Number);
      errors.push(`${amps.get(ampId)?.model ?? "Amplifier"} ch ${channel + 1} drives two kinds of speakers.`);
    }
  }
  const ways = new Map<string, WayInfo>();
  const wayOf = new Map<number, string>();
  for (let o = 0; o < topo.outputs; o++) {
    const loads: { key: string; load: ChannelLoad }[] = [];
    for (const w of draft.wires) {
      if (w.type === "feed" && w.output === o) {
        for (const d of driven.get(`${w.amp}:${w.channel}`) ?? [])
          loads.push({
            key: d.key,
            load: { output: o, amp: amps.get(w.amp) ?? null, channel: w.channel, cabinets: d.count },
          });
      } else if (w.type === "direct" && w.output === o) {
        const kind = kindOf.get(w.speaker);
        if (kind !== undefined)
          loads.push({ key: wayKey(kind, w.section), load: { output: o, amp: null, channel: 0, cabinets: 1 } });
      }
    }
    const keys = [...new Set(loads.map((l) => l.key))];
    if (keys.length === 0) continue;
    if (keys.length > 1) {
      errors.push(`Out ${o + 1} drives two kinds of speakers: give each its own output.`);
      continue;
    }
    const key = keys[0]!;
    const [kindId = 0, index = 0] = key.split("/").map(Number);
    const kind = kinds.get(kindId);
    const section = kind?.sections[index];
    if (!kind || !section) continue;
    let way = ways.get(key);
    if (!way) {
      way = { key, kind, index, section, outputs: [], channels: [], cabinets: 0, active: false };
      ways.set(key, way);
    }
    way.outputs.push(o);
    wayOf.set(o, key);
    for (const { load } of loads) {
      // Several active cabinets on one output: one feed with several cabinets.
      const same = load.amp === null && way.channels.find((c) => c.amp === null && c.output === o);
      if (same) same.cabinets++;
      else way.channels.push(load);
      way.cabinets += load.cabinets;
    }
  }
  for (const way of ways.values()) {
    const direct = way.channels.filter((c) => c.amp === null).length;
    if (direct && direct < way.channels.length)
      errors.push(`${way.section.name}: some cabinets have an amplifier, some are fed directly (active).`);
    way.active = direct === way.channels.length;
  }
  return { ways: [...ways.values()], wayOf, errors };
}

/** Channel names of a way's outputs: its name, plus " L" / " R" when its outputs play one side
 * each, or a number when there are several of the same kind. */
export function outputNames(draft: Draft, way: WayInfo): Map<number, string> {
  const names = new Map<number, string>();
  const sides = way.outputs.map((o) => routeOf(draft, o).side);
  const distinct = new Set(sides).size === sides.length;
  way.outputs.forEach((o, i) => {
    const side = sides[i]!;
    if (way.outputs.length === 1) names.set(o, way.section.name);
    else if (distinct) names.set(o, side === "LR" ? way.section.name : `${way.section.name} ${side}`);
    else names.set(o, `${way.section.name}${i + 1}`);
  });
  return names;
}

// --- loads, limiters, levels -------------------------------------------------------------------

export function ampGain(amp: AmpNode): number {
  if (amp.gainMode === "gain") return num(amp.gainDb);
  return gainFromSensitivity(num(amp.sensitivityV), num(amp.sensitivityPowerW), num(amp.sensitivityOhm));
}

export function ampRatings(amp: AmpNode): Record<string, number> {
  return Object.fromEntries(Object.entries(amp.powerW).map(([load, w]) => [load, num(w)]));
}

export interface ChannelResult {
  load: ChannelLoad;
  impedanceOhm: number;
  aesW: number;
  powerW: number | null;
  limiter: LimiterResult | null;
  error: string | null;
}

/** The load and the limiter of one amplifier channel (cabinets in parallel). */
export function channelResult(section: Section, load: ChannelLoad): ChannelResult {
  const z = num(section.impedanceOhm);
  const aes = num(section.aesW);
  const n = load.cabinets;
  const base = { load, impedanceOhm: z / n, aesW: aes * n, powerW: null, limiter: null };
  if (load.amp === null) return { ...base, error: null };
  if (!positive(z) || !positive(aes)) return { ...base, error: "speaker power and impedance are needed" };
  const power = ampPowerAt(ampRatings(load.amp), z / n);
  const input = {
    speakerAesW: aes * n,
    impedanceOhm: z / n,
    ampGainDb: ampGain(load.amp),
    ampPowerW: power,
    load: section.load,
    mode: section.mode,
    rounding: section.rounding,
  };
  const error = validateLimiter(input);
  return { ...base, powerW: power, limiter: error ? null : computeLimiter(input), error };
}

export interface WayLevel {
  channels: ChannelResult[];
  /** The lowest of its channels' (its outputs are linked); null for active speakers. */
  limiter: LimiterResult | null;
  error: string | null;
  /** SPL at 1 m of all its cabinets at the limiter threshold. */
  splMaxDb: number | null;
  /** SPL for a mono programme at 0 dBu on the source, before the output gain. */
  splAt0Db: number | null;
}

export function wayLevel(draft: Draft, way: WayInfo): WayLevel {
  const channels = way.channels.map((c) => channelResult(way.section, c));
  const empty = { channels, limiter: null, splMaxDb: null, splAt0Db: null };
  if (way.active || channels.length === 0) return { ...empty, error: null };
  const error = channels.find((c) => c.error)?.error ?? null;
  if (error) return { ...empty, error };
  const limiter = channels
    .map((c) => c.limiter!)
    .reduce((low, l) => (l.compThresholdDbu < low.compThresholdDbu ? l : low));
  const sensitivity = num(way.section.sensitivityDb);
  if (!Number.isFinite(sensitivity)) return { ...empty, limiter, error: null };
  const sources = new Map(draft.sources.map((s) => [s.id, s]));
  // Power sum of every cabinet, each output at `level(output)` dBu.
  const spl = (level: (output: number) => number) => {
    let total = 0;
    for (const c of channels) {
      const volts = DBU_REF_V * 10 ** ((level(c.load.output) + ampGain(c.load.amp!)) / 20);
      const perCabinet = volts ** 2 / c.impedanceOhm / c.load.cabinets;
      total += c.load.cabinets * 10 ** ((sensitivity + 10 * Math.log10(perCabinet)) / 10);
    }
    return 10 * Math.log10(total);
  };
  const boost = (output: number) => {
    const route = routeOf(draft, output);
    return route.side === "LR" && sources.get(route.source ?? -1)?.stereo ? SUM_DB : 0;
  };
  return {
    channels,
    limiter,
    error: null,
    splMaxDb: spl(() => limiter.compThresholdDbu),
    splAt0Db: spl(boost),
  };
}

/** Output gain of each way: the main ways matched to the quietest one, the others at 0 dB; a
 * gain typed by hand wins. */
export function wayGains(
  draft: Draft,
  ways: WayInfo[],
): Map<string, { gainDb: number; computed: number }> {
  const levels = new Map(ways.map((w) => [w.key, wayLevel(draft, w)]));
  const aligned = ways
    .filter((w) => !w.section.aux)
    .map((w) => levels.get(w.key)?.splAt0Db ?? null)
    .filter((v): v is number => v !== null);
  const reference = aligned.length ? Math.min(...aligned) : 0;
  const gains = new Map<string, { gainDb: number; computed: number }>();
  for (const way of ways) {
    const at0 = levels.get(way.key)?.splAt0Db ?? null;
    const computed = !way.section.aux && at0 !== null ? Math.round((reference - at0) * 10) / 10 : 0;
    const typed = num(way.section.gainDb);
    gains.set(way.key, { gainDb: Number.isFinite(typed) ? typed : computed, computed });
  }
  return gains;
}

// --- filters -----------------------------------------------------------------------------------

function centreHz(way: WayInfo): number {
  const low = num(way.section.lowHz);
  const high = num(way.section.highHz);
  return positive(low) && positive(high) ? Math.sqrt(low * high) : Infinity;
}

/** Main ways from low to high (by the centre of their range). */
export function mainWays(ways: WayInfo[]): WayInfo[] {
  return ways
    .filter((w) => !w.section.aux)
    .map((w, order) => ({ w, order, centre: centreHz(w) }))
    .sort((a, b) => (a.centre === b.centre ? a.order - b.order : a.centre - b.centre))
    .map(({ w }) => w);
}

export interface Boundary {
  key: string;
  lower: WayInfo;
  upper: WayInfo;
  proposedHz: number;
  /** The two speakers' ranges do not meet. */
  gap: boolean;
}

/** Crossover proposed between two ranges: the geometric mean of where they meet. */
export function proposeCrossover(lowerTopHz: number, upperBottomHz: number): number {
  return Math.round(Math.sqrt(lowerTopHz * upperBottomHz));
}

export function boundaries(ways: WayInfo[]): Boundary[] {
  const main = mainWays(ways);
  const result: Boundary[] = [];
  for (let i = 0; i + 1 < main.length; i++) {
    const lower = main[i]!;
    const upper = main[i + 1]!;
    const top = num(lower.section.highHz);
    const bottom = num(upper.section.lowHz);
    result.push({
      key: `${lower.key}|${upper.key}`,
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

/** Give every crossover and auxiliary way its own editable setting (from an event handler:
 * the computations only read the draft). */
export function ensureFilters(draft: Draft, ways: WayInfo[], slopes: string[]): void {
  for (const b of boundaries(ways)) draft.crossovers[b.key] ??= defaultCrossover(slopes);
  for (const way of ways.filter((w) => w.section.aux)) draft.aux[way.key] ??= defaultAux(slopes);
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
  ways: WayInfo[],
  slopes: string[],
): Map<string, { hpf: Filter | null; lpf: Filter | null }> {
  const filters = new Map<string, { hpf: Filter | null; lpf: Filter | null }>();
  const main = mainWays(ways);
  for (const way of main) filters.set(way.key, { hpf: null, lpf: null });
  const lowest = main[0];
  if (lowest) {
    const bottom = num(lowest.section.lowHz);
    filters.get(lowest.key)!.hpf = resolved(draft.subsonic, positive(bottom) ? bottom : 30);
  }
  for (const b of boundaries(ways)) {
    const filter = resolved(draft.crossovers[b.key] ?? defaultCrossover(slopes), b.proposedHz);
    filters.get(b.lower.key)!.lpf = filter;
    filters.get(b.upper.key)!.hpf = filter;
  }
  for (const way of ways.filter((w) => w.section.aux)) {
    const setting = draft.aux[way.key] ?? defaultAux(slopes);
    const bottom = num(way.section.lowHz);
    const top = num(way.section.highHz);
    filters.set(way.key, {
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

export function sourceChannelNames(source: Source): string[] {
  return source.stereo ? [`${source.name} L`, `${source.name} R`] : [source.name];
}

/** Problems that keep the wizard from going on, per step (the input EQ is set at the last). */
export function inputErrors(draft: Draft, topo: Topology): string[] {
  const errors: string[] = [];
  if (draft.sources.length === 0) errors.push("Add a source.");
  if (inputsNeeded(draft) > topo.inputs)
    errors.push(`The sources need ${inputsNeeded(draft)} inputs, this DSP has ${topo.inputs}.`);
  for (const s of draft.sources) {
    for (const name of sourceChannelNames(s)) {
      const e = nameError(name, CHANNEL_NAME_LENGTH);
      if (e) errors.push(`Source "${s.name}": ${e} (channel name "${name}").`);
    }
  }
  return errors;
}

export function planErrors(draft: Draft, topo: Topology): string[] {
  const w = wiring(draft, topo);
  const errors = [...w.errors];
  if (w.ways.length === 0)
    errors.push(
      "Wire at least one DSP output to a speaker, through an amplifier channel (or directly for an active speaker).",
    );
  const sources = new Set(draft.sources.map((s) => s.id));
  const amps = new Set<AmpNode>();
  for (const way of w.ways) {
    const s = way.section;
    const label = s.name || way.kind.model;
    for (const [o, name] of outputNames(draft, way)) {
      const e = nameError(name, CHANNEL_NAME_LENGTH);
      if (e) errors.push(`Out ${o + 1}: ${e} (channel name "${name}").`);
      const route = routeOf(draft, o);
      if (route.source === null || !sources.has(route.source)) errors.push(`Out ${o + 1}: pick what it plays.`);
    }
    if (!positive(num(s.lowHz)) || !positive(num(s.highHz)))
      errors.push(`${label}: the speaker's frequency range is needed.`);
    else if (num(s.lowHz) >= num(s.highHz)) errors.push(`${label}: the range's bottom must be below its top.`);
    if (way.active) continue;
    for (const c of way.channels) if (c.amp) amps.add(c.amp);
    if (!positive(num(s.aesW))) errors.push(`${label}: the speaker's AES power is needed.`);
    if (!positive(num(s.impedanceOhm))) errors.push(`${label}: the speaker's impedance is needed.`);
    if (!Number.isFinite(num(s.sensitivityDb))) errors.push(`${label}: the speaker's sensitivity is needed.`);
  }
  for (const amp of amps) if (!Number.isFinite(ampGain(amp))) errors.push(`${amp.model}: its gain is needed.`);
  if (errors.length === 0) {
    for (const way of w.ways) {
      const error = wayLevel(draft, way).error;
      if (error) errors.push(`${way.section.name}: ${error}.`);
    }
  }
  return [...new Set(errors)];
}

export function filterErrors(draft: Draft, topo: Topology): string[] {
  const { ways } = wiring(draft, topo);
  const errors: string[] = [];
  for (const [key, f] of wayFilters(draft, ways, topo.slopes)) {
    const way = ways.find((w) => w.key === key);
    if (way && f.hpf && f.lpf && f.hpf.freq_hz >= f.lpf.freq_hz)
      errors.push(`${way.section.name}: the high-pass is above the low-pass.`);
  }
  return errors;
}

export function storeErrors(draft: Draft, topo: Topology): string[] {
  const errors: string[] = [];
  if (!(draft.slot >= 1 && draft.slot <= topo.presets)) errors.push("Pick a preset slot.");
  const e = nameError(draft.presetName, PRESET_NAME_LENGTH);
  if (e) errors.push(`Preset name: ${e}.`);
  if (draft.lowShelf.enabled) {
    const f = num(draft.lowShelf.freqHz);
    const g = num(draft.lowShelf.gainDb);
    if (!positive(f)) errors.push("Low shelf: a frequency is needed.");
    if (!Number.isFinite(g) || g < -12 || g > 12) errors.push("Low shelf: gain between −12 and +12 dB.");
  }
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

/** The inputs an output plays (its matrix). */
export function outputMatrix(draft: Draft, output: number, inputs: number): boolean[] {
  const route = routeOf(draft, output);
  const source = draft.sources.find((s) => s.id === route.source);
  const ins = sourceInputs(draft).get(route.source ?? -1) ?? [];
  const picked = source?.stereo && route.side !== "LR" ? [ins[route.side === "L" ? 0 : 1]] : ins;
  const matrix = Array<boolean>(inputs).fill(false);
  for (const i of picked) if (i !== undefined && i < inputs) matrix[i] = true;
  return matrix;
}

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
    sourceChannelNames(source).forEach((name, k) => {
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
  const { ways } = wiring(draft, topo);
  const filters = wayFilters(draft, ways, topo.slopes);
  const gains = wayGains(draft, ways);
  for (const way of ways) {
    const level = wayLevel(draft, way);
    const names = outputNames(draft, way);
    const f = filters.get(way.key);
    for (const o of way.outputs) {
      outputs[o] = {
        name: names.get(o) ?? way.section.name,
        used: true,
        sources: outputMatrix(draft, o, topo.inputs),
        gain_db: gains.get(way.key)?.gainDb ?? 0,
        phase: way.section.phase,
        hpf: f?.hpf ?? null,
        lpf: f?.lpf ?? null,
        dynamics: level.limiter
          ? {
              compressor_threshold_db: level.limiter.compThresholdDbu,
              limiter_threshold_db: level.limiter.limitThresholdDbu,
            }
          : null,
      };
    }
    if (way.outputs.length > 1) outputLinks.push([...way.outputs]);
  }
  outputLinks.sort((a, b) => a[0]! - b[0]!);
  return { inputs, outputs, input_links: inputLinks, output_links: outputLinks };
}
