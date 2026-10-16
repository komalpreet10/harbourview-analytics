# Design

## Flow and scope

**Question → local privacy check → clarification if needed → JSON spec → validation → MongoDB aggregation → results → chart.**

The notebook covers the full descriptive analysis. The Streamlit assistant supports four metrics:

| Metric | Meaning |
|---|---|
| `admission_count` | Admissions within the selected dates; optionally monthly |
| `referral_conversion_rate` | Referrals within the window admitted by its end / all referrals in that window |
| `median_length_of_stay` | Median valid stay length for residents discharged within the window |
| `occupancy_rate` | Occupied bed-days / available bed-days; optionally monthly |

Dates are inclusive. Ongoing-stay medians and eligible follow-up outcome rates remain outside the agent's scope. Admission day counts towards occupancy; discharge day does not. Exit-status residents with missing discharge dates are excluded, potentially understating occupancy.

## Specification and validation

`agent.py` uses `gpt-4o-mini` to create a JSON spec containing metric, dimensions, filters, time window, and chart type. `schemas.py` enforces types and allow-listed fields; `validator.py` checks values, operators, compatible combinations, and limits.

Admission counts and stay medians accept filters for current status, discharge reason, fee waiver, and recorded six-/twelve-month outcomes. `eq` takes one value; `in` takes a nonempty string list. Waiver accepts boolean `eq` only. Occupancy and conversion do not accept filters. Snapshot status and follow-up values do not establish historical status or collection dates.

Charts support KPI, line, and bar. The model can still choose an unintended chart or filter.

## Clarification and hallucination controls

Ambiguous terms and missing essential dates should trigger clarification before querying:

> User: How many residents were successful in 2025?  
> Assistant: How should successful be defined?  
> User: Residents admitted in 2025 whose discharge reason is completed.

The expected spec uses admission count, the 2025 window, and `discharge_reason eq completed`. The app retains the pending question and clarification reply; general conversational follow-ups are not supported.

The LLM never generates executable queries or analytical figures. Python builds approved aggregations, and charts use database results directly. Invalid specs are rejected and retried once.

## Query safety and tenant isolation

`scripts/setup_mongodb.py` imports the supplied CSV separately, converts types, excludes staff notes, and adds `tenant_id=harbourview`. It provisions a collection-scoped account with only `find` permission. Runtime verifies actual authenticated permissions before each query.

Pipelines begin with an exact tenant match. Recursive allow-lists block `$out`, `$merge`, cross-collection stages, and executable code. Limits are 100 result rows, 366 reporting days, five seconds of server execution, and a six-second client deadline. Typed filter values are not executable query code. Early write-command checks supplement database-enforced permissions.

Harbourview is a fixed demo tenant, not user authentication. Production must derive membership from login and select tenant-specific credentials from trusted server configuration. Unknown tenants are rejected; the model cannot choose the database.

## Privacy and deployment

The LLM receives the user’s question, schema, and metric definitions—not resident records, staff notes, or query results. Local regex and Presidio screening block detected identifiers before model calls; they do not redact text and may miss PHI. Raw questions remain in session history.

This prototype uses synthetic inputs with the hosted OpenAI API. Production would require an approved Canadian-hosted model deployment, appropriate agreements, and verified Canadian data residency before any third-party PHI exposure. Stronger free-text redaction and protected chat history are future work.

Audit logging is proposed, not implemented. It would record user/tenant, validated spec, versions, execution status, duration, and result size, while excluding credentials and sensitive text. Logs would have restricted access and a defined retention period.

## Evaluation and future work

Tests cover mocked agent responses, spec validation, query safety, local privacy screening, and chart month completion. Opt-in real MongoDB tests compare metrics against independent CSV calculations and verify denied writes and other-tenant reads.

I would maintain a versioned set of natural-language questions with expected actions, JSON specifications, and query results. It would include paraphrases, filters, ambiguous questions, unsupported metrics, and write requests. Expected numbers would be calculated independently from the CSV.

I would measure valid-spec rates, correct interpretation, numerical accuracy, and appropriate clarification or rejection. The same tests would run after prompt, model, schema, or metric changes to detect regressions.
Current automated tests cover application behaviour and database correctness.
