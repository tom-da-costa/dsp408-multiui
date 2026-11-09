import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HOLD_DELAY_MS, holdRepeat, repeatInterval, repeatSteps } from "./repeat";

// No DOM in these tests: Node's EventTarget stands in for the button.
function button(): HTMLElement {
  return new EventTarget() as unknown as HTMLElement;
}

function press(node: HTMLElement, type: string) {
  node.dispatchEvent(Object.assign(new Event(type, { cancelable: true }), { button: 0, pointerId: 1 }));
}

function click(node: HTMLElement, detail: number) {
  node.dispatchEvent(Object.assign(new Event("click"), { detail }));
}

describe("holdRepeat", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("steps once on a tap, then repeats faster while held", () => {
    const node = button();
    const step = vi.fn();
    const end = vi.fn();
    const action = holdRepeat(node, { step, end });

    press(node, "pointerdown");
    expect(step).toHaveBeenLastCalledWith(1);
    vi.advanceTimersByTime(HOLD_DELAY_MS - 1);
    expect(step).toHaveBeenCalledTimes(1); // a short tap: one step only
    vi.advanceTimersByTime(1);
    expect(step).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(5 * 150 + 10 * 70 + 10 * 30);
    expect(step).toHaveBeenCalledTimes(2 + 5 + 10 + 10);

    press(node, "pointerup");
    expect(end).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1000);
    expect(step).toHaveBeenCalledTimes(27);
    action.destroy();
  });

  it("ignores presses while disabled and steps once on keyboard activation", () => {
    const node = button();
    const step = vi.fn();
    const action = holdRepeat(node, { step, disabled: true });
    press(node, "pointerdown");
    expect(step).not.toHaveBeenCalled();
    action.update({ step });
    click(node, 0);
    expect(step).toHaveBeenCalledTimes(1);
    click(node, 1); // follows a pointer press
    expect(step).toHaveBeenCalledTimes(1);
    action.destroy();
  });

  it("accelerates", () => {
    expect(repeatInterval(0)).toBe(150);
    expect(repeatInterval(5)).toBe(70);
    expect(repeatInterval(15)).toBe(30);
    expect([repeatSteps(0), repeatSteps(39), repeatSteps(40), repeatSteps(140)]).toEqual([
      1, 1, 5, 25,
    ]);
  });
});
