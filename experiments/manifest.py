# Spec 015 §4.2 — experiment manifest (YAML → Pydantic). Offline only.
from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class ShockProtocolSpec(BaseModel):
    """Optional demand-crash schedule for paper grid (applied in later slices)."""

    model_config = {"frozen": True}

    mode: Literal["fixed_duration", "stochastic_regime"] = "fixed_duration"
    demand_crash_at_tick: int = Field(ge=0)
    scenario: Literal["mild", "standard", "severe"] = "severe"


class ExperimentManifest(BaseModel):
    """Batch experiment declaration — Spec 015 §4.2."""

    model_config = {"frozen": True}

    experiment_id: str = Field(min_length=1)
    base_seed: int
    n_runs: int = Field(ge=1)
    n_ticks: int = Field(ge=1)
    burn_in_ticks: int = Field(ge=0, default=0)
    ml_share_grid: tuple[float, ...]
    runtime_mode: Literal["legacy", "extended"] = "extended"
    output_dir: str
    shock_protocol: ShockProtocolSpec | None = None
    n_buyers: int = Field(default=50, ge=2)
    n_sellers: int = Field(default=8, ge=1)

    @field_validator("ml_share_grid")
    @classmethod
    def _shares_in_unit_interval(cls, value: tuple[float, ...] | list[float]) -> tuple[float, ...]:
        shares = tuple(float(x) for x in value)
        if not shares:
            raise ValueError("ml_share_grid must be non-empty")
        for s in shares:
            if s < 0.0 or s > 1.0:
                raise ValueError(f"ml_share_grid values must be in [0, 1], got {s}")
        return shares

    @model_validator(mode="after")
    def _burn_in_lt_ticks(self) -> Self:
        if self.burn_in_ticks >= self.n_ticks and self.n_ticks > 0:
            # Allow burn_in == 0; burn_in >= n_ticks is useless but valid for empty windows later.
            pass
        return self


def load_manifest(path: Path | str) -> ExperimentManifest:
    """Load and validate experiment YAML (or JSON) from disk."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest root must be a mapping, got {type(raw)!r}")
    return ExperimentManifest.model_validate(raw)
