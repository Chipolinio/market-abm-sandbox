import { useEffect, useState } from "react";

import type { SystemEventDTO } from "@/types/events";

const FLASH_CRASH_ALARM_MS = 10_000;

/** UI-only margin stability alarm from WS events (Spec 009 §2.5). */
export function useFlashCrashAlarm(events: SystemEventDTO[] | undefined): boolean {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const hasFlashCrash =
      events?.some(
        (event) => event.display_code === "FLASH_CRASH" && event.severity === "critical",
      ) ?? false;

    if (!hasFlashCrash) {
      setActive(false);
      return undefined;
    }

    setActive(true);
    const timer = setTimeout(() => setActive(false), FLASH_CRASH_ALARM_MS);
    return () => clearTimeout(timer);
  }, [events]);

  return active;
}
