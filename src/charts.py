
"""Display dashboard query results using Streamlit."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.schemas import DashboardSpec


def render_chart(spec: DashboardSpec, df):
    """Render a chart using the database results."""

    if spec.metric == "admission_count" and spec.dimensions == ["admission_month"]:
        months = pd.date_range(
            pd.Timestamp(spec.time_window.start).replace(day=1),
            pd.Timestamp(spec.time_window.end).replace(day=1),
            freq="MS",
        )
        df = df.copy()
        df["admission_month"] = pd.to_datetime(df["admission_month"])
        df = (
            df.set_index("admission_month")
            .reindex(months, fill_value=0)
            .rename_axis("admission_month")
            .reset_index()
        )

    if df.empty or df["value"].isna().all():
        st.info("No data available for the selected period.")
        return

    # Single-number metric
    if spec.chart_type == "kpi":
        value = df["value"].iloc[0]

        if spec.metric in ("occupancy_rate", "referral_conversion_rate"):
            st.metric("Result", f"{value:.1f}%")

        elif spec.metric == "median_length_of_stay":
            st.metric("Median length of stay", f"{value:.1f} days")

        else:
            st.metric("Admissions", f"{int(value)}")

    else:
        dimension = spec.dimensions[0]
        x_label = "Admission month" if dimension == "admission_month" else "Occupancy month"
        y_label = "Admissions" if spec.metric == "admission_count" else "Occupancy (%)"
        data = df.sort_values(dimension)
        chart = px.line if spec.chart_type == "line" else px.bar
        fig = chart(
            data, x=dimension, y="value",
            labels={dimension: x_label, "value": y_label},
            template="simple_white",
        )
        if spec.chart_type == "line":
            fig.update_traces(mode="lines+markers")
        fig.update_xaxes(
            dtick="M1", tickformat="%b\n%Y",
            hoverformat="%B %Y",
        )
        fig.update_yaxes(rangemode="tozero")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
