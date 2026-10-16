from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_arbitrary_quantile_output_is_chart_ready(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("distribution", {"unit": "item", "field": "price",
            "output": "quantiles", "quantiles": [0, .5, .9, 1]})
        assert result["success"], result
        assert [row["value"] for row in result["rows"]] == [0, 70, 144, 200]
        assert result["result_kind"] == "quantiles"
        assert result["columns"]["quantile"]["type"] == "quantitative"
    finally:
        ds.close()
