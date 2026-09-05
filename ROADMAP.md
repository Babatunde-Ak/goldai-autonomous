# Roadmap

| Milestone | Scope |
|---|---|
| M0 | Accepted: architecture foundation, safe contracts, CLI, tests, and CI |
| M1 | Implemented: canonical historical and observe-only live market-data core |
| M2 | Implemented candidate migration with synthetic source parity; historical replay outstanding |
| M3 | Unified deterministic replay and backtest engine |
| M4 | Portfolio router and complete risk engine |
| M5 | MT5 observe-only parity |
| M6 | Autonomous paper trading |
| M7 | Guarded autonomous MT5 DEMO execution |
| M8 | Jarvis, local LLM, and Obsidian memory |
| M9 | Telegram notifications, reports, and questions |
| M10 | Professional trading terminal UI |
| M11 | Dedicated scalping research |
| M12 | Fresh-data validation and ML or meta-model research |

Every milestone requires review. Milestone 2 does not authorize Milestone 3 replay implementation or any broker mutation. Recommended M3 scope is unified deterministic per-strategy replay, exact Bid/Ask fill semantics, source exit controls and reproducible outcome manifests. No portfolio allocation, broker execution, AI or UI is authorized by this recommendation.
