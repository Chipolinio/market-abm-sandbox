# Назначение файла: доменные типы system_events (Slice 8.3).
from __future__ import annotations

from enum import Enum

from market_abm.domain.constants import COL_TICK_ID

COL_EVENT_ID: str = "event_id"
COL_EVENT_TYPE: str = "event_type"
COL_DISPLAY_CODE: str = "display_code"
COL_SEVERITY: str = "severity"
COL_MESSAGE: str = "message"
COL_PAYLOAD_JSON: str = "payload_json"

SYSTEM_EVENTS_COLUMNS: tuple[str, ...] = (
    COL_EVENT_ID,
    COL_TICK_ID,
    COL_EVENT_TYPE,
    COL_DISPLAY_CODE,
    COL_SEVERITY,
    COL_MESSAGE,
    COL_PAYLOAD_JSON,
)

SYSTEM_EVENTS_SCHEMA_DTYPES: dict[str, str] = {
    COL_EVENT_ID: "Utf8",
    COL_TICK_ID: "Int32",
    COL_EVENT_TYPE: "Utf8",
    COL_DISPLAY_CODE: "Utf8",
    COL_SEVERITY: "Utf8",
    COL_MESSAGE: "Utf8",
    COL_PAYLOAD_JSON: "Utf8",
}


class SystemEventType(str, Enum):
    COLLUSION_DETECTED = "collusion_detected"
    FLASH_CRASH = "flash_crash"
    DEMAND_SHOCK = "demand_shock"
    BANKRUPTCY = "bankruptcy"


DISPLAY_CODE_BY_TYPE: dict[SystemEventType, str] = {
    SystemEventType.COLLUSION_DETECTED: "PRICING_WAR",
    SystemEventType.FLASH_CRASH: "FLASH_CRASH",
    SystemEventType.DEMAND_SHOCK: "DEMAND_SHOCK",
    SystemEventType.BANKRUPTCY: "BANKRUPTCY",
}
