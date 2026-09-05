from goldai.cli.main import main


def test_doctor_reports_safe_status(capsys) -> None:
    result = main(["doctor"])
    output = capsys.readouterr().out
    assert result == 0
    assert "GoldAI Core" in output
    assert "Execution" in output
    assert "OBSERVE_ONLY" in output
    assert "MT5 connection" in output
    assert "DISABLED" in output


def test_data_audit_fails_clearly(capsys) -> None:
    result = main(["data", "audit"])
    assert result == 3
    assert "NOT IMPLEMENTED" in capsys.readouterr().out


def test_strategy_status_lists_registry(capsys) -> None:
    result = main(["strategies", "status"])
    output = capsys.readouterr().out
    assert result == 0
    assert "ema50_chandelier_m15_touch" in output
    assert "NONE" in output

