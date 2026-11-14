import { describe, expect, it } from "vitest";
import {
  AMPLIFIERS,
  ampPowerAt,
  boundaries,
  buildPlan,
  type Draft,
  ensureFilters,
  filterErrors,
  gainFromSensitivity,
  inputErrors,
  mainWays,
  newDraft,
  newWay,
  proposeCrossover,
  speakerErrors,
  speakerFromLibrary,
  SPEAKERS,
  storeErrors,
  systemErrors,
  type Topology,
  useAmplifier,
  wayFilters,
  wayGains,
  wayLevel,
  wayOutputs,
} from "./setup";

const SLOPES = ["Off", "BW-6", "BL-6", "BW-12", "BL-12", "LR-12", "BW-18", "BL-18", "BW-24",
  "BL-24", "LR-24", "BW-30", "BL-30", "BW-36", "BL-36", "LR-36", "BW-42", "BL-42", "BW-48",
  "BL-48", "LR-48"];
const DSP408: Topology = { inputs: 4, outputs: 8, presets: 20, slopes: SLOPES };
const BW24 = 8;
const LR24 = 10;

const model = (id: string) => SPEAKERS.find((m) => m.id === id)!;
const ad42 = AMPLIFIERS.find((a) => a.id === "admark-ad42")!;
const ad416 = AMPLIFIERS.find((a) => a.id === "admark-ad416")!;

/** The owner's stack: TH1821 subs (mono), MKH-230 kicks and bi-amped T24N clones (stereo). */
function ownerStack(): Draft {
  const draft = newDraft(SLOPES);
  const add = (id: string, section: number, name: string, stereo: boolean) => {
    const way = newWay(draft.nextId++, name, speakerFromLibrary(model(id), section), [1]);
    way.stereo = stereo;
    draft.ways.push(way);
    return way;
  };
  // Listed out of order: the wizard sorts the ways from low to high.
  const high = add("t24n-clone", 1, "High", true);
  const sub = add("th1821", 0, "Sub", false);
  const kick = add("mkh230", 0, "Kick", true);
  const low = add("t24n-clone", 0, "Low", true);
  useAmplifier(sub, ad42);
  useAmplifier(kick, ad416);
  useAmplifier(low, ad416);
  useAmplifier(high, ad416);
  draft.slot = 5;
  draft.presetName = "Owner";
  return draft;
}

describe("library", () => {
  it("gives an amplifier's power at a load, on the safe side", () => {
    expect(ampPowerAt(ad42, 8)).toBe(4200);
    expect(ampPowerAt(ad42, 4)).toBe(7800);
    expect(ampPowerAt(ad42, 5.3)).toBe(4200); // between 4 and 8 Ω: the 8 Ω rating
    expect(ampPowerAt(ad42, 16)).toBe(2100); // above 8 Ω: constant voltage
    expect(ampPowerAt(ad42, 1)).toBeNull(); // below its lowest rated load
  });

  it("pre-fills the highest listed gain", () => {
    const way = newWay(1, "Sub", speakerFromLibrary(model("th1821"), 0), [1]);
    useAmplifier(way, ad42);
    expect(way.amp.gainDb).toBe("41");
    expect(way.amp.powerW).toBe("4200");
  });

  it("turns an input sensitivity into a gain", () => {
    // 1.4 V for 1600 W into 8 Ω: √12800 = 113 V, i.e. 38.15 dB
    expect(gainFromSensitivity(1.4, 1600, 8)).toBeCloseTo(38.15, 2);
  });
});

describe("ways and filters", () => {
  it("orders the main ways from low to high and proposes the crossovers", () => {
    const draft = ownerStack();
    expect(mainWays(draft).map((w) => w.name)).toEqual(["Sub", "Kick", "Low", "High"]);
    expect(boundaries(draft).map((b) => b.proposedHz)).toEqual([105, 180, 1200]);
    expect(proposeCrossover(143, 77)).toBe(105);
  });

  it("filters every way: subsonic, crossovers, nothing above the top way", () => {
    const draft = ownerStack();
    const f = wayFilters(draft, SLOPES);
    const byName = (name: string) => f.get(draft.ways.find((w) => w.name === name)!.id)!;
    expect(byName("Sub")).toEqual({
      hpf: { freq_hz: 38, slope: BW24 },
      lpf: { freq_hz: 105, slope: LR24 },
    });
    expect(byName("Kick").hpf).toEqual({ freq_hz: 105, slope: LR24 });
    expect(byName("High")).toEqual({ hpf: { freq_hz: 1200, slope: LR24 }, lpf: null });
  });

  it("uses a crossover typed by hand on both sides", () => {
    const draft = ownerStack();
    ensureFilters(draft, SLOPES);
    const key = boundaries(draft)[1]!.key;
    draft.crossovers[key]!.freqHz = "130";
    const f = wayFilters(draft, SLOPES);
    const [kick, low] = [boundaries(draft)[1]!.lower, boundaries(draft)[1]!.upper];
    expect(f.get(kick.id)!.lpf?.freq_hz).toBe(130);
    expect(f.get(low.id)!.hpf?.freq_hz).toBe(130);
  });

  it("filters an auxiliary way to its speaker's range", () => {
    const draft = ownerStack();
    const monitor = newWay(draft.nextId++, "Mon", speakerFromLibrary(model("t24n-clone"), 1), [1]);
    monitor.aux = true;
    monitor.speaker.lowHz = "80";
    monitor.speaker.highHz = "18000";
    draft.ways.push(monitor);
    expect(wayFilters(draft, SLOPES).get(monitor.id)).toEqual({
      hpf: { freq_hz: 80, slope: BW24 },
      lpf: { freq_hz: 18000, slope: BW24 },
    });
    expect(mainWays(draft)).not.toContain(monitor);
  });
});

describe("levels", () => {
  it("computes the limiter and the SPL at its threshold", () => {
    const draft = ownerStack();
    const sub = draft.ways.find((w) => w.name === "Sub")!;
    const level = wayLevel(sub);
    // 1700 W AES / 1.56 into 8 Ω at 41 dB: 0.6 dBu, rounded up to the 0.5 dB step
    expect(level.limiter?.compThresholdDbu).toBe(1);
    expect(level.limiter?.limitThresholdDbu).toBe(7);
    // 1 dBu + 41 dB = 97.6 V: 1190 W into 8 Ω, 104.8 + 30.8 dB
    expect(level.splMaxDb).toBeCloseTo(135.56, 1);
    expect(level.splAt0Db).toBeCloseTo(134.56, 1);
  });

  it("adds 3 dB per doubling of the cabinets", () => {
    const draft = ownerStack();
    const sub = draft.ways.find((w) => w.name === "Sub")!;
    const one = wayLevel(sub).splAt0Db!;
    // Two cabinets in parallel on the channel (4 Ω): each gets what one got alone, two boxes.
    sub.cabinets = 2;
    expect(wayLevel(sub).splAt0Db! - one).toBeCloseTo(3.01, 1);
    // In series (16 Ω): a quarter of the power each, two boxes.
    sub.wiring = "series";
    expect(wayLevel(sub).splAt0Db! - one).toBeCloseTo(-6.02 + 3.01, 1);
  });

  it("turns the louder main ways down to the quietest", () => {
    const draft = ownerStack();
    const gains = wayGains(draft);
    const levels = draft.ways.map((w) => wayLevel(w).splAt0Db! + gains.get(w.id)!.gainDb);
    for (const level of levels) expect(level).toBeCloseTo(Math.min(...levels), 0);
    expect(Math.max(...[...gains.values()].map((g) => g.gainDb))).toBe(0);
  });

  it("keeps a gain typed by hand and leaves the auxiliary ways at 0 dB", () => {
    const draft = ownerStack();
    draft.ways[0]!.gainDb = "-2";
    draft.ways[1]!.aux = true;
    const gains = wayGains(draft);
    expect(gains.get(draft.ways[0]!.id)!.gainDb).toBe(-2);
    expect(gains.get(draft.ways[1]!.id)!.gainDb).toBe(0);
  });

  it("sets no limiter on active speakers", () => {
    const draft = ownerStack();
    draft.ways[0]!.amp.active = true;
    expect(wayLevel(draft.ways[0]!)).toEqual({
      limiter: null,
      error: null,
      splMaxDb: null,
      splAt0Db: null,
    });
  });
});

describe("routing and plan", () => {
  it("assigns the outputs from low to high, L then R", () => {
    const draft = ownerStack();
    const outs = wayOutputs(draft, 8);
    const of = (name: string) => outs.get(draft.ways.find((w) => w.name === name)!.id);
    expect([of("Sub"), of("Kick"), of("Low"), of("High")]).toEqual([[0], [1, 2], [3, 4], [5, 6]]);
  });

  it("keeps outputs chosen by hand and flags a clash", () => {
    const draft = ownerStack();
    draft.ways.find((w) => w.name === "Sub")!.outputs = [7];
    const outs = wayOutputs(draft, 8);
    expect(outs.get(draft.ways.find((w) => w.name === "Sub")!.id)).toEqual([7]);
    expect(outs.get(draft.ways.find((w) => w.name === "Kick")!.id)).toEqual([0, 1]);
    draft.ways.find((w) => w.name === "High")!.outputs = [7, 6];
    expect(systemErrors(draft, DSP408)).toContain("Out 8 is used twice.");
  });

  it("builds the plan the server loads", () => {
    const draft = ownerStack();
    draft.lowShelf.enabled = true;
    const plan = buildPlan(draft, DSP408);
    expect(plan.inputs.map((i) => i.name)).toEqual(["Mix L", "Mix R", "InC", "InD"]);
    expect(plan.inputs[0]!.low_shelf).toEqual({ freq_hz: 100, gain_db: 3 });
    expect(plan.inputs[2]!.low_shelf).toBeNull();
    expect(plan.input_links).toEqual([[0, 1]]);
    expect(plan.outputs.map((o) => o.name)).toEqual([
      "Sub", "Kick L", "Kick R", "Low L", "Low R", "High L", "High R", "Out8",
    ]);
    // Mono sub: L + R; stereo ways: L on the left, R on the right.
    expect(plan.outputs.map((o) => o.sources.slice(0, 2))).toEqual([
      [true, true], [true, false], [false, true], [true, false], [false, true], [true, false],
      [false, true], [false, false],
    ]);
    expect(plan.outputs.map((o) => o.used)).toEqual([true, true, true, true, true, true, true, false]);
    expect(plan.output_links).toEqual([[1, 2], [3, 4], [5, 6]]);
    expect(plan.outputs[0]!.dynamics).toEqual({
      compressor_threshold_db: 1,
      limiter_threshold_db: 7,
    });
    expect(plan.outputs[7]!.dynamics).toBeNull();
  });

  it("checks every step", () => {
    const draft = ownerStack();
    expect(inputErrors(draft, DSP408)).toEqual([]);
    expect(systemErrors(draft, DSP408)).toEqual([]);
    expect(speakerErrors(draft)).toEqual([]);
    expect(filterErrors(draft, SLOPES)).toEqual([]);
    expect(storeErrors(draft, DSP408)).toEqual([]);

    draft.sources.push({ id: 9, name: "Microphone", stereo: true }, { id: 10, name: "DJ", stereo: false });
    expect(inputErrors(draft, DSP408)).toEqual([
      "The sources need 5 inputs, this DSP has 4.",
      'Source "Microphone": 8 characters at most (channel name "Microphone L").',
      'Source "Microphone": 8 characters at most (channel name "Microphone R").',
    ]);
    const fill = newWay(99, "Fill", speakerFromLibrary(model("th1821"), 0), []);
    fill.stereo = true;
    draft.ways.push(fill);
    expect(systemErrors(draft, DSP408)).toEqual([
      "The ways need 9 outputs, this DSP has 8.",
      'Way "Fill": pick its source.',
    ]);
    draft.ways[0]!.amp.gainDb = "";
    expect(speakerErrors(draft)).toContain("High: the amplifier's gain is needed.");
    draft.slot = 0;
    draft.presetName = "";
    expect(storeErrors(draft, DSP408)).toEqual([
      "Pick a preset slot.",
      "Preset name: a name is required.",
    ]);
  });
});
