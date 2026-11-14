import { describe, expect, it } from "vitest";
import {
  addAmp,
  addSpeaker,
  AMPLIFIERS,
  ampPowerAt,
  boundaries,
  buildPlan,
  connect,
  disconnect,
  type Draft,
  duplicateSpeaker,
  ensureFilters,
  filterErrors,
  gainFromSensitivity,
  inputErrors,
  mainWays,
  newDraft,
  outputNames,
  parsePort,
  planErrors,
  portKey,
  proposeCrossover,
  removeNode,
  setAmpChannels,
  storeErrors,
  type Topology,
  wayFilters,
  wayGains,
  wayLevel,
  wireBetween,
  wiring,
} from "./setup";

const SLOPES = ["Off", "BW-6", "BL-6", "BW-12", "BL-12", "LR-12", "BW-18", "BL-18", "BW-24",
  "BL-24", "LR-24", "BW-30", "BL-30", "BW-36", "BL-36", "LR-36", "BW-42", "BL-42", "BW-48",
  "BL-48", "LR-48"];
const DSP408: Topology = { inputs: 4, outputs: 8, presets: 20, slopes: SLOPES };
const BW24 = 8;
const LR24 = 10;
const ad42 = AMPLIFIERS.find((a) => a.id === "admark-ad42")!;

/** The owner's system: four TH1821 on an AD42 (two per channel, two outputs, mono), MKH-230
 * kicks and bi-amped T24N clones in stereo on two AD416. */
function ownerStack(): Draft {
  const d = newDraft(SLOPES);
  const sub = addAmp(d, "admark-ad42", 300, 0);
  const mid = addAmp(d, "admark-ad416", 300, 200);
  const high = addAmp(d, "admark-ad416", 300, 400);
  const feed = (output: number, amp: number, channel: number, side: "L" | "R" | "LR") => {
    connect(d, { type: "feed", output, amp, channel });
    d.routes[output]!.side = side;
  };
  const drive = (amp: number, channel: number, speaker: number, section = 0) =>
    connect(d, { type: "drive", amp, channel, speaker, section });
  for (let n = 0; n < 4; n++) drive(sub.id, n >> 1, addSpeaker(d, "th1821", 600, n * 60).id);
  const kicks = [addSpeaker(d, "mkh230", 600, 300), addSpeaker(d, "mkh230", 600, 360)];
  const tops = [addSpeaker(d, "t24n-clone", 600, 420), addSpeaker(d, "t24n-clone", 600, 500)];
  feed(0, sub.id, 0, "LR");
  feed(1, sub.id, 1, "LR");
  feed(2, mid.id, 0, "L");
  feed(3, mid.id, 1, "R");
  feed(4, mid.id, 2, "L");
  feed(5, mid.id, 3, "R");
  feed(6, high.id, 0, "L");
  feed(7, high.id, 1, "R");
  drive(mid.id, 0, kicks[0]!.id);
  drive(mid.id, 1, kicks[1]!.id);
  drive(mid.id, 2, tops[0]!.id, 0);
  drive(mid.id, 3, tops[1]!.id, 0);
  drive(high.id, 0, tops[0]!.id, 1);
  drive(high.id, 1, tops[1]!.id, 1);
  d.slot = 5;
  d.presetName = "Owner";
  return d;
}

const wayNamed = (d: Draft, name: string) =>
  wiring(d, DSP408).ways.find((w) => w.section.name === name)!;

describe("library", () => {
  it("gives an amplifier's power at a load, on the safe side", () => {
    expect(ampPowerAt(ad42.power_w, 8)).toBe(4200);
    expect(ampPowerAt(ad42.power_w, 4)).toBe(7800);
    expect(ampPowerAt(ad42.power_w, 5.3)).toBe(4200); // between 4 and 8 Ω: the 8 Ω rating
    expect(ampPowerAt(ad42.power_w, 16)).toBe(2100); // above 8 Ω: constant voltage
    expect(ampPowerAt(ad42.power_w, 1)).toBeNull(); // below its lowest rated load
    expect(ampPowerAt({ "8": NaN }, 8)).toBeNull(); // not rated
  });

  it("pre-fills the highest listed gain and the ratings", () => {
    const d = newDraft(SLOPES);
    const amp = addAmp(d, "admark-ad42", 0, 0);
    expect([amp.gainDb, amp.channels, amp.powerW["4"]]).toEqual(["41", 2, "7800"]);
    expect(addAmp(d, null, 0, 0).gainDb).toBe("");
  });

  it("turns an input sensitivity into a gain", () => {
    // 1.4 V for 1600 W into 8 Ω: √12800 = 113 V, i.e. 38.15 dB
    expect(gainFromSensitivity(1.4, 1600, 8)).toBeCloseTo(38.15, 2);
  });

  it("shares a library model's specs between its cabinets", () => {
    const d = newDraft(SLOPES);
    const a = addSpeaker(d, "th1821", 0, 0);
    const b = addSpeaker(d, "th1821", 0, 0);
    const c = duplicateSpeaker(d, a);
    expect(new Set([a.kind, b.kind, c.kind]).size).toBe(1);
    expect(addSpeaker(d, null, 0, 0).kind).not.toBe(a.kind); // a generic speaker: its own
    removeNode(d, "speaker", a.id);
    removeNode(d, "speaker", b.id);
    expect(d.kinds).toHaveLength(2);
    removeNode(d, "speaker", c.id);
    expect(d.kinds).toHaveLength(1);
  });
});

describe("wiring", () => {
  it("joins ports in either order, and only the right ones", () => {
    const out = { node: "dsp", port: 2 } as const;
    const ampIn = { node: "amp-in", id: 7, port: 1 } as const;
    expect(wireBetween(ampIn, out)).toEqual({ type: "feed", output: 2, amp: 7, channel: 1 });
    expect(wireBetween(out, { node: "spk", id: 9, port: 0 })?.type).toBe("direct");
    expect(wireBetween(ampIn, { node: "spk", id: 9, port: 0 })).toBeNull();
    expect(parsePort(portKey(ampIn))).toEqual(ampIn);
  });

  it("deduces the ways from the wiring", () => {
    const d = ownerStack();
    const { ways, errors } = wiring(d, DSP408);
    expect(errors).toEqual([]);
    expect(mainWays(ways).map((w) => [w.section.name, w.outputs, w.cabinets])).toEqual([
      ["Sub", [0, 1], 4],
      ["Kick", [2, 3], 2],
      ["Low", [4, 5], 2],
      ["High", [6, 7], 2],
    ]);
    expect([...outputNames(d, wayNamed(d, "Sub")).values()]).toEqual(["Sub1", "Sub2"]);
    expect([...outputNames(d, wayNamed(d, "Kick")).values()]).toEqual(["Kick L", "Kick R"]);
  });

  it("gives an amplifier input or a speaker one signal", () => {
    const d = ownerStack();
    const amp = d.amps[0]!.id;
    connect(d, { type: "feed", output: 7, amp, channel: 0 });
    expect(d.wires.filter((w) => w.type === "feed" && w.amp === amp && w.channel === 0)).toEqual([
      { type: "feed", output: 7, amp, channel: 0 },
    ]);
    disconnect(d, { type: "feed", output: 7, amp, channel: 0 });
    expect(wayNamed(d, "Sub").outputs).toEqual([1]);
  });

  it("refuses an output or an amplifier channel on two kinds of speakers", () => {
    const d = ownerStack();
    const [sub, mid] = d.amps;
    connect(d, { type: "feed", output: 0, amp: mid!.id, channel: 0 }); // Out 1 also to the kicks
    expect(wiring(d, DSP408).errors).toContain(
      "Out 1 drives two kinds of speakers: give each its own output.",
    );
    const kick = d.speakers.find((s) => d.kinds.find((k) => k.id === s.kind)?.ref === "mkh230")!;
    connect(d, { type: "drive", amp: sub!.id, channel: 1, speaker: kick.id, section: 0 });
    expect(wiring(d, DSP408).errors).toContain("Admark AD42 ch 2 drives two kinds of speakers.");
  });

  it("drops the wires of a removed amplifier or channel", () => {
    const d = ownerStack();
    const mid = d.amps[1]!;
    setAmpChannels(d, mid, 2);
    expect(d.wires.some((w) => w.type !== "direct" && w.amp === mid.id && w.channel >= 2)).toBe(
      false,
    );
    removeNode(d, "amp", mid.id);
    expect(d.wires.some((w) => w.type !== "direct" && w.amp === mid.id)).toBe(false);
  });

  it("treats speakers wired straight to an output as active", () => {
    const d = newDraft(SLOPES);
    const spk = addSpeaker(d, null, 0, 0);
    connect(d, { type: "direct", output: 0, speaker: spk.id, section: 0 });
    const [way] = wiring(d, DSP408).ways;
    expect(way?.active).toBe(true);
    expect(wayLevel(d, way!).limiter).toBeNull();
  });
});

describe("filters", () => {
  it("proposes the crossovers between the main ways", () => {
    const d = ownerStack();
    const { ways } = wiring(d, DSP408);
    expect(boundaries(ways).map((b) => b.proposedHz)).toEqual([105, 180, 1200]);
    expect(proposeCrossover(143, 77)).toBe(105);
    const f = wayFilters(d, ways, SLOPES);
    expect(f.get(wayNamed(d, "Sub").key)).toEqual({
      hpf: { freq_hz: 38, slope: BW24 },
      lpf: { freq_hz: 105, slope: LR24 },
    });
    expect(f.get(wayNamed(d, "High").key)).toEqual({
      hpf: { freq_hz: 1200, slope: LR24 },
      lpf: null,
    });
  });

  it("uses a crossover typed by hand on both sides", () => {
    const d = ownerStack();
    const { ways } = wiring(d, DSP408);
    ensureFilters(d, ways, SLOPES);
    const b = boundaries(ways)[1]!;
    d.crossovers[b.key]!.freqHz = "130";
    const f = wayFilters(d, ways, SLOPES);
    expect(f.get(b.lower.key)!.lpf?.freq_hz).toBe(130);
    expect(f.get(b.upper.key)!.hpf?.freq_hz).toBe(130);
  });

  it("filters an auxiliary way to its speaker's range", () => {
    const d = ownerStack();
    const amp = addAmp(d, "admark-ad42", 0, 0);
    const mon = addSpeaker(d, null, 0, 0);
    const kind = d.kinds.find((k) => k.id === mon.kind)!;
    Object.assign(kind.sections[0]!, {
      name: "Mon",
      aux: true,
      lowHz: "80",
      highHz: "18000",
      aesW: "300",
    });
    // The DSP 408 has 8 outputs: the monitor takes Out 8 from High R.
    disconnect(d, { type: "feed", output: 7, amp: d.amps[2]!.id, channel: 1 });
    connect(d, { type: "feed", output: 7, amp: amp.id, channel: 0 });
    connect(d, { type: "drive", amp: amp.id, channel: 0, speaker: mon.id, section: 0 });
    const { ways } = wiring(d, DSP408);
    expect(wayFilters(d, ways, SLOPES).get(`${kind.id}/0`)).toEqual({
      hpf: { freq_hz: 80, slope: BW24 },
      lpf: { freq_hz: 18000, slope: BW24 },
    });
    expect(mainWays(ways).map((w) => w.section.name)).not.toContain("Mon");
  });
});

describe("levels", () => {
  it("computes each channel's limiter, the way taking the lowest", () => {
    const d = ownerStack();
    const level = wayLevel(d, wayNamed(d, "Sub"));
    // Two TH1821 per AD42 channel: 3400 W AES / 1.56 into 4 Ω at 41 dB, 0.6 dBu, rounded up
    expect(level.channels.map((c) => [c.impedanceOhm, c.aesW, c.powerW])).toEqual([
      [4, 3400, 7800],
      [4, 3400, 7800],
    ]);
    expect(level.limiter?.compThresholdDbu).toBe(1);
    expect(level.limiter?.limitThresholdDbu).toBe(7);
    // 1 dBu + 41 dB = 97.6 V: 1190 W per cabinet, 104.8 + 30.8 dB, four cabinets +6 dB
    expect(level.splMaxDb).toBeCloseTo(141.58, 1);
    // A mono programme: L + R summed on the sub outputs, +6 dB
    expect(level.splAt0Db).toBeCloseTo(146.59, 1);
  });

  it("turns the louder main ways down to the quietest", () => {
    const d = ownerStack();
    const { ways } = wiring(d, DSP408);
    const gains = wayGains(d, ways);
    const levels = ways.map((w) => wayLevel(d, w).splAt0Db! + gains.get(w.key)!.gainDb);
    for (const level of levels) expect(level).toBeCloseTo(Math.min(...levels), 0);
    expect(Math.max(...[...gains.values()].map((g) => g.gainDb))).toBe(0);
  });

  it("keeps a gain typed by hand and leaves auxiliary ways at 0 dB", () => {
    const d = ownerStack();
    const { ways } = wiring(d, DSP408);
    ways[0]!.section.gainDb = "-2";
    ways[1]!.section.aux = true;
    const gains = wayGains(d, ways);
    expect(gains.get(ways[0]!.key)!.gainDb).toBe(-2);
    expect(gains.get(ways[1]!.key)!.gainDb).toBe(0);
  });
});

describe("plan", () => {
  it("builds the plan the server loads", () => {
    const d = ownerStack();
    d.lowShelf.enabled = true;
    const plan = buildPlan(d, DSP408);
    expect(plan.inputs.map((i) => i.name)).toEqual(["Main L", "Main R", "InC", "InD"]);
    expect(plan.inputs[0]!.low_shelf).toEqual({ freq_hz: 100, gain_db: 3 });
    expect(plan.inputs[2]!.low_shelf).toBeNull();
    expect(plan.input_links).toEqual([[0, 1]]);
    expect(plan.outputs.map((o) => o.name)).toEqual([
      "Sub1", "Sub2", "Kick L", "Kick R", "Low L", "Low R", "High L", "High R",
    ]);
    expect(plan.outputs.map((o) => o.sources.slice(0, 2))).toEqual([
      [true, true], [true, true], [true, false], [false, true], [true, false], [false, true],
      [true, false], [false, true],
    ]);
    expect(plan.output_links).toEqual([[0, 1], [2, 3], [4, 5], [6, 7]]);
    expect(plan.outputs[0]!.dynamics).toEqual({
      compressor_threshold_db: 1,
      limiter_threshold_db: 7,
    });
  });

  it("leaves the outputs not wired unused", () => {
    const d = ownerStack();
    removeNode(d, "amp", d.amps[2]!.id);
    const plan = buildPlan(d, DSP408);
    expect(plan.outputs.slice(6).map((o) => [o.name, o.used])).toEqual([
      ["Out7", false],
      ["Out8", false],
    ]);
  });

  it("checks every step", () => {
    const d = ownerStack();
    expect(inputErrors(d, DSP408)).toEqual([]);
    expect(planErrors(d, DSP408)).toEqual([]);
    expect(filterErrors(d, DSP408)).toEqual([]);
    expect(storeErrors(d, DSP408)).toEqual([]);

    d.sources.push(
      { id: 90, name: "Microphone", stereo: true },
      { id: 91, name: "DJ", stereo: false },
    );
    expect(inputErrors(d, DSP408)).toEqual([
      "The sources need 5 inputs, this DSP has 4.",
      'Source "Microphone": 8 characters at most (channel name "Microphone L").',
      'Source "Microphone": 8 characters at most (channel name "Microphone R").',
    ]);
    d.amps[0]!.gainDb = "";
    d.routes[2]!.source = null;
    expect(planErrors(d, DSP408)).toEqual([
      "Out 3: pick what it plays.",
      "Admark AD42: its gain is needed.",
    ]);
    expect(planErrors(newDraft(SLOPES), DSP408)).toHaveLength(1);
    d.slot = 0;
    d.presetName = "";
    d.lowShelf = { enabled: true, freqHz: "", gainDb: "15" };
    expect(storeErrors(d, DSP408)).toEqual([
      "Pick a preset slot.",
      "Preset name: a name is required.",
      "Low shelf: a frequency is needed.",
      "Low shelf: gain between −12 and +12 dB.",
    ]);
  });
});
