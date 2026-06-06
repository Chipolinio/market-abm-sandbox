# Назначение пакета: публичные Pydantic DTO API, разбитые по доменам (Slice 7.1).
# Базовая идея: re-export из подмодулей — импорт `from market_abm.api.schemas import X` сохраняется.
from market_abm.api.schemas.analytics import (
    GmvByTickResponse,
    GmvPointDTO,
    PriceIndexPointDTO,
    PriceIndexResponse,
)
from market_abm.api.schemas.health import HealthResponse
from market_abm.api.schemas.shock import (
    SimulationShockRequest,
    SimulationShockResponse,
)
from market_abm.api.schemas.session import (
    SessionConfigureRequest,
    SessionConfigureResponse,
)
from market_abm.api.schemas.simulation import (
    SimulationStartRequest,
    SimulationStatusResponse,
)
from market_abm.api.schemas.stream import (
    MarketAggregateDTO,
    PriceQuantilesDTO,
    TickStreamPayload,
)

__all__ = [
    "GmvByTickResponse",
    "GmvPointDTO",
    "HealthResponse",
    "MarketAggregateDTO",
    "PriceIndexPointDTO",
    "PriceIndexResponse",
    "PriceQuantilesDTO",
    "SimulationShockRequest",
    "SimulationShockResponse",
    "SessionConfigureRequest",
    "SessionConfigureResponse",
    "SimulationStartRequest",
    "SimulationStatusResponse",
    "TickStreamPayload",
]
