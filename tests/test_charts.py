"""Check calendar completion for monthly admission charts."""

from unittest.mock import patch

import pandas as pd
import pytest

from src.charts import render_chart
from src.schemas import DashboardSpec


@pytest.mark.parametrize("chart", ["line", "bar"])
@pytest.mark.parametrize("empty", [False, True])
def test_missing_admission_months_shown_as_zero(chart, empty):
    spec = DashboardSpec(metric="admission_count", dimensions=["admission_month"], filters=[],
                         time_window={"start": "2025-01-01", "end": "2025-12-31"}, chart_type=chart)
    data = pd.DataFrame({"admission_month": pd.to_datetime([] if empty else ["2025-01-01", "2025-04-01"]),
                         "value": [] if empty else [4, 1]})
    original = data.copy(deep=True)
    with patch("src.charts.st.plotly_chart") as display:
        render_chart(spec, data)
        trace = display.call_args.args[0].data[0]
        assert len(trace.x) == 12
        assert list(trace.y) == ([0] * 12 if empty else [4, 0, 0, 1] + [0] * 8)
    pd.testing.assert_frame_equal(data, original)
