
"""JSON schema for analytics dashboard queries."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal[
        "current_status",
        "discharge_reason",
        "fee_waived",
        "followup_6m",
        "followup_12m",
    ]
    operator: Literal["eq", "in"]
    value: StrictStr | StrictBool | list[StrictStr]


class TimeWindow(BaseModel):
    """Inclusive reporting dates; the business validator caps the period."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def check_dates(self):
        if self.start > self.end:
            raise ValueError("Start date cannot be after end date")
        return self


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: Literal[
        "admission_count",
        "referral_conversion_rate",
        "occupancy_rate",
        "median_length_of_stay",
    ]

    dimensions: list[
        Literal["admission_month", "occupancy_month"]
    ] = Field(default_factory=list)

    filters: list[FilterSpec] = Field(default_factory=list)

    time_window: TimeWindow
    chart_type: Literal["kpi", "bar", "line"]
