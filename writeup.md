# Harbourview House — Take-home write-up

**Key decisions.** I used the supplied synthetic data for a 2025 analysis notebook and a small Streamlit assistant. MongoDB matches Axon’s stack. The assistant supports admissions, referral conversion, completed-stay median, and occupancy. The LLM creates a JSON specification; Python validates its metric, dates, filters, grouping, and chart type before building a read-only aggregation. Displayed numbers come from MongoDB.

**Assumptions.** Reporting covers January–December 2025. The funnel follows residents referred in 2025 through year end. Admission day counts as occupied; discharge day does not. Earlier stays contribute where they overlap 2025. Aftercare and alumni are assumed to follow residential discharge. Ongoing stays are censored at year end and reported separately. Follow-ups are assumed due six/twelve months after discharge. Every outcome rate includes everyone due, with lost-to-follow-up, unknown, and missing outcomes shown separately. Engagement is not proof of sobriety. Collection dates are absent, so outcomes cannot be confirmed as known at year end.

**Trade-offs and safeguards**. I limited the assistant to four metrics to make it easier to test, although this means it cannot answer every question. Admissions with missing intake dates are still counted, but unreliable and unfinished waiting times are excluded, which may make waits appear shorter. Three discharged residents have no discharge date, so their stays are excluded from occupancy and stay-length calculations; this may undercount occupancy. Their follow-up eligibility is also unknown. The app uses read-only access, tenant checks, and query limits. Harbourview is a fixed demo tenant, with no user login. Privacy checks can miss sensitive information or block harmless questions. Staff notes and query results are not sent to the LLM. 

**Next steps**. I would confirm the metric definitions and follow-up starting point with the house, resolve missing dates, and record when follow-up outcomes were collected. I would then test more real questions against expected specifications and independently checked results. Before production, I would add user authentication, audit logging, protected chat history, and approved Canadian model hosting. Caching and dashboard-spec versioning would follow.


**Task C1 — Notes to structure.** I would combine abbreviation rules with structured LLM extraction in an approved Canadian environment. Fields would include meeting attendance, passes, incidents, and documented mood/risk observations. Each value would retain supporting text, dates, negation, and uncertainty; unmentioned information stays unknown. Schema validation checks structure, not factual correctness. Staff review would be required for uncertain or consequential flags.

**Task C2 — Accuracy.** 
I would evaluate accuracy using five steps:
1. Evaluation set: Create a dataset of 300–500 representative staff notes, including normal, ambiguous, contradictory, and edge cases.
2. Human labeling: Have two staff members independently label the notes to establish ground truth and resolve disagreements.
3. Metrics: Measure precision, recall, and F1 score for each extracted field. Also track hallucination rates, false positives, and false negatives, especially for incident and risk flags.
4. Human-in-the-loop: Route uncertain or sensitive cases to staff for review. Use their corrections to improve the system and regularly audit accepted predictions.
5. Drift monitoring: Monitor changes in staff terminology, data patterns, and extraction accuracy. Periodically test against newly labeled notes and update prompts or models when performance declines.

**Task C3 — Predictive idea.** 
I would forecast weekly occupied beds four weeks ahead to help staff plan staffing and admissions.
- Data needed: Several years of reliable admissions, discharges, daily occupancy, capacity changes, referrals, and waitlist records.
- Main risks: Small samples and changing demand could produce unreliable forecasts. Historical access inequalities could carry into predictions. Forecasts could be misused to deny admissions.
- Before shipping: Compare against simple baselines using time-based tests, measure forecast error and uncertainty, check performance across periods and relevant groups, and pilot with staff oversight. Forecasts should support planning, never automatically decide admissions.

**AI disclosure.** I used ChatGPT/Codex for implementation, debugging, explanations, tests, and documentation drafting.
