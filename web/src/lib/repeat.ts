// Press-and-hold auto-repeat for the − / + buttons (a Svelte action).
//
// A press steps once; held for HOLD_DELAY_MS it then repeats, faster and faster, and after
// about 2 s each repeat moves several steps (long ranges such as a 3000 ms release). Keyboard
// activation (Enter / Space) steps once. Scrolling the page from the button (pointercancel) or
// releasing it stops the repeat; `end` then runs once.

export interface RepeatParams {
  /** Move by `count` steps (1 on a press; more per repeat once held for long). */
  step: (count: number) => void;
  end?: () => void;
  disabled?: boolean;
}

export const HOLD_DELAY_MS = 400;

/** Interval before repeat number `n` (0-based): 150 ms, then 70 ms, then 30 ms. */
export function repeatInterval(n: number): number {
  if (n < 5) return 150;
  if (n < 15) return 70;
  return 30;
}

/** Steps per repeat number `n`: 1, then 5 after ~2 s of holding, then 25 after ~3 s more. */
export function repeatSteps(n: number): number {
  if (n < 40) return 1;
  if (n < 140) return 5;
  return 25;
}

export function holdRepeat(node: HTMLElement, initial: RepeatParams) {
  let params = initial;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let count = 0;
  let active = false;

  function tick() {
    params.step(repeatSteps(count));
    timer = setTimeout(tick, repeatInterval(count++));
  }

  function start(event: PointerEvent) {
    if (params.disabled || event.button !== 0) return;
    event.preventDefault(); // no focus change, no text selection, no long-press menu
    node.setPointerCapture?.(event.pointerId);
    active = true;
    count = 0;
    params.step(1);
    timer = setTimeout(tick, HOLD_DELAY_MS);
  }

  function stop() {
    if (!active) return;
    active = false;
    clearTimeout(timer);
    params.end?.();
  }

  function click(event: MouseEvent) {
    // Pointer presses are handled above; detail 0 means Enter / Space.
    if (event.detail === 0 && !params.disabled) {
      params.step(1);
      params.end?.();
    }
  }

  const noMenu = (event: Event) => event.preventDefault();

  node.addEventListener("pointerdown", start);
  node.addEventListener("pointerup", stop);
  node.addEventListener("pointercancel", stop);
  node.addEventListener("lostpointercapture", stop);
  node.addEventListener("click", click);
  node.addEventListener("contextmenu", noMenu);

  return {
    update(next: RepeatParams) {
      params = next;
      if (next.disabled) stop();
    },
    destroy() {
      stop();
      node.removeEventListener("pointerdown", start);
      node.removeEventListener("pointerup", stop);
      node.removeEventListener("pointercancel", stop);
      node.removeEventListener("lostpointercapture", stop);
      node.removeEventListener("click", click);
      node.removeEventListener("contextmenu", noMenu);
    },
  };
}
