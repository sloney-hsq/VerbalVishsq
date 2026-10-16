from test_olist_adapter import _load, olist_csvs  # noqa: F401


def test_full_data_correlations_and_summary_ignore_display_sampling(olist_csvs):
    ds = _load(olist_csvs)
    try:
        args = {"unit": "item", "x": "price", "y": "freight_value",
                "representation": "points", "correlations": ["pearson", "spearman"]}
        small = ds.execute("relationship", {**args, "sampling": {"max_points": 2, "seed": 1}})
        large = ds.execute("relationship", {**args, "sampling": {"max_points": 5, "seed": 9}})
        assert small["success"] and large["success"]
        assert small["metadata"]["correlations"] == large["metadata"]["correlations"]
        summary = ds.execute("relationship", {**args, "representation": "summary"})
        assert summary["success"], summary
        assert summary["result_kind"] == "relationship_summary"
        assert summary["rows"][0]["valid_pair_count"] == 8
    finally:
        ds.close()


def test_summary_rejects_sampling(olist_csvs):
    ds = _load(olist_csvs)
    try:
        result = ds.execute("relationship", {"unit": "item", "x": "price", "y": "freight_value",
            "representation": "summary", "sampling": {"max_points": 2}})
        assert not result["success"]
    finally:
        ds.close()
