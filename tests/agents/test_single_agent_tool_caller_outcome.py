from __future__ import annotations

from datetime import date

from backend.agents.single_agent_tool_caller import _first_s1_text, _outcome_metrics_from_scenario


def test_outcome_metrics_from_scenario_none_without_core_prices() -> None:
    scenario = {
        "price_performance": {
            "lock_up_cliff_date": "2024-03-15",
            "ipo_price": None,
            "current_price": None,
        }
    }
    assert _outcome_metrics_from_scenario(scenario) is None


def test_outcome_metrics_from_scenario_maps_core_fields() -> None:
    scenario = {
        "price_performance": {
            "ipo_price": 10.0,
            "current_price": 25.0,
            "performance_since_ipo_pct": 50.0,
            "peak_price": 30.0,
            "peak_date": "2024-06-01",
            "trough_price": 8.0,
            "trough_date": "2024-05-01",
            "lock_up_cliff_date": "2024-04-01",
            "price_at_lock_up_cliff": 12.0,
            "recovered_to_ipo_date": None,
            "recovered_to_peak_date": None,
        }
    }
    om = _outcome_metrics_from_scenario(scenario)
    assert om is not None
    assert om.ipo_price == 10.0
    assert om.current_price == 25.0
    assert om.performance_since_ipo_pct == 50.0
    assert om.peak_date == date(2024, 6, 1)


def test_first_s1_text_accepts_form_s1_filing_type() -> None:
    analysis = {
        "harvester_output": {
            "sec_filings": [
                {"filing_type": "FORM S-1", "text": "Prospectus body about lock-up and shares."},
            ]
        }
    }
    assert _first_s1_text(analysis) == "Prospectus body about lock-up and shares."
