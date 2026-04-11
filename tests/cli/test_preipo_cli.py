from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cli import main as cli_main
from tui.types import AnalysisOutputsResponse, CreateAnalysisResponse, SingleAgentResult


def test_doctor_reachable() -> None:
    log = logging.getLogger("test")
    with patch("cli.main.httpx.Client") as mock_cls:
        client = MagicMock()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp
        mock_cls.return_value.__enter__.return_value = client
        mock_cls.return_value.__exit__.return_value = None
        code = cli_main._cmd_doctor("http://127.0.0.1:8000", log)
    assert code == 0
    client.get.assert_called_once()


def test_doctor_unreachable() -> None:
    log = logging.getLogger("test")
    with patch("cli.main.httpx.Client") as mock_cls:
        client = MagicMock()
        client.get.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value.__enter__.return_value = client
        mock_cls.return_value.__exit__.return_value = None
        code = cli_main._cmd_doctor("http://127.0.0.1:8000", log)
    assert code == 1


def test_analyze_poll_and_print_plain(capsys: pytest.CaptureFixture[str]) -> None:
    log = logging.getLogger("test")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    created = CreateAnalysisResponse(
        analysis_id="id-1",
        company_name="Acme",
        status="pending",
        complexity_tier="standard",
        created_at=ts,
    )
    running = AnalysisOutputsResponse(
        analysis_id="id-1",
        company_name="Acme",
        status="running",
        complexity_tier="standard",
        last_completed_agent=None,
        created_at=ts,
        analysis_result=None,
    )
    result = SingleAgentResult(company_name="Acme", generated_at=ts)
    completed = AnalysisOutputsResponse(
        analysis_id="id-1",
        company_name="Acme",
        status="completed",
        complexity_tier="standard",
        last_completed_agent="single_agent",
        created_at=ts,
        analysis_result=result,
    )
    with patch("cli.main.PreipoHttpClient") as mock_cl:
        inst = MagicMock()
        inst.create_analysis.return_value = created
        inst.get_analysis.side_effect = [running, completed]
        mock_cl.return_value.__enter__.return_value = inst
        mock_cl.return_value.__exit__.return_value = None
        code = cli_main._cmd_analyze(
            "http://127.0.0.1:8000",
            "Acme",
            timeout_sec=30.0,
            interval_sec=0.0,
            json_mode=False,
            show_id=False,
            log=log,
        )
    assert code == 0
    out = capsys.readouterr().out
    assert "Acme" in out


def test_analyze_json_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    log = logging.getLogger("test")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    created = CreateAnalysisResponse(
        analysis_id="id-2",
        company_name="Beta",
        status="pending",
        complexity_tier="standard",
        created_at=ts,
    )
    completed = AnalysisOutputsResponse(
        analysis_id="id-2",
        company_name="Beta",
        status="failed",
        complexity_tier="standard",
        last_completed_agent="single_agent",
        created_at=ts,
        analysis_result=None,
    )
    with patch("cli.main.PreipoHttpClient") as mock_cl:
        inst = MagicMock()
        inst.create_analysis.return_value = created
        inst.get_analysis.return_value = completed
        mock_cl.return_value.__enter__.return_value = inst
        mock_cl.return_value.__exit__.return_value = None
        code = cli_main._cmd_analyze(
            "http://127.0.0.1:8000",
            "Beta",
            timeout_sec=30.0,
            interval_sec=0.0,
            json_mode=True,
            show_id=False,
            log=log,
        )
    assert code == 1
    out = capsys.readouterr().out
    assert '"analysis_id": "id-2"' in out
    assert '"status": "failed"' in out


def test_analyze_returns_error_on_poll_failure() -> None:
    log = logging.getLogger("test")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    created = CreateAnalysisResponse(
        analysis_id="id-3",
        company_name="Gamma",
        status="pending",
        complexity_tier="standard",
        created_at=ts,
    )
    with patch("cli.main.PreipoHttpClient") as mock_cl:
        inst = MagicMock()
        inst.create_analysis.return_value = created
        inst.get_analysis.side_effect = httpx.ConnectError("dropped")
        mock_cl.return_value.__enter__.return_value = inst
        mock_cl.return_value.__exit__.return_value = None
        code = cli_main._cmd_analyze(
            "http://127.0.0.1:8000",
            "Gamma",
            timeout_sec=30.0,
            interval_sec=0.0,
            json_mode=False,
            show_id=False,
            log=log,
        )
    assert code == 1


def test_export_calls_export_all(tmp_path: Path) -> None:
    log = logging.getLogger("test")
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = SingleAgentResult(company_name="Co", generated_at=ts)
    data = AnalysisOutputsResponse(
        analysis_id="e1",
        company_name="Co",
        status="completed",
        complexity_tier="standard",
        last_completed_agent="single_agent",
        created_at=ts,
        analysis_result=result,
    )
    base = str(tmp_path)
    with patch("cli.main.PreipoHttpClient") as mock_cl:
        inst = MagicMock()
        inst.get_analysis.return_value = data
        mock_cl.return_value.__enter__.return_value = inst
        mock_cl.return_value.__exit__.return_value = None
        with patch("cli.main.export_all") as exp:
            code = cli_main._cmd_export("http://127.0.0.1:8000", "e1", base, log)
    assert code == 0
    exp.assert_called_once_with(analysis_id="e1", result=result, base_dir=base)
