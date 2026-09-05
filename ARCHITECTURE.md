# Architecture

## Design goals

GoldAI separates market data, strategies, risk, execution, and persistence. The domain package does not depend on MetaTrader 5, a web framework, an LLM, or a database driver.

## Long-term flow

```text
Historical Data / Live MT5
            |
            v
Canonical Market Engine
            |
            v
        Indicators
            |
            v
     Strategy Engines
            |
            v
Regime / Portfolio Router
            |
            v
       Risk Engine
            |
            v
Paper / MT5 DEMO Execution
            |
            v
      Trade Database
            |
            v
     Jarvis + Memory
            |
            v
Telegram + Web Terminal
```

## Canonical market boundary

HistData Bid/Ask ticks and future live MT5 Bid/Ask ticks must map to the same `MarketTick`. Strategy code consumes canonical objects and never imports MetaTrader5.

```text
Historical HistData Bid/Ask ticks -> Canonical MarketTick <- Live MT5 Bid/Ask ticks
```

Adapters own source-specific parsing, precision, sequencing, and connection behavior. Canonical validation rejects non-positive prices, naive timestamps, and `bid > ask`.

## Strategy boundary

A strategy receives `MarketState` and returns `StrategyDecision`. It cannot execute an order. Decision state is explicit: `IDLE`, `FORMING`, `WAITING`, `READY`, `INVALIDATED`, or `COOLDOWN`.

The registry stores identity, version, symbol, timeframe, research status, runtime status, and execution authorization. Registration never promotes a strategy.

## Risk and execution boundary

The required downstream order is:

```text
Strategy -> Portfolio Router -> Risk Engine -> Execution Authorization -> Adapter
```

Milestone 0 uses fail-closed authorization. MT5 DEMO execution is disabled even for a DEMO account. REAL, FUNDED, CONTEST, and UNKNOWN account types are rejected before other checks.

## Events and auditability

Events use canonical UTC timestamps and deterministic SHA-256-derived identifiers over canonical content. Replaying identical input produces the same event identifier. Correlation IDs connect market input, decisions, risk outcomes, and future fills without logging credentials.

## Configuration

Configuration is typed and loaded from JSON. `OBSERVE_ONLY` is the default. Milestone 0 rejects `DEMO` configuration at load time. A later milestone must add an explicit, tested DEMO promotion workflow without weakening account classification.

## Storage direction

The initial interface supports ticks, bars, decisions, signals, positions, trades, outcomes, events, research runs, strategy versions, and reports. Operational metadata may begin with SQLite. Historical bulk data should use Parquet with DuckDB-compatible schemas.

## Dependency rule

Dependencies point inward. Domain code remains framework-neutral. Broker, persistence, notifications, AI, and UI integrations remain adapters outside deterministic strategy logic.

