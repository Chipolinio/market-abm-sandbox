# Назначение файла: anti-stagnation exploration на векторе цен (Spec 005 §4.5).
# Базовая идея: чистый векторный stochastic-трансформер цен — добавляет мультипликативный
# шум (gaussian_log) или rule-like bump (epsilon_greedy) и жёстко клипует к [p_min, p_max].
# Не знает про маржинальность/маски: границы и активные строки готовит вызывающая сторона.
from __future__ import annotations

import numpy as np

from market_abm.config.ml_repricing import ExplorationConfig


def apply_price_exploration(
    base_prices: np.ndarray,
    config: ExplorationConfig,
    rng: np.random.Generator,
    p_min: np.ndarray,
    p_max: np.ndarray,
) -> np.ndarray:
    """
    Векторное исследование цен (§4.5). Без Python-цикла по строкам.

    - gaussian_log: next = clip(base * exp(N(0, sigma^2)), p_min, p_max);
    - epsilon_greedy (v1, якорь = base): с вероятностью epsilon на строку
      next = clip(base * (1 ± epsilon_relative_step), p_min, p_max), иначе base (TD-5.4-1);
    - enabled=False: чистый клип base к [p_min, p_max].

    Детерминизм полностью задаётся переданным rng (FP: генератор пробрасывается сверху).
    """
    base = np.asarray(base_prices, dtype=np.float64)
    lo = np.asarray(p_min, dtype=np.float64)
    hi = np.asarray(p_max, dtype=np.float64)

    if not config.enabled:
        return np.clip(base, lo, hi).astype(np.float32)

    if config.mode == "gaussian_log":
        noise = rng.normal(0.0, config.gaussian_sigma, size=base.shape[0])
        explored = base * np.exp(noise)
    elif config.mode == "epsilon_greedy":
        trigger = rng.random(base.shape[0]) < config.epsilon
        direction = rng.choice(np.array([-1.0, 1.0]), size=base.shape[0])
        bumped = base * (1.0 + direction * config.epsilon_relative_step)
        explored = np.where(trigger, bumped, base)
    else:  # pragma: no cover - mode валидируется в ExplorationConfig
        explored = base

    return np.clip(explored, lo, hi).astype(np.float32)
