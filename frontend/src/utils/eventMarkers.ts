import type { EventMarker } from "@/components/center/types";

function hasPayload(marker: EventMarker): boolean {
  return marker.payload != null && Object.keys(marker.payload).length > 0;
}

/**
 * Merge chart event markers.
 * Confirmed WS markers (with payload) replace any optimistic same-label markers
 * regardless of tick distance — click tick ≠ apply tick by several frames.
 */
export function mergeEventMarker(prev: EventMarker[], marker: EventMarker): EventMarker[] {
  const confirmed = hasPayload(marker);
  const optimistic = !confirmed;
  let next = prev.filter((existing) => {
    if (existing.label === marker.label && existing.tickId === marker.tickId) {
      return false;
    }
    // Confirmed WS replaces all optimistic siblings of the same label.
    if (confirmed && existing.label === marker.label && !hasPayload(existing)) {
      return false;
    }
    // Only one pending optimistic per label (re-click replaces).
    if (optimistic && existing.label === marker.label && !hasPayload(existing)) {
      return false;
    }
    return true;
  });
  next = [...next, marker];
  return next.slice(-8);
}

export function markerLabelForShock(
  shockType: string,
): "ШОК" | "АКЦИЯ" | null {
  // Demand shocks are marked from WS DEMAND_SHOCK only (avoid double lines).
  if (shockType === "marketplace_promotion") {
    return "АКЦИЯ";
  }
  return null;
}
