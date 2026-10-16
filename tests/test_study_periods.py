from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_period_summary_allows_unequal_windows_and_dynamic_p90(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_periods", {"output": "summary", "time_field": "order_date",
            "unit": "order", "metrics": [], "measures": [{"id": "p90", "stat": "quantile", "field": "delivery_days", "q": .9}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-01", "end": "2017-12-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-04-01"}]})
        assert result["success"], result
        assert result["result_kind"] == "periods"
        assert result["metadata"]["periods"][0]["duration_days"] == 61
        assert [row["p90"] for row in result["rows"]] == [7.7, 9.2]
    finally:
        ds.close()


def test_period_series_spine_uses_null_for_absent_bucket(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_periods", {"output": "series", "grain": "month", "time_field": "order_date",
            "unit": "order", "metrics": [], "measures": [{"id": "mean_days", "stat": "mean", "field": "delivery_days"}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-01", "end": "2018-01-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-04-01"}],
            "comparison": {"reference_period_id": "a", "outputs": ["difference"]}})
        assert result["success"], result
        absent = next(row for row in result["rows"] if row["period_id"] == "a" and row["bucket_index"] == 2)
        assert absent["bucket_present"] is False and absent["record_count"] == 0
        assert absent["mean_days"] is None and absent["mean_days__difference"] is None
        assert "complete" not in " ".join(result["metadata"].keys()).lower()
    finally:
        ds.close()


def test_period_series_requires_calendar_alignment_and_equal_buckets(olist_csvs):
    ds = _load(olist_csvs)
    try:
        bad = ds.execute("compare_periods", {"output": "series", "grain": "month", "time_field": "order_date",
            "unit": "order", "metrics": ["order_count"], "periods": [
                {"id": "a", "label": "A", "start": "2017-10-02", "end": "2018-01-01"},
                {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-04-01"}]})
        assert not bad["success"] and bad["error"]["code"] == "INCOMPATIBLE_PERIODS"
    finally:
        ds.close()


def test_period_quantile_pool_and_shared_date_clipping_suppress_deltas(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_periods", {"output": "summary", "time_field": "order_date", "unit": "order", "metrics": [],
            "filters": [{"id": "middle", "field": "delivery_days", "op": "quantile_between", "value": {"lower": .2, "upper": .8}}],
            "measures": [{"id": "days", "stat": "mean", "field": "delivery_days"}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-02", "end": "2017-12-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-03-01"}],
            "comparison": {"reference_period_id": "a", "outputs": ["difference"]}},
            scope=[{"field": "order_date", "op": "gte", "value": "2017-11-01"}])
        assert result["success"], result
        assert result["metadata"]["quantile_rules"][0]["base_valid_count"] == 3
        assert result["metadata"]["comparison_suppressed_reasons"] == ["shared_date_filter"]
        assert all(row["days__difference"] is None for row in result["rows"])
        assert len(result["metadata"]["row_valid_counts"]) == len(result["rows"])
    finally:
        ds.close()


def test_wide_shared_date_scope_does_not_falsely_suppress_comparison(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_periods", {"output": "summary", "time_field": "order_date", "unit": "order",
            "metrics": [], "measures": [{"id": "days", "stat": "mean", "field": "delivery_days"}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-02", "end": "2017-12-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-03-01"}],
            "comparison": {"reference_period_id": "a", "outputs": ["difference"]}},
            scope=[{"field": "order_date", "op": "gte", "value": "2017-01-01"},
                   {"field": "order_date", "op": "lt", "value": "2019-01-01"}])
        assert result["success"], result
        assert result["metadata"]["comparison_suppressed_reasons"] == []
        assert result["rows"][1]["days__difference"] is not None
        assert all(period["within_observed_date_extent"] for period in result["metadata"]["periods"])
    finally:
        ds.close()


def test_period_grouping_does_not_silently_drop_groups_at_display_limits(olist_csvs):
    ds = _load(olist_csvs)
    try:
        ds._interface.con.execute("""
            INSERT INTO order_grain
            SELECT base.* REPLACE (
                'period-group-' || CAST(i AS VARCHAR) AS order_id,
                'GROUP-' || lpad(CAST(i AS VARCHAR), 3, '0') AS customer_state,
                CAST(i AS DOUBLE) AS delivery_days)
            FROM range(150) AS generated(i)
            CROSS JOIN (SELECT * FROM order_grain WHERE order_id = 'o1') AS base
        """)
        result = ds.execute("compare_periods", {"output": "summary", "time_field": "order_date",
            "unit": "order", "group_by": ["customer_state"], "metrics": [],
            "measures": [{"id": "days", "stat": "mean", "field": "delivery_days"}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-01", "end": "2017-12-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-04-01"}]})
        assert result["success"], result
        assert any(row["customer_state"] == "GROUP-149" and row["period_id"] == "a" for row in result["rows"])
        assert len({row["customer_state"] for row in result["rows"]}) > 100
        assert result["truncated"] is False
    finally:
        ds.close()


def test_mixed_period_valid_counts_are_row_aligned_by_group(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("compare_periods", {"output": "summary", "time_field": "order_date",
            "unit": "order", "group_by": ["customer_state"], "metrics": ["order_count"],
            "measures": [{"id": "score", "stat": "mean", "field": "review_score"}],
            "periods": [{"id": "a", "label": "A", "start": "2017-10-01", "end": "2018-01-01"},
                        {"id": "b", "label": "B", "start": "2018-01-01", "end": "2018-04-01"}]})
        assert result["success"], result
        paired = list(zip(result["rows"], result["metadata"]["row_valid_counts"]))
        sp_a = next(counts for row, counts in paired if row["period_id"] == "a" and row["customer_state"] == "SP")
        rj_b = next(counts for row, counts in paired if row["period_id"] == "b" and row["customer_state"] == "RJ")
        assert sp_a == {"order_count": 2, "score": 2}
        assert rj_b == {"order_count": 2, "score": 2}
    finally:
        ds.close()
