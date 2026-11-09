// Press-and-hold auto-repeat for the − / + buttons (a Svelte action).
//
// A press steps once; held for HOLD_DELAY_MS it then repeats at a constant REPEAT_MS rate.
// Keyboard activation (Enter / Space) steps once. Scrolling the page from the button (pointercancel) or
// releasing it stops the repeat; `end` then runs once.

export interface RepeatParams {
  step: () => void;
  end?: () => void;
  disabled?: boolean;
}

export const HOLD_DELAY_MS = 400;
export const REPEAT_MS = 80;

export function holdRepeat(node: HTMLElement, initial: RepeatParams) {
  let params = initial;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let active = false;

  function tick() {
    params.step();
    timer = setTimeout(tick, REPEAT_MS);
  }

  function start(event: PointerEvent) {
    if (params.disabled || event.button !== 0) return;
    event.preventDefault(); // no focus change, no text selection, no long-press menu
    node.setPointerCapture?.(event.pointerId);
    active = true;
    params.step();
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
      params.step();
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
