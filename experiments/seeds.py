# Spec 015 §4.1 — deterministic seed schedule for batch runs (no SeedManager class).
from __future__ import annotations

import numpy as np


def seed_for_run(base_seed: int, run_index: int) -> int:
    """Return run seed from SeedSequence([base_seed, run_index]) — Spec 015 §19 #3."""
    return int(np.random.SeedSequence([int(base_seed), int(run_index)]).generate_state(1)[0])
