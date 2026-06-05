from __future__ import annotations

from market_abm.api.stub_telemetry import stub_market_summary, stub_tick_payload


def test_stub_market_summary_has_quantiles_and_nonzero_gmv() -> None:
    summary = stub_market_summary(42)
    assert summary.price_quantiles is not None
    q = summary.price_quantiles
    assert q.p10 <= q.p50 <= q.p90
    assert summary.total_gmv >= 0.0
    assert summary.mean_price != 0.0


def test_stub_tick_payload_matches_tick_id() -> None:
    payload = stub_tick_payload(7)
    assert payload.tick_id == 7
    assert payload.market_summary.price_quantiles is not None
