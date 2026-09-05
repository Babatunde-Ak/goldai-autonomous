import json

import pytest

from goldai.config import ExecutionMode, load_config


def test_default_execution_mode_is_observe_only() -> None:
    assert load_config().execution_mode is ExecutionMode.OBSERVE_ONLY


def test_configuration_loading(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"execution_mode": "RESEARCH", "symbols": ["XAUUSD"], "timeframes": ["M15"]}))
    config = load_config(path)
    assert config.execution_mode is ExecutionMode.RESEARCH
    assert config.timeframes[0].value == "M15"


def test_configuration_rejects_demo_mode(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"execution_mode": "DEMO"}))
    with pytest.raises(ValueError, match="DEMO mode"):
        load_config(path)

