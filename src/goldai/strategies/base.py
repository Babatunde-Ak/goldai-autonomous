from __future__ import annotations

from abc import ABC, abstractmethod

from goldai.market import MarketState
from goldai.strategies.models import StrategyDecision


class DeterministicStrategy(ABC):
    """Pure strategy boundary. Implementations may decide, never execute."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, market: MarketState) -> StrategyDecision:
        raise NotImplementedError

