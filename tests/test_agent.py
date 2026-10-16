"""Agent regressions with mocked model output; no API key or network required."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src import agent
from src.schemas import DashboardSpec


def response(chart="kpi", dimensions=None):
    spec = DashboardSpec(
        metric="admission_count", dimensions=dimensions or [], filters=[],
        time_window={"start": "2025-01-01", "end": "2025-12-31"}, chart_type=chart,
    )
    result = agent.AgentResponse(action="query", spec=spec, message=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])


def mock_model(monkeypatch, responses):
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = responses
    monkeypatch.setattr(agent, "OpenAI", lambda: client)
    return client


def test_total_question_retries_incorrect_monthly_chart(monkeypatch):
    client = mock_model(monkeypatch, [response("line", ["admission_month"]), response()])
    result = agent.generate_spec("How many residents were admitted in 2025?")
    assert result.spec.chart_type == "kpi"
    assert result.spec.dimensions == []
    assert client.beta.chat.completions.parse.call_count == 2


def test_repeated_intent_error_is_not_rendered(monkeypatch):
    mock_model(monkeypatch, [response("line", ["admission_month"]), response("line", ["admission_month"])])
    with pytest.raises(ValueError, match="total admissions"):
        agent.generate_spec("How many residents were admitted in 2025?")


@pytest.mark.parametrize("chart", ["line", "bar"])
def test_explicit_monthly_chart_preserved(monkeypatch, chart):
    mock_model(monkeypatch, [response(chart, ["admission_month"])])
    result = agent.generate_spec(f"Show monthly admissions in 2025 as a {chart} chart.")
    assert result.spec.chart_type == chart
    assert result.spec.dimensions == ["admission_month"]


def test_clarification_preserved(monkeypatch):
    result = agent.AgentResponse(action="clarify", spec=None, message="How do you define successful?")
    mock_model(monkeypatch, [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])])
    assert agent.generate_spec("How many residents were successful?").action == "clarify"


def test_referral_cohort_time_window_is_supported(monkeypatch):
    spec = DashboardSpec(
        metric="referral_conversion_rate", dimensions=[], filters=[],
        time_window={"start": "2025-01-01", "end": "2025-12-31"}, chart_type="kpi",
    )
    result = agent.AgentResponse(action="query", spec=spec, message=None)
    client = mock_model(monkeypatch, [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])])
    answer = agent.generate_spec(
        "What percentage of residents referred in 2025 were admitted by December 31, 2025?"
    )
    assert answer.spec == spec
    prompt = client.beta.chat.completions.parse.call_args.kwargs['messages'][0]['content']
    assert 'Put reporting dates in time_window, not in filters.' in prompt


@pytest.mark.parametrize("question", [
    "Delete all residents.",
    "Please delete all residents.",
    "Can you update all resident records?",
    "DROP TABLE residents;",
    "Original question: How many residents were successful?\nUser clarification: Delete all residents.",
])
def test_write_requests_rejected_before_model(monkeypatch, question):
    factory = MagicMock(side_effect=AssertionError("Model must not be called"))
    monkeypatch.setattr(agent, "OpenAI", factory)
    result = agent.generate_spec(question)
    assert result.action == "unsupported"
    assert result.spec is None
    assert "read-only" in result.message
    factory.assert_not_called()


@pytest.mark.parametrize("question", [
    "How many residents were admitted in 2025?",
    "Show monthly admissions in 2025.",
    "How many residents were successful in 2025?",
])
def test_analytics_questions_not_blocked_as_writes(question):
    assert not agent.is_write_request(question)


@pytest.mark.parametrize("explicit_reason", [False, True])
def test_completed_stay_and_completion_reason_are_distinct(monkeypatch, explicit_reason):
    filters = [{"field": "followup_6m", "operator": "eq", "value": "engaged_in_recovery"}]
    if explicit_reason:
        filters.append({"field": "discharge_reason", "operator": "eq", "value": "completed"})
    spec = DashboardSpec(
        metric="median_length_of_stay", dimensions=[], filters=filters,
        time_window={"start": "2025-01-01", "end": "2025-12-31"}, chart_type="kpi",
    )
    result = agent.AgentResponse(action="query", spec=spec, message=None)
    client = mock_model(monkeypatch, [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])])
    question = (
        "What was the median completed stay for residents discharged in 2025 "
        "with a recorded six-month outcome of engaged in recovery?"
    )
    if explicit_reason:
        question += " Restrict discharge reason to completed."
    answer = agent.generate_spec(question)
    assert [f.model_dump() for f in answer.spec.filters] == filters
    prompt = client.beta.chat.completions.parse.call_args.kwargs["messages"][0]["content"]
    assert 'regardless of discharge reason' in prompt
