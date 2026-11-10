import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HOLD_DELAY_MS, holdRepeat, REPEAT_MS } from "./repeat";

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

  it("steps once on a tap, then repeats at a constant rate while held", () => {
    const node = button();
    const step = vi.fn();
    const end = vi.fn();
    const action = holdRepeat(node, { step, end });

    press(node, "pointerdown");
    vi.advanceTimersByTime(HOLD_DELAY_MS - 1);
    expect(step).toHaveBeenCalledTimes(1); // a short tap: one step only
    vi.advanceTimersByTime(1);
    expect(step).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(25 * REPEAT_MS);
    expect(step).toHaveBeenCalledTimes(2 + 25);

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


});
