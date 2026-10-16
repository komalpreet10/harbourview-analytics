
"""Validate dashboard specifications."""

from src.schemas import DashboardSpec


ALLOWED_VALUES = {
    "current_status": {
        "not_admitted", "discharged", "alumni",
        "aftercare", "phase_1", "phase_2", "phase_3",
    },
    "discharge_reason": {
        "completed", "self_discharge",
        "administrative", "transfer", "other",
    },
}

FOLLOWUP_VALUES = {
    "engaged_in_recovery", "relapse_reported", "lost_to_follow_up",
    "unknown", "not_yet_due",
}
ALLOWED_VALUES["followup_6m"] = FOLLOWUP_VALUES
ALLOWED_VALUES["followup_12m"] = FOLLOWUP_VALUES


def validate_spec(spec: DashboardSpec) -> DashboardSpec:

    # Metric and dimension compatibility
    allowed_dimensions = {
        "admission_count": ["admission_month"],
        "referral_conversion_rate": [],
        "occupancy_rate": ["occupancy_month"],
        "median_length_of_stay": [],
    }

    if len(spec.dimensions) != len(set(spec.dimensions)):
        raise ValueError("Duplicate dimensions")

    if any(
        d not in allowed_dimensions[spec.metric]
        for d in spec.dimensions
    ):
        raise ValueError("Invalid dimension for metric")

    # Chart compatibility
    if spec.chart_type == "kpi" and spec.dimensions:
        raise ValueError("KPI cannot have dimensions")

    if spec.chart_type in ("bar", "line"):
        if len(spec.dimensions) != 1:
            raise ValueError("Bar/line requires one dimension")

    if len(spec.filters) > 10:
        raise ValueError("Maximum 10 filters")

    # Filter validation
    for f in spec.filters:
        if f.operator == "eq" and isinstance(f.value, list):
            raise ValueError("'eq' requires a single value")

        if isinstance(f.value, list) and len(f.value) > 50:
            raise ValueError("Maximum 50 filter values")

        if f.operator == "in":
            if not isinstance(f.value, list) or not f.value:
                raise ValueError("'in' requires a nonempty list")

        if f.field == "fee_waived":
            if f.operator != "eq" or type(f.value) is not bool:
                raise ValueError("fee_waived requires true or false")
        else:
            values = f.value if isinstance(f.value, list) else [f.value]

            if any(
                type(v) is not str or v not in ALLOWED_VALUES[f.field]
                for v in values
            ):
                raise ValueError(f"Invalid value for {f.field}")

    # Avoid misleading historical occupancy calculations
    if spec.metric == "occupancy_rate" and spec.filters:
        raise ValueError("Occupancy does not support filters")

    # Avoid cohort ambiguity for conversion rates
    if spec.metric == "referral_conversion_rate" and spec.filters:
        raise ValueError("Conversion rate does not support filters")

    # Reporting period limit
    days = (spec.time_window.end - spec.time_window.start).days + 1

    if days > 366:
        raise ValueError("Maximum reporting period is 366 days")

    return spec
    

ALLOWED_STAGES = {
    "$match", "$group", "$project", "$sort", "$count", "$limit", "$facet", "$unwind",
}
ALLOWED_OPERATORS = ALLOWED_STAGES | {
    "$and", "$or", "$eq", "$ne", "$gte", "$gt", "$lt", "$lte", "$in", "$nin", "$expr",
    "$sum", "$cond", "$multiply", "$divide", "$dateTrunc", "$dateDiff", "$avg",
    "$push", "$arrayElemAt", "$floor", "$subtract", "$min", "$max", "$literal",
    "$size", "$filter", "$first",
}


def validate_pipeline(pipeline: list[dict], tenant_id: str, max_rows: int) -> None:
    """Reject unscoped pipelines, write stages, namespace escapes, and executable code.

    Only compiler output reaches execution. This validator is defense in depth,
    not an interface for accepting arbitrary client-supplied pipelines.
    """
    if not pipeline or pipeline[0] != {"$match": {"tenant_id": tenant_id}}:
        raise ValueError("Pipeline must begin with the exact tenant scope")
    if pipeline[-1] != {"$limit": max_rows}:
        raise ValueError("Pipeline must end with the configured row limit")
    if len(pipeline) > 30:
        raise ValueError("Too many aggregation stages")

    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.startswith("$") and key not in ALLOWED_OPERATORS:
                    raise ValueError(f"Unsupported aggregation operator: {key}")
                if key == "$facet":
                    for branch in child.values():
                        check_stages(branch)
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    def check_stages(stages):
        for stage in stages:
            if not isinstance(stage, dict) or len(stage) != 1 or next(iter(stage)) not in ALLOWED_STAGES:
                raise ValueError("Unsupported aggregation stage")

    check_stages(pipeline)
    inspect(pipeline)
