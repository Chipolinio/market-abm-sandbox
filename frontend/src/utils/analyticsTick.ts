/**
 * Worker tick_counter / WS tick_id = next tick to execute.
 * Analytics Parquet is keyed by last completed tick (0-based).
 */
export function toLastCompletedTick(nextTick: number): number {
  if (nextTick <= 0) {
    return 0;
  }
  return nextTick - 1;
}
