"""Import supplied synthetic records and provision a separate find-only account.

Run manually with setup credentials; the dashboard never imports this module.
"""

import csv
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    uri = os.environ.get("MONGODB_SETUP_URI")
    password = os.environ.get("MONGODB_READER_PASSWORD")
    if not uri or not password:
        raise SystemExit("Set MONGODB_SETUP_URI and MONGODB_READER_PASSWORD locally")
    with (ROOT / "data/harbourview_residents.csv").open(encoding="utf-8-sig", newline="") as source:
        records = []
        for row in csv.DictReader(source):
            row.pop("staff_note", None)  # Free text is unnecessary for these metrics.
            for field in ("referral_date", "intake_date", "admission_date", "discharge_date"):
                row[field] = datetime.fromisoformat(row[field]) if row[field] else None
            row["fee_waived"] = {"True": True, "False": False, "": None}[row["fee_waived"]]
            row["entrance_fee"] = float(row["entrance_fee"]) if row["entrance_fee"] else None
            row["bed_capacity"] = int(row["bed_capacity"])
            row["tenant_id"] = "harbourview"
            records.append(row)
    with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
        db = client.harbourview
        db.residents.create_index([("tenant_id", 1), ("resident_id", 1)], unique=True)
        for field in ("referral_date", "admission_date", "discharge_date"):
            db.residents.create_index([("tenant_id", 1), (field, 1)])
        db.residents.bulk_write([
            ReplaceOne({"tenant_id": row["tenant_id"], "resident_id": row["resident_id"]}, row, upsert=True)
            for row in records
        ])
        role = "analytics_reader"
        privileges = [{"resource": {"db": "harbourview", "collection": "residents"}, "actions": ["find"]}]
        exists = db.command("rolesInfo", role)["roles"]
        db.command("updateRole" if exists else "createRole", role, privileges=privileges, roles=[])
        exists = db.command("usersInfo", "analytics_app")["users"]
        db.command("updateUser" if exists else "createUser", "analytics_app", pwd=password,
                   roles=[{"role": role, "db": "harbourview"}])
    print(f"Imported {len(records)} synthetic residents; find-only analytics_app provisioned.")


if __name__ == "__main__":
    main()
