"""Compile validated specs into bounded, tenant-scoped MongoDB aggregations."""

import os
from datetime import datetime, time, timedelta
from itertools import islice

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient, timeout
from pymongo.errors import ExecutionTimeout, PyMongoError

from src.schemas import DashboardSpec
from src.validator import validate_pipeline, validate_spec

COLLECTION = "residents"
MAX_ROWS = 100
MAX_TIME_MS = 5000
CLIENT_TIMEOUT_SECONDS = 6
# Trusted server configuration, never supplied by the model or question.
TENANTS = {"harbourview": "harbourview"}
EXIT_STATUSES = ["discharged", "alumni", "aftercare"]


def compile_pipeline(spec: DashboardSpec, tenant_id: str) -> list[dict]:
    """Compile only supported metrics; no raw model-generated pipeline is accepted."""
    spec = DashboardSpec.model_validate(spec.model_dump())
    validate_spec(spec)
    if tenant_id not in TENANTS:
        raise PermissionError("Unknown tenant")
    start = datetime.combine(spec.time_window.start, time.min)
    end = datetime.combine(spec.time_window.end + timedelta(days=1), time.min)
    date_field = {
        "admission_count": "admission_date",
        "referral_conversion_rate": "referral_date",
        "median_length_of_stay": "discharge_date",
    }.get(spec.metric)
    pipeline = [{"$match": {"tenant_id": tenant_id}}]
    conditions = []
    if date_field:
        conditions.append({date_field: {"$gte": start, "$lt": end}})
    for f in spec.filters:
        conditions.append({f.field: {"$eq" if f.operator == "eq" else "$in": f.value}})
    if conditions:
        pipeline.append({"$match": {"$and": conditions}})

    if spec.metric == "admission_count":
        if spec.dimensions:
            pipeline += [
                {"$group": {"_id": {"$dateTrunc": {"date": "$admission_date", "unit": "month"}}, "value": {"$sum": 1}}},
                {"$project": {"_id": 0, "admission_month": "$_id", "value": 1}},
                {"$sort": {"admission_month": 1}},
            ]
        else:
            pipeline.append({"$count": "value"})
    elif spec.metric == "referral_conversion_rate":
        pipeline += [
            {"$group": {"_id": None, "denominator": {"$sum": 1}, "numerator": {"$sum": {"$cond": [
                {"$and": [{"$ne": ["$admission_date", None]}, {"$gte": ["$admission_date", "$referral_date"]}, {"$lt": ["$admission_date", end]}]}, 1, 0,
            ]}}}},
            {"$project": {"_id": 0, "numerator": 1, "denominator": 1, "value": {"$multiply": [100, {"$divide": ["$numerator", "$denominator"]}]}}},
        ]
    elif spec.metric == "median_length_of_stay":
        pipeline += [
            {"$match": {"admission_date": {"$ne": None}, "$expr": {"$gte": ["$discharge_date", "$admission_date"]}}},
            {"$project": {"days": {"$dateDiff": {"startDate": "$admission_date", "endDate": "$discharge_date", "unit": "day"}}}},
            {"$sort": {"days": 1}},
            {"$group": {"_id": None, "days": {"$push": "$days"}, "count": {"$sum": 1}}},
            # Exact median: average the two middle values (same value for odd n).
            {"$project": {"_id": 0, "count": 1, "value": {"$avg": [
                {"$arrayElemAt": ["$days", {"$floor": {"$divide": [{"$subtract": ["$count", 1]}, 2]}}]},
                {"$arrayElemAt": ["$days", {"$floor": {"$divide": ["$count", 2]}}]},
            ]}}},
        ]
    else:
        # Bounded calendar (<=366 days); only dates and capacity enter this facet.
        days = [start + timedelta(days=i) for i in range((end - start).days)]
        pipeline += [
            {"$facet": {
                "capacity": [{"$group": {"_id": None, "low": {"$min": "$bed_capacity"}, "high": {"$max": "$bed_capacity"}}}],
                "stays": [
                    {"$match": {"admission_date": {"$ne": None, "$lt": end}, "$or": [
                        {"discharge_date": {"$gt": start}, "$expr": {"$gte": ["$discharge_date", "$admission_date"]}},
                        {"discharge_date": None, "current_status": {"$nin": EXIT_STATUSES}},
                    ]}},
                    {"$project": {"_id": 0, "admission_date": 1, "discharge_date": 1}},
                ],
            }},
            {"$project": {"stays": 1, "capacity": {"$arrayElemAt": ["$capacity", 0]}, "day": {"$literal": days}}},
            {"$unwind": "$day"},
            {"$project": {"day": 1, "capacity": 1, "occupied": {"$size": {"$filter": {
                "input": "$stays", "as": "stay", "cond": {"$and": [
                    {"$lte": ["$$stay.admission_date", "$day"]},
                    {"$or": [{"$eq": ["$$stay.discharge_date", None]}, {"$gt": ["$$stay.discharge_date", "$day"]}]},
                ]},
            }}}}},
            {"$group": {"_id": {"$dateTrunc": {"date": "$day", "unit": "month"}} if spec.dimensions else None,
                         "average_beds": {"$avg": "$occupied"}, "capacity": {"$first": "$capacity"}}},
            {"$project": {"_id": 0, **({"occupancy_month": "$_id"} if spec.dimensions else {}),
                          "value": {"$cond": [
                              {"$and": [{"$gt": ["$capacity.low", 0]}, {"$eq": ["$capacity.low", "$capacity.high"]}]},
                              {"$multiply": [100, {"$divide": ["$average_beds", "$capacity.low"]}]}, None,
                          ]}}},
        ]
        if spec.dimensions:
            pipeline.append({"$sort": {"occupancy_month": 1}})
    pipeline.append({"$limit": MAX_ROWS})
    validate_pipeline(pipeline, tenant_id, MAX_ROWS)
    return pipeline


def verify_reader(database, database_name: str) -> None:
    """Fail closed unless credentials grant only find on this tenant collection."""
    auth = database.command("connectionStatus", showPrivileges=True).get("authInfo", {})
    privileges = auth.get("authenticatedUserPrivileges", [])
    resource = {"db": database_name, "collection": COLLECTION}
    if not auth.get("authenticatedUsers") or not privileges:
        raise PermissionError("MongoDB authentication and a collection-scoped reader are required")
    if any(p.get("resource") != resource or set(p.get("actions", [])) != {"find"} for p in privileges):
        raise PermissionError("Use a dedicated find-only account for this tenant collection")


def run_query(spec: DashboardSpec, tenant_id: str):
    """Execute a compiled pipeline with server and client deadlines; return aggregates only."""
    pipeline = compile_pipeline(spec, tenant_id)
    load_dotenv()
    uri = os.environ.get("MONGODB_READ_URI")
    if not uri:
        raise RuntimeError("Set MONGODB_READ_URI to the tenant's find-only MongoDB account")
    database_name = TENANTS[tenant_id]
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000) as client:
            with timeout(CLIENT_TIMEOUT_SECONDS):
                database = client[database_name]
                verify_reader(database, database_name)
                with database[COLLECTION].aggregate(
                    pipeline, maxTimeMS=MAX_TIME_MS, allowDiskUse=False, batchSize=MAX_ROWS,
                ) as cursor:
                    rows = list(islice(cursor, MAX_ROWS + 1))
        if len(rows) > MAX_ROWS:
            raise ValueError("Query exceeded the result row limit")
    except ExecutionTimeout:
        raise TimeoutError("MongoDB query exceeded its execution deadline") from None
    except PyMongoError as error:
        if error.timeout:
            raise TimeoutError("MongoDB operation exceeded its client deadline") from None
        # Never display a URI, credentials, or raw server error in Streamlit.
        raise RuntimeError("MongoDB unavailable or access denied; check local setup") from None
    if not rows and not spec.dimensions:
        rows = [{"value": 0 if spec.metric == "admission_count" else None}]
    return pd.DataFrame(rows, columns=[*spec.dimensions, "value"] if not rows else None)
