"""Opt-in tests against an isolated MongoDB 8+ test server, never production."""

import csv
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from scripts.setup_mongodb import main as import_csv
from src import database
from src.schemas import DashboardSpec


@pytest.fixture(scope="module")
def mongo():
    uri = os.environ.get("AXON_TEST_MONGO_SETUP_URI")
    if not uri:
        pytest.skip("Set AXON_TEST_MONGO_SETUP_URI for an isolated MongoDB test server")
    # A throwaway server is mandatory: these databases are test fixtures.
    admin = MongoClient(uri, serverSelectionTimeoutMS=3000)
    old = {key: os.environ.get(key) for key in ("MONGODB_SETUP_URI", "MONGODB_READER_PASSWORD", "MONGODB_READ_URI")}
    os.environ["MONGODB_SETUP_URI"] = uri
    os.environ["MONGODB_READER_PASSWORD"] = "integration-test-only"
    os.environ["MONGODB_READ_URI"] = os.environ["AXON_TEST_MONGO_READ_URI"]
    import_csv()
    # Another tenant has its own database and cannot be read by this app account.
    admin.other_house.residents.insert_one({"tenant_id": "other_house", "admission_date": datetime(2025, 1, 1)})
    yield admin
    admin.drop_database("other_house")
    admin.close()
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def spec(metric, dimensions=None):
    return DashboardSpec(metric=metric, dimensions=dimensions or [], filters=[],
                         time_window={"start": "2025-01-01", "end": "2025-12-31"},
                         chart_type="line" if dimensions else "kpi")


def test_real_metrics_match_csv(mongo):
    df = pd.read_csv(Path(__file__).resolve().parents[1] / "data/harbourview_residents.csv",
                     parse_dates=["referral_date", "admission_date", "discharge_date"])
    start, end = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01")
    admitted = df["admission_date"].between(start, end, inclusive="left")
    assert database.run_query(spec("admission_count"), "harbourview")["value"].iloc[0] == admitted.sum()
    monthly = database.run_query(spec("admission_count", ["admission_month"]), "harbourview")
    assert monthly["value"].sum() == admitted.sum()
    cohort = df[df["referral_date"].between(start, end, inclusive="left")]
    numerator = ((cohort["admission_date"] >= cohort["referral_date"]) & (cohort["admission_date"] < end)).sum()
    rate = database.run_query(spec("referral_conversion_rate"), "harbourview")["value"].iloc[0]
    assert rate == pytest.approx(100 * numerator / len(cohort))
    completed = df[df["discharge_date"].between(start, end, inclusive="left") & (df["discharge_date"] >= df["admission_date"])]
    median = (completed["discharge_date"] - completed["admission_date"]).dt.days.median()
    assert database.run_query(spec("median_length_of_stay"), "harbourview")["value"].iloc[0] == median
    unknown = df["current_status"].isin(database.EXIT_STATUSES) & df["discharge_date"].isna()
    stays = df[~unknown]
    days = pd.date_range(start, end, inclusive="left")
    daily = pd.Series([
        ((stays["admission_date"] <= day) & (stays["discharge_date"].isna() | (stays["discharge_date"] > day))).sum()
        for day in days
    ], index=days)
    expected = daily.resample("MS").mean() / df["bed_capacity"].iloc[0] * 100
    actual = database.run_query(spec("occupancy_rate", ["occupancy_month"]), "harbourview")
    assert actual["value"].tolist() == pytest.approx(expected.tolist())
    assert database.run_query(spec("occupancy_rate"), "harbourview")["value"].iloc[0] == pytest.approx(daily.mean() / 24 * 100)


def test_real_credentials_deny_writes_and_other_tenant(mongo):
    with MongoClient(os.environ["MONGODB_READ_URI"]) as reader:
        database.verify_reader(reader.harbourview, "harbourview")
        for operation in [
            lambda: reader.harbourview.residents.insert_one({"tenant_id": "harbourview"}),
            lambda: reader.harbourview.residents.delete_many({}),
            lambda: reader.harbourview.residents.update_many({}, {"$set": {"bad": True}}),
            lambda: list(reader.harbourview.residents.aggregate([{"$out": "forbidden"}])),
            lambda: list(reader.harbourview.residents.aggregate([{"$merge": "forbidden"}])),
            lambda: reader.other_house.residents.find_one({}),
        ]:
            with pytest.raises(OperationFailure) as error:
                operation()
            assert error.value.code == 13


def test_tenant_match_excludes_mislabeled_records(mongo):
    before = database.run_query(spec("admission_count"), "harbourview")["value"].iloc[0]
    inserted = mongo.harbourview.residents.insert_one({
        "tenant_id": "other_house", "resident_id": "TEST-OTHER", "admission_date": datetime(2025, 1, 1),
    }).inserted_id
    try:
        assert database.run_query(spec("admission_count"), "harbourview")["value"].iloc[0] == before
        with pytest.raises(PermissionError):
            database.run_query(spec("admission_count"), "other_house")
    finally:
        mongo.harbourview.residents.delete_one({"_id": inserted})
