from __future__ import annotations

from typing import Callable

import numpy as np
import scipy.stats

from market_abm.config.buyers import CategoricalSpec, DistributionSpec

SamplerFn = Callable[[dict[str, float], int, np.random.Generator], np.ndarray]


def _rvs(family: str, params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    """Общий вызов scipy.stats.<family>.rvs с фиксированным Generator."""
    dist = getattr(scipy.stats, family)
    return dist.rvs(size=size, random_state=rng, **params)


def _sample_lognorm(params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    return _rvs("lognorm", params, size, rng)


def _sample_norm(params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    return _rvs("norm", params, size, rng)


def _sample_truncnorm(params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    return _rvs("truncnorm", params, size, rng)


def _sample_gamma(params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    return _rvs("gamma", params, size, rng)


def _sample_uniform(params: dict[str, float], size: int, rng: np.random.Generator) -> np.ndarray:
    return _rvs("uniform", params, size, rng)


_SAMPLERS: dict[str, SamplerFn] = {
    "lognorm": _sample_lognorm,
    "norm": _sample_norm,
    "truncnorm": _sample_truncnorm,
    "gamma": _sample_gamma,
    "uniform": _sample_uniform,
}


def sample_from_spec(
    spec: DistributionSpec,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Векторный сэмпл непрерывной фичи длины ``size`` по спецификации scipy.

    Диспетчеризация match/strategy: ``spec.family`` → приватная функция ``_sample_*``.
    """
    if size <= 0:
        raise ValueError(f"size должен быть > 0, получено {size}")

    sampler = _SAMPLERS.get(spec.family)
    if sampler is None:
        raise ValueError(f"Неподдерживаемое семейство распределения: {spec.family!r}")

    return sampler(spec.params, size, rng)


def sample_categorical(
    spec: CategoricalSpec,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Вектор строковых уровней категории длины ``size``."""
    if size <= 0:
        raise ValueError(f"size должен быть > 0, получено {size}")
    return rng.choice(spec.levels, size=size, p=list(spec.probabilities))


def sample_bernoulli(
    p: float,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Вектор булевых значений Bernoulli(p) длины ``size``."""
    if size <= 0:
        raise ValueError(f"size должен быть > 0, получено {size}")
    return rng.random(size=size) < p


def sample_activity_hours(size: int, rng: np.random.Generator) -> np.ndarray:
    """Дискретный uniform на {0, …, 23} для ``activity_hour`` (UInt8)."""
    if size <= 0:
        raise ValueError(f"size должен быть > 0, получено {size}")
    return rng.integers(0, 24, size=size, dtype=np.uint8)
