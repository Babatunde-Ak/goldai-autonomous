from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from types import ModuleType
from typing import Any

from goldai.market import MarketTick, SymbolSpecification
from goldai.risk import AccountType


class MT5DependencyStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"


def _value(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


@dataclass(slots=True)
class MT5ObserveMarketDataAdapter:
    """Read-only MT5 boundary. It exposes domain models, never MT5 objects."""

    module: ModuleType | object | None = None
    connected: bool = False

    @staticmethod
    def dependency_status() -> MT5DependencyStatus:
        return (
            MT5DependencyStatus.AVAILABLE
            if importlib.util.find_spec("MetaTrader5") is not None
            else MT5DependencyStatus.NOT_INSTALLED
        )

    def _module(self) -> ModuleType | object:
        if self.module is None:
            if self.dependency_status() is MT5DependencyStatus.NOT_INSTALLED:
                raise RuntimeError("MetaTrader5 is optional and is not installed")
            self.module = importlib.import_module("MetaTrader5")
        return self.module

    def initialize(self, **connection_options: object) -> bool:
        module = self._module()
        initialized = bool(module.initialize(**connection_options))
        self.connected = initialized
        if not initialized:
            error = module.last_error() if hasattr(module, "last_error") else "unknown error"
            raise ConnectionError(f"MT5 initialization failed: {error}")
        return True

    def shutdown(self) -> None:
        if self.module is not None and self.connected:
            self.module.shutdown()
        self.connected = False

    def ensure_symbol(self, symbol: str) -> bool:
        module = self._module()
        info = module.symbol_info(symbol)
        if info is None:
            return False
        if not bool(_value(info, "visible", False)):
            return bool(module.symbol_select(symbol, True))
        return True

    def symbol_specification(self, symbol: str) -> SymbolSpecification:
        info = self._module().symbol_info(symbol)
        if info is None:
            raise LookupError(f"MT5 symbol is unavailable: {symbol}")
        return SymbolSpecification(
            symbol=symbol,
            digits=int(_value(info, "digits")),
            point=float(_value(info, "point")),
            contract_size=float(_value(info, "trade_contract_size")),
            minimum_volume=float(_value(info, "volume_min")),
            maximum_volume=float(_value(info, "volume_max")),
            volume_step=float(_value(info, "volume_step")),
        )

    def map_tick(self, symbol: str, raw_tick: object, *, sequence: int | None = None) -> MarketTick:
        milliseconds = _value(raw_tick, "time_msc")
        if milliseconds is not None:
            timestamp = datetime.fromtimestamp(float(milliseconds) / 1000.0, tz=UTC)
        else:
            timestamp = datetime.fromtimestamp(float(_value(raw_tick, "time")), tz=UTC)
        last_raw = _value(raw_tick, "last")
        last = float(last_raw) if last_raw is not None and float(last_raw) > 0 else None
        volume_raw = _value(raw_tick, "volume_real", _value(raw_tick, "volume"))
        last_volume = float(volume_raw) if volume_raw is not None and float(volume_raw) >= 0 else None
        raw_flags = _value(raw_tick, "flags")
        flags = (f"mt5_flags:{raw_flags}",) if raw_flags is not None else ()
        return MarketTick(
            symbol=symbol,
            timestamp=timestamp,
            bid=float(_value(raw_tick, "bid")),
            ask=float(_value(raw_tick, "ask")),
            last=last,
            last_volume=last_volume,
            source="mt5",
            sequence=sequence,
            flags=flags,
        )

    def latest_tick(self, symbol: str) -> MarketTick:
        raw_tick = self._module().symbol_info_tick(symbol)
        if raw_tick is None:
            raise LookupError(f"MT5 returned no tick for {symbol}")
        return self.map_tick(symbol, raw_tick)

    def historical_ticks(self, symbol: str, start: datetime, end: datetime) -> Iterator[MarketTick]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("MT5 history boundaries must be timezone-aware")
        module = self._module()
        mode = getattr(module, "COPY_TICKS_ALL", 0)
        rows = module.copy_ticks_range(symbol, start.astimezone(UTC), end.astimezone(UTC), mode)
        if rows is None:
            raise RuntimeError(f"MT5 tick history failed for {symbol}")
        for sequence, row in enumerate(rows):
            yield self.map_tick(symbol, row, sequence=sequence)

    def historical_rates(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> tuple[dict[str, object], ...]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("MT5 history boundaries must be timezone-aware")
        rows = self._module().copy_rates_range(symbol, timeframe, start.astimezone(UTC), end.astimezone(UTC))
        if rows is None:
            raise RuntimeError(f"MT5 rate history failed for {symbol}")
        result: list[dict[str, object]] = []
        for row in rows:
            if isinstance(row, Mapping):
                result.append(dict(row))
            elif hasattr(row, "dtype") and getattr(row.dtype, "names", None):
                result.append({name: row[name].item() for name in row.dtype.names})
            else:
                result.append(dict(vars(row)))
        return tuple(result)

    def account_classification(self) -> AccountType:
        module = self._module()
        info = module.account_info()
        if info is None:
            return AccountType.UNKNOWN
        trade_mode = _value(info, "trade_mode")
        if trade_mode == getattr(module, "ACCOUNT_TRADE_MODE_DEMO", object()):
            return AccountType.DEMO
        if trade_mode == getattr(module, "ACCOUNT_TRADE_MODE_CONTEST", object()):
            return AccountType.CONTEST
        if trade_mode == getattr(module, "ACCOUNT_TRADE_MODE_REAL", object()):
            return AccountType.REAL
        return AccountType.UNKNOWN

    def account_snapshot(self) -> dict[str, object]:
        info = self._module().account_info()
        if info is None:
            return {"account_type": AccountType.UNKNOWN.value, "available": False}
        return {
            "account_type": self.account_classification().value,
            "available": True,
            "currency": _value(info, "currency"),
            "server": _value(info, "server"),
            "trade_allowed": bool(_value(info, "trade_allowed", False)),
        }
