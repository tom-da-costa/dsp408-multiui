// One colour per channel, the same in every view (strips, chips, graphs, link groups). Fixed by
// position, so "Out 3" has the same colour on a DSP 408, 206 or 204. Linked channels share the
// colour of the lowest-numbered channel of their group. None of these is the green, blue or
// orange used for a channel's own response curves.

const INPUT_COLORS = ["#f783ac", "#91a7ff", "#ffd8a8", "#d0bfff"]; // In A-D
// Out 1-8
const OUTPUT_COLORS = ["#ff6b6b", "#e599f7", "#66d9e8", "#c0eb75", "#ffe066", "#ffffff", "#fcc2d7", "#b2f2bb"]; // prettier-ignore

/** Colour of `path` ("inputs.0" / "outputs.3"), given the other members of its link group. */
export function channelColor(path: string, linked: readonly number[] = []): string {
  const [side, n] = path.split(".");
  const lead = Math.min(Number(n), ...linked);
  const colors = side === "outputs" ? OUTPUT_COLORS : INPUT_COLORS;
  return colors[lead % colors.length]!;
}
