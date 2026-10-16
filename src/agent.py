
"""Convert natural-language questions into dashboard specifications."""

import re
from datetime import date
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from src.privacy import contains_identifiers
from src.schemas import DashboardSpec
from src.validator import validate_spec


# Load OPENAI_API_KEY from .env
load_dotenv()



class AgentResponse(BaseModel):
    """LLM response: query, clarification, or unsupported."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["query", "clarify", "unsupported"]
    spec: DashboardSpec | None
    message: str | None


SYSTEM_PROMPT = """
Translate analytics questions into the supplied structured response schema.
Return query with a validated spec, clarify with a focused question when essential
meaning is missing, or unsupported when the request is outside these capabilities.
Query responses have message=null; other responses have spec=null.

Metric definitions:
- admission_count: admissions dated within the reporting window.
- referral_conversion_rate: all referrals dated within the window form the
  denominator; valid admissions among them by the window end form the numerator.
  The admission cutoff must equal the referral window end.
- median_length_of_stay: median admission-to-discharge days for valid stays
  discharged within the window. Admission may precede the window. A completed
  stay means a stay with a recorded discharge date, regardless of discharge reason.
  Ongoing-stay medians are unsupported; clarify if stay type is unspecified.
- occupancy_rate: occupied bed-days divided by available bed-days in the window.

Grouping and charts:
- Use kpi with dimensions=[] for an ungrouped result.
- Only admission_count supports admission_month; occupancy_rate supports
  occupancy_month. Use line for requested monthly trends, or bar if requested.
- A reporting year is a time window, not a request for monthly grouping.

Filters:
- current_status: not_admitted, discharged, alumni, aftercare, phase_1,
  phase_2, phase_3. This is the recorded snapshot status, not necessarily
  the resident's status during the reporting period.
- discharge_reason: completed, self_discharge, administrative, transfer, other.
- fee_waived: true or false; use eq only.
- followup_6m and followup_12m: engaged_in_recovery, relapse_reported,
  lost_to_follow_up, unknown, not_yet_due.

Filter rules:
- Use eq for one value and in for a nonempty list of string values.
- Add a filter only when the user requests it. Do not infer filters from
  metric names or terminology. Ask when the intended meaning is unclear.
- Filters are supported only for admission_count and median_length_of_stay.
  Use filters=[] for occupancy_rate and referral_conversion_rate.
- Put reporting dates in time_window, not in filters.
- Follow-up filters match recorded outcomes. They do not determine whether
  follow-up was due or when the outcome was collected.
- Follow-up outcome percentages and filters for blank outcomes are unsupported.
- If the population is unclear, ask whether the user means residents admitted
  or discharged during the requested period.

Dates and boundaries:
- Start and end are inclusive, with a maximum reporting period of 366 days.
- Ask for an essential missing period; use the supplied date for relative dates.
- Current status and recorded follow-up outcomes are snapshot attributes, not
  proof of status or outcome knowledge at a historical cutoff.

Safety and ambiguity:
- This assistant is read-only. Reject requests to modify records or access
  another customer's data; do not reinterpret them as analytics.
- Ask users to define ambiguous clinical terms such as successful, sober, active,
  or relapse. Explicit recorded outcome categories can be used directly.
- Never invent fields, metrics, filters, dates, or numerical answers. Never
  generate SQL or MongoDB pipelines. Figures come only from executed queries.
"""



def validate_question_intent(question: str, spec: DashboardSpec) -> None:
    """Guard the explicit total-admissions question used in the demo.

    This narrow rule is not a general natural-language intent classifier.
    Other phrasings still rely on the model and need evaluation coverage.
    """
    total_question = re.fullmatch(
        r"how many residents (?:were )?admitted in [0-9]{4}\s*[?.]?",
        question.strip(),
        flags=re.IGNORECASE,
    )
    if total_question and (
        spec.metric != "admission_count"
        or spec.dimensions
        or spec.chart_type != "kpi"
    ):
        raise ValueError(
            "The user requested total admissions, not a monthly breakdown. "
            "Use admission_count, dimensions=[], chart_type='kpi'."
        )


def is_write_request(question: str) -> bool:
    """Recognize explicit write commands, including a clarification reply.

    This is a UX guard; database permissions enforce the security boundary.
    """
    command = re.compile(
        r"^(?:(?:please|can you|could you|would you)\s+)*"
        r"(?:delete|erase|truncate|drop|insert|update|overwrite)\b",
        flags=re.IGNORECASE,
    )
    for line in question.splitlines():
        text = re.sub(r"^(?:Original question|User clarification):\s*", "", line.strip())
        if command.match(text):
            return True
    return False


def generate_spec(question: str) -> AgentResponse:
    """Generate a dashboard specification, retrying once if invalid."""

    # Scan the complete input, including original question and clarification.
    if contains_identifiers(question):
        return AgentResponse(
            action="unsupported", spec=None,
            message=("Please remove personal identifiers such as names, locations, resident IDs, "
                     "phone numbers, or email addresses and ask an aggregate question."),
        )

    if is_write_request(question):
        return AgentResponse(
            action="unsupported", spec=None,
            message="This assistant supports read-only analytics and cannot delete or modify resident records.",
        )

    client = OpenAI()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Today's date: {date.today()}\nQuestion: {question}",
        },
    ]

    for attempt in range(2):
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            response_format=AgentResponse,
            temperature=0,
        )

        result = response.choices[0].message.parsed

        if result is None:
            raise ValueError("LLM did not return a valid response")

        if result.action != "query":
            if result.spec is not None or not result.message:
                raise ValueError("Invalid agent response")
            return result

        if result.spec is None:
            raise ValueError("Missing dashboard specification")

        try:
            validate_spec(result.spec)
            validate_question_intent(question, result.spec)
            return result

        except ValueError as error:
            if attempt == 1:
                raise

            messages.append({
                "role": "assistant",
                "content": result.model_dump_json(),
            })
            messages.append({
                "role": "user",
                "content": (
                    f"Your specification failed validation: {error}. "
                    "Correct the specification without changing "
                    "the user's intended question. "
                    "For KPI charts use dimensions=[]. "
                    "For monthly charts use the appropriate dimension."
                ),
            })
