"""Specification, aggregation, deadline, and credential safety checks."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from pymongo.errors import ExecutionTimeout

from src import database
from src.schemas import DashboardSpec
from src.validator import validate_pipeline


def make_spec(metric="admission_count", dimensions=None, filters=None):
    return DashboardSpec(
        metric=metric, dimensions=dimensions or [], filters=filters or [],
        time_window={"start": "2025-01-01", "end": "2025-12-31"},
        chart_type="line" if dimensions else "kpi",
    )


@pytest.mark.parametrize("metric,dimension", [
    ("admission_count", []), ("admission_count", ["admission_month"]),
    ("referral_conversion_rate", []), ("median_length_of_stay", []),
    ("occupancy_rate", []), ("occupancy_rate", ["occupancy_month"]),
])
def test_compiler_scopes_and_bounds_all_metrics(metric, dimension):
    pipeline = database.compile_pipeline(make_spec(metric, dimension), "harbourview")
    assert pipeline[0] == {"$match": {"tenant_id": "harbourview"}}
    assert pipeline[-1] == {"$limit": database.MAX_ROWS}


@pytest.mark.parametrize("stage", ["$out", "$merge", "$lookup", "$unionWith", "$function", "$where"])
def test_unsafe_operators_blocked_including_nested(stage):
    for unsafe in ({stage: "other"}, {"$facet": {"hidden": [{stage: "other"}]}}):
        pipeline = [{"$match": {"tenant_id": "harbourview"}}, unsafe, {"$limit": 100}]
        with pytest.raises(ValueError):
            validate_pipeline(pipeline, "harbourview", 100)


def test_unscoped_or_unbounded_pipeline_rejected():
    pipeline = database.compile_pipeline(make_spec(), "harbourview")
    with pytest.raises(ValueError):
        validate_pipeline(pipeline[1:], "harbourview", 100)
    with pytest.raises(ValueError):
        validate_pipeline(pipeline[:-1], "harbourview", 100)
    with pytest.raises(ValueError):
        validate_pipeline(pipeline, "another_house", 100)


def test_unknown_tenant_rejected_before_connection():
    with pytest.raises(PermissionError):
        database.run_query(make_spec(), "another_house")


@pytest.mark.parametrize("field,value", [
    ("tenant_id", "other"), ("current_status", {"$ne": None}),
    ("current_status", "phase_1'; DROP TABLE residents; --"), ("fee_waived", 1),
])
def test_invalid_filters_rejected(field, value):
    with pytest.raises((ValidationError, ValueError)):
        database.compile_pipeline(make_spec(filters=[{"field": field, "operator": "eq", "value": value}]), "harbourview")


def test_time_window_bounded():
    spec = make_spec()
    spec.time_window.end = spec.time_window.end.replace(year=2027)
    with pytest.raises(ValueError):
        database.compile_pipeline(spec, "harbourview")


def reader_info():
    return {"authInfo": {"authenticatedUsers": [{"user": "reader", "db": "harbourview"}],
            "authenticatedUserPrivileges": [{"resource": {"db": "harbourview", "collection": "residents"}, "actions": ["find"]}]}}


def test_credentials_must_be_find_only_and_collection_scoped():
    db = MagicMock()
    info = reader_info()
    db.command.return_value = info
    database.verify_reader(db, "harbourview")
    for changed in ("write", "other_tenant", "unauthenticated"):
        invalid = deepcopy(info)
        if changed == "write":
            invalid["authInfo"]["authenticatedUserPrivileges"][0]["actions"].append("insert")
        elif changed == "other_tenant":
            invalid["authInfo"]["authenticatedUserPrivileges"][0]["resource"]["db"] = "other"
        else:
            invalid["authInfo"]["authenticatedUsers"] = []
        db.command.return_value = invalid
        with pytest.raises(PermissionError):
            database.verify_reader(db, "harbourview")


def test_execution_options_and_timeout(monkeypatch):
    monkeypatch.setenv("MONGODB_READ_URI", "mongodb://unused")
    client = MagicMock()
    monkeypatch.setattr(database, "MongoClient", MagicMock(return_value=client))
    db = client.__enter__.return_value.__getitem__.return_value
    db.command.return_value = reader_info()
    collection = db.__getitem__.return_value
    collection.aggregate.side_effect = ExecutionTimeout("server deadline")
    with pytest.raises(TimeoutError):
        database.run_query(make_spec(), "harbourview")
    kwargs = collection.aggregate.call_args.kwargs
    assert kwargs["maxTimeMS"] == database.MAX_TIME_MS
    assert kwargs["allowDiskUse"] is False
    assert kwargs["batchSize"] == database.MAX_ROWS


def test_defensive_result_cap(monkeypatch):
    monkeypatch.setenv("MONGODB_READ_URI", "mongodb://unused")
    client = MagicMock()
    monkeypatch.setattr(database, "MongoClient", MagicMock(return_value=client))
    db = client.__enter__.return_value.__getitem__.return_value
    db.command.return_value = reader_info()
    cursor = db.__getitem__.return_value.aggregate.return_value.__enter__.return_value
    cursor.__iter__.return_value = iter([{"value": 1}] * (database.MAX_ROWS + 1))
    with pytest.raises(ValueError, match="row limit"):
        database.run_query(make_spec(), "harbourview")


@pytest.mark.parametrize("field", ["followup_6m", "followup_12m"])
@pytest.mark.parametrize("metric", ["admission_count", "median_length_of_stay"])
@pytest.mark.parametrize("operator,value", [
    ("eq", "lost_to_follow_up"),
    ("in", ["engaged_in_recovery", "relapse_reported"]),
])
def test_followup_filters_compile(field, metric, operator, value):
    pipeline = database.compile_pipeline(make_spec(metric, filters=[
        {"field": field, "operator": operator, "value": value},
    ]), "harbourview")
    assert {field: {"$eq" if operator == "eq" else "$in": value}} in pipeline[1]["$match"]["$and"]


@pytest.mark.parametrize("field", ["followup_6m", "followup_12m"])
@pytest.mark.parametrize("value", ["sober", "missing", True, {"$ne": None}])
def test_invalid_followup_values_rejected(field, value):
    with pytest.raises((ValidationError, ValueError)):
        database.compile_pipeline(make_spec(filters=[
            {"field": field, "operator": "eq", "value": value},
        ]), "harbourview")


@pytest.mark.parametrize("metric", ["occupancy_rate", "referral_conversion_rate"])
def test_followup_filters_cannot_change_rate_denominators(metric):
    with pytest.raises(ValueError, match="does not support filters"):
        database.compile_pipeline(make_spec(metric, filters=[
            {"field": "followup_6m", "operator": "eq", "value": "engaged_in_recovery"},
        ]), "harbourview")
