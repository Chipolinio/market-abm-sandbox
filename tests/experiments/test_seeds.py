# Spec 015 slice 15.1 — seed_for_run (SeedSequence schedule).
from __future__ import annotations

import numpy as np

from experiments.seeds import seed_for_run


def test_15_1_t1_seed_for_run_deterministic() -> None:
    """15.1-T1: same (base, i) → same seed; formula = SeedSequence([base, i])."""
    base = 10_000
    a = seed_for_run(base, 0)
    b = seed_for_run(base, 0)
    assert a == b
    assert isinstance(a, int)

    expected = int(np.random.SeedSequence([base, 0]).generate_state(1)[0])
    assert a == expected

    c = seed_for_run(base, 1)
    assert c == int(np.random.SeedSequence([base, 1]).generate_state(1)[0])
    assert a != c
