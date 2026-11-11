<script lang="ts">
  // Between the inputs and the outputs of the views with one strip per channel: a band with
  // "IN" and "OUT" written vertically, so that the two groups are told apart at a glance.
</script>

<div class="side-divider" role="separator" aria-orientation="vertical" aria-label="Inputs | Outputs">
  <span>IN</span>
  <span class="line"></span>
  <span>OUT</span>
</div>

<style>
  .side-divider {
    flex: 0 0 24px;
    align-self: stretch;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    margin: 0 4px;
    padding: 8px 0;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  span {
    writing-mode: vertical-rl;
    text-orientation: upright;
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 1px;
    color: var(--text);
  }
  .line {
    flex: 1;
    width: 2px;
    border-radius: 1px;
    background: var(--muted);
    opacity: 0.5;
  }
</style>
