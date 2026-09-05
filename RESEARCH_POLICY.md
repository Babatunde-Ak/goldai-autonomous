# Research Policy

## Evidence standard

GoldAI reports profitability only from executed and reproducible experiments. Hypotheses, scaffolds, and unrun tests are never presented as results.

## Chronology and holdouts

- Split development and evaluation data chronologically.
- Use 2021 through 2025 for development and robustness work when that full evidence is available.
- Reserve 2026 as a separate evaluation period.
- Keep designated final holdouts immutable.
- Do not change strategy rules after viewing final holdout performance.

## Market realism

- Prevent look-ahead at every aggregation and decision boundary.
- Replay exact Bid/Ask ticks when the evidence supports it.
- Model spread, order side, timestamp order, data gaps, and execution costs.
- Keep locked tick evidence immutable, including designated July datasets.
- Record provenance and content hashes for source artifacts.
- Preserve raw source archives unchanged. Reject invalid rows explicitly and record all quality counts.
- Prepare reusable canonical partitions before repeated strategy research. Do not repeatedly decompress raw archives for each trial.
- Treat source SHA-256, canonical fingerprints, schema versions, and manifests as part of the experiment evidence.

## Canonical data evidence

- Canonical timestamps are timezone-aware UTC values.
- Historical HistData and live-style MT5 ticks must map to the same source-neutral market semantics.
- Completed candles become visible only after their UTC close boundary.
- Data audit performance fields are diagnostics, not market evidence.
- Generated manifests identify the raw source and canonical outputs without changing the raw source.

## Strategy protocol

- Test each strategy independently before portfolio interaction.
- Compare structural-break entries independently against POC retest, PDH/PDL, and ORB-style comparators when implemented.
- Use true `+3R/-1R` outcomes and the source exit structure as a control where specified.
- Separate strategy edge research from position sizing and capital curves.
- Begin with constant-risk sizing for fair comparison.
- Maintain a strategy trial ledger with hypothesis, version, parameters, data window, code hash, and outcome.

## Overfitting controls

- Predeclare primary metrics and rejection rules.
- Limit parameter searches and record all trials.
- Use perturbation, placebo, and permutation tests.
- Validate across regimes and plausible cost assumptions.
- Distinguish development, robustness, shadow, paper, and DEMO evidence.
- Reject results that depend on a narrow parameter peak or data error.
