"""Local identifier screening must prevent model calls on flagged input."""

from unittest.mock import patch

import pytest

from src.agent import generate_spec
from src.privacy import contains_identifiers


@pytest.mark.parametrize("text", [
    "Email jane@example.com about admissions",
    "Call 604-555-0123", "Call (604) 555-0123", "Call 6045550123",
    "Show resident HV-0001", "Resident id: 12345678",
    "health card: 1234 567 890",
    "Original question: Admissions in 2025\nUser clarification: jane@example.com",
])
def test_identifier_blocks_model(text):
    assert contains_identifiers(text)
    with patch("src.agent.OpenAI") as client:
        result = generate_spec(text)
        assert result.action == "unsupported"
        assert result.spec is None
        assert text not in result.message
        client.assert_not_called()


@pytest.mark.parametrize("text", [
    "How many residents were admitted in 2025?",
    "Show monthly admissions from 2025-01-01 to 2025-12-31",
    "What percentage had a recorded six-month outcome of engaged in recovery?",
])
def test_aggregate_questions_pass_screen(text):
    assert not contains_identifiers(text)


@pytest.mark.parametrize("text", ["Did John Smith relapse?", "Show residents living in Toronto."])
def test_local_entity_detection(text):
    assert contains_identifiers(text)


def test_detector_failure_blocks_model():
    with patch("src.privacy.get_analyzer", side_effect=RuntimeError("unavailable")):
        with patch("src.agent.OpenAI") as client:
            with pytest.raises(RuntimeError, match="no question was sent"):
                generate_spec("Show monthly admissions in 2025")
            client.assert_not_called()
