// The setup wizard's draft (Setup tab): kept while the page is open, so that switching tabs
// does not lose it; a reload starts from scratch (nothing is saved).

import { ensureFilters, newDraft, type Draft, type Topology } from "./setup";

export const STEPS = ["Inputs", "System", "Speakers", "Filters", "Apply"] as const;

class Wizard {
  step = $state(0);
  draft = $state<Draft>(newDraft([]));
  /** Set once the draft has been made for this DSP's slopes. */
  ready = $state(false);

  start(slopes: string[]): void {
    this.draft = newDraft(slopes);
    this.step = 0;
    this.ready = true;
  }

  go(step: number, topo: Topology): void {
    if (step >= 3) ensureFilters(this.draft, topo.slopes);
    this.step = Math.max(0, Math.min(STEPS.length - 1, step));
  }
}

export const wizard = new Wizard();
