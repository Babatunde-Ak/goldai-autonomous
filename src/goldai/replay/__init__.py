"""Offline per-strategy simulation. No broker or execution adapters."""
ENGINE_VERSION = "goldai.replay.v1"
STRATEGIES = (
    "ema50_chandelier_m15_touch", "poc_continuation_retest_long",
    "pdh_pdl_breakout_retest", "xauusd_structural_break_trend_v1",
    "m15_supply_demand", "m15_supply_demand_2r",
)
