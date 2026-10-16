"""Generate reproducible synthetic fixtures, not a replacement for supplied data.

Example: python scripts/generate_data.py --rows 50 --seed 42
"""

import argparse
import calendar
import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED_CSV = ROOT / "data/harbourview_residents.csv"
FIELDS = [
    "resident_id", "referral_date", "intake_date", "admission_date",
    "current_status", "discharge_date", "discharge_reason", "entrance_fee",
    "fee_waived", "followup_6m", "followup_12m", "staff_note", "bed_capacity",
]


def add_months(day, months):
    """Match calendar-month follow-up eligibility, including month ends."""
    offset = day.month - 1 + months
    year, month = day.year + offset // 12, offset % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def generate_rows(count, seed):
    """Return fictional rows with missing-date and fee-consistency test cases.

    Assumptions are deliberately simple, not a realistic recovery population.
    The first three rows exercise admitted/missing intake, invalid intake order,
    and discharged/missing discharge. Further rows include ordinary stage paths.
    """
    rng = random.Random(seed)
    snapshot = date(2025, 12, 31)
    rows = []
    for index in range(count):
        referral = date(2024, 7, 1) + timedelta(days=rng.randrange(450))
        intake = referral + timedelta(days=rng.randint(1, 20))
        admission = intake + timedelta(days=rng.randint(1, 30))
        discharge = None
        status = rng.choice(["not_admitted", "phase_1", "phase_2", "phase_3", "discharged", "alumni", "aftercare"])
        if index < 3:
            status = "discharged"
        if status in {"discharged", "alumni", "aftercare"}:
            discharge = min(admission + timedelta(days=rng.randint(20, 180)), snapshot)
        if status == "not_admitted":
            admission = None
            if rng.choice([True, False]):
                intake = None
        reason = rng.choice(["completed", "self_discharge", "administrative", "transfer", "other"]) if discharge else ""
        waived = rng.choice([True, False]) if admission else None
        fee = (0 if waived else rng.choice([500, 750, 1000])) if admission else ""
        followups = {}
        for months in (6, 12):
            followups[f"followup_{months}m"] = (
                "" if discharge is None else
                "not_yet_due" if add_months(discharge, months) > snapshot else
                rng.choice(["engaged_in_recovery", "relapse_reported", "lost_to_follow_up", "unknown", ""])
            )
        row = {
            "resident_id": f"TEST-{index + 1:04d}",
            "referral_date": referral.isoformat(),
            "intake_date": intake.isoformat() if intake else "",
            "admission_date": admission.isoformat() if admission else "",
            "current_status": status,
            "discharge_date": discharge.isoformat() if discharge else "",
            "discharge_reason": reason,
            "entrance_fee": fee,
            "fee_waived": waived if waived is not None else "",
            **followups,
            "staff_note": "Synthetic test fixture; no real resident information.",
            "bed_capacity": 24,
        }
        if index == 0:
            row["intake_date"] = ""
        elif index == 1:
            row["intake_date"] = (referral - timedelta(days=2)).isoformat()
        elif index == 2:
            row["discharge_date"] = ""
            row["followup_6m"] = row["followup_12m"] = ""
        elif index == 3 and admission:
            row["fee_waived"], row["entrance_fee"] = True, 750
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=ROOT / "data/generated/residents_test.csv")
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("--rows must be positive")
    if args.output.resolve() == SUPPLIED_CSV.resolve():
        parser.error("The supplied CSV must not be overwritten")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects other existing files, including hard links.
    with args.output.open("x", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(generate_rows(args.rows, args.seed))
    print(f"Created {args.rows} synthetic test records: {args.output}")


if __name__ == "__main__":
    main()
