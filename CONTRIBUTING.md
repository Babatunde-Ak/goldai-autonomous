# Contributing

## Principles

Prioritize correctness, safety, reproducibility, testability, maintainability, performance, then feature quantity.

## Requirements

- Preserve deterministic domain behavior.
- Keep strategies independent from broker adapters.
- Add or update tests for every change.
- Use timezone-aware timestamps.
- Record strategy versions and research provenance.
- Never fabricate or overstate experimental results.
- Never commit credentials or personal data.
- Never weaken account-type blocking.
- Do not add AI co-author metadata.

## Checks

```bash
python -m pytest
python -m compileall -q src
python -m goldai doctor
```

Use focused commits and explain architecture or safety effects in the pull request.

