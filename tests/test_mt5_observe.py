from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from goldai.data import CanonicalCandleAggregator
from goldai.market import Timeframe
from goldai.mt5 import MT5DependencyStatus, MT5ObserveMarketDataAdapter
from goldai.risk import AccountType


class FakeMT5:
    COPY_TICKS_ALL = 0
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self) -> None:
        self.closed = False
        self.rows: list[object] = []

    def initialize(self, **_: object) -> bool:
        return True

    def shutdown(self) -> None:
        self.closed = True

    def symbol_info_tick(self, _: str) -> object:
        return self.rows[-1]

    def copy_ticks_range(self, *_: object) -> list[object]:
        return self.rows

    def symbol_info(self, _: str) -> object:
        return SimpleNamespace(
            visible=True,
            digits=2,
            point=0.01,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )

    def account_info(self) -> object:
        return SimpleNamespace(trade_mode=0, currency="USD", server="Demo", trade_allowed=True)


def _raw(timestamp: datetime, bid: float, ask: float, volume: float = 0.0) -> object:
    return SimpleNamespace(
        time_msc=int(timestamp.timestamp() * 1000),
        bid=bid,
        ask=ask,
        last=0.0,
        volume_real=volume,
        flags=6,
    )


def test_linux_import_succeeds_without_mt5_dependency() -> None:
    assert MT5ObserveMarketDataAdapter.dependency_status() in {
        MT5DependencyStatus.AVAILABLE,
        MT5DependencyStatus.NOT_INSTALLED,
    }


def test_synthetic_mt5_tick_maps_to_canonical_contract() -> None:
    fake = FakeMT5()
    timestamp = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    fake.rows = [_raw(timestamp, 2600.1, 2600.3, 2.0)]
    adapter = MT5ObserveMarketDataAdapter(module=fake)
    tick = adapter.latest_tick("XAUUSD")
    assert tick.timestamp == timestamp
    assert tick.bid == 2600.1
    assert tick.ask == 2600.3
    assert tick.last is None
    assert tick.last_volume == 2.0
    assert tick.source == "mt5"


def test_mt5_account_classification_and_symbol_specification_are_observational() -> None:
    adapter = MT5ObserveMarketDataAdapter(module=FakeMT5())
    assert adapter.account_classification() is AccountType.DEMO
    assert adapter.account_snapshot()["account_type"] == "DEMO"
    assert adapter.symbol_specification("XAUUSD").digits == 2


def test_historical_and_synthetic_mt5_ticks_produce_identical_bars(tmp_path) -> None:
    start = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    semantic = [
        (start, 2600.1, 2600.3, 1.0),
        (start + timedelta(minutes=2), 2600.4, 2600.6, 2.0),
        (start + timedelta(minutes=5), 2600.2, 2600.4, 3.0),
    ]
    historical_path = tmp_path / "ticks.csv"
    historical_path.write_text(
        "\n".join(
            f"{timestamp.strftime('%Y%m%d %H%M%S')}000,{bid},{ask},{volume}"
            for timestamp, bid, ask, volume in semantic
        )
        + "\n"
    )
    from goldai.data import HistDataAdapter

    historical_ticks = list(HistDataAdapter(historical_path, "XAUUSD").ticks())
    fake = FakeMT5()
    fake.rows = [_raw(*row) for row in semantic]
    live_ticks = list(MT5ObserveMarketDataAdapter(module=fake).historical_ticks("XAUUSD", start, start + timedelta(minutes=6)))

    results = []
    for ticks in (historical_ticks, live_ticks):
        aggregator = CanonicalCandleAggregator(Timeframe.M5)
        bars = []
        for tick in ticks:
            bars.extend(aggregator.push(tick))
        results.append([bar.semantic_dict() for bar in bars])
    assert results[0] == results[1]


def test_optional_dependency_error_is_clear(monkeypatch) -> None:
    monkeypatch.setattr(MT5ObserveMarketDataAdapter, "dependency_status", staticmethod(lambda: MT5DependencyStatus.NOT_INSTALLED))
    with pytest.raises(RuntimeError, match="not installed"):
        MT5ObserveMarketDataAdapter().latest_tick("XAUUSD")
