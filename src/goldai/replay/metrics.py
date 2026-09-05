"""Closed-trade constant-risk statistics, ordered by actual exit cursor."""
from statistics import mean, median
from collections import defaultdict
from datetime import datetime


def metrics(rows):
    closed = sorted((r for r in rows if r["realized_r"] is not None),
                    key=lambda r: (r["exit_cursor"], r["trade_id"]))
    values = [r["cost_adjusted_r"] for r in closed]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    equity = peak = dd = 0.0
    ws = ls = max_ws = max_ls = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        dd = max(dd, peak-equity)
        ws = ws+1 if value > 0 else 0
        ls = ls+1 if value < 0 else 0
        max_ws, max_ls = max(max_ws, ws), max(max_ls, ls)
    avgwin, avgloss = mean(wins) if wins else None, mean(losses) if losses else None
    return {
        "trade_count": len(closed), "wins": len(wins), "losses": len(losses),
        "breakevens": sum(v == 0 for v in values),
        "win_rate": len(wins)/len(values) if values else None,
        "net_r": sum(values), "average_r": mean(values) if values else None,
        "median_r": median(values) if values else None,
        "expectancy_r": mean(values) if values else None,
        "gross_profit_r": sum(wins), "gross_loss_r": -sum(losses),
        "profit_factor": sum(wins)/-sum(losses) if losses else None,
        "profit_factor_status": "DEFINED" if losses else "NO_LOSSES" if wins else "NO_TRADES_OR_BREAKEVEN",
        "maximum_drawdown_r": dd, "longest_winning_streak": max_ws,
        "longest_losing_streak": max_ls, "average_win_r": avgwin, "average_loss_r": avgloss,
        "payoff_ratio": avgwin/-avgloss if avgwin is not None and avgloss is not None else None,
        "average_mfe_r": mean([r["mfe_r"] for r in closed]) if closed else None,
        "average_mae_r": mean([r["mae_r"] for r in closed]) if closed else None,
        "median_holding_seconds": median([r["holding_seconds"] for r in closed]) if closed else None,
        "average_holding_seconds": mean([r["holding_seconds"] for r in closed]) if closed else None,
    }


def grouped_metrics(rows):
    result = {}
    for group in ("year", "month", "direction", "strategy_id", "timeframe"):
        buckets = defaultdict(list)
        for row in rows:
            if row["realized_r"] is None:
                continue
            # Chronological attribution is by exit UTC, never entry ordering.
            key = row["exit_timestamp"][:4 if group == "year" else 7] if group in ("year", "month") else row[group]
            buckets[key].append(row)
        result[group] = {k: metrics(v) for k, v in sorted(buckets.items())}
    return result


def remove_top_trades(rows, count):
    if type(count) is not int or count < 0:
        raise ValueError("count must be a nonnegative integer")
    closed = [r for r in rows if r["realized_r"] is not None]
    removed = {r["trade_id"] for r in sorted(closed, key=lambda r: (-r["cost_adjusted_r"], r["trade_id"]))[:count]}
    return metrics([r for r in rows if r["trade_id"] not in removed])


def segment_metrics(rows, segments):
    """Named half-open UTC exit-time windows, diagnostic only."""
    result = {}
    for name, (start, end) in segments.items():
        start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("segments require ordered timezone-aware bounds")
        result[name] = metrics([r for r in rows if r["exit_timestamp"] is not None
                               and start <= datetime.fromisoformat(r["exit_timestamp"]) < end])
    return result
