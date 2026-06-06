# Назначение файла: DTO system_events для REST/WS (Slice 8.3).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SystemEventDTO(BaseModel):
    event_id: str
    tick_id: int
    event_type: str
    display_code: str
    severity: Literal["info", "warning", "critical"]
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class SystemEventsResponse(BaseModel):
    events: list[SystemEventDTO]
