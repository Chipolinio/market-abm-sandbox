# Назначение файла: публичный API ML-слоя (Spec 005) — bootstrap-сбор обучающей выборки.
# Базовая идея: модели и пайплайны живут вне доменных таблиц (инфраструктура прогона).
from market_abm.ml.bootstrap import (
    LABEL_COLUMN,
    collect_bootstrap_training_frame,
    run_bootstrap_simulation,
)

__all__ = [
    "LABEL_COLUMN",
    "collect_bootstrap_training_frame",
    "run_bootstrap_simulation",
]
