/** System events DTO (Spec 008 / Spec 009 §5). */

export type SystemEventSeverity = "info" | "warning" | "critical";

export type SystemEventDTO = {
  event_id: string;
  tick_id: number;
  event_type: string;
  display_code: string;
  severity: SystemEventSeverity;
  message: string;
  payload?: Record<string, unknown>;
};

export type SystemEventsResponse = {
  events: SystemEventDTO[];
};
