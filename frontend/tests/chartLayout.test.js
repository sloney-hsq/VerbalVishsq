import test from "node:test";
import assert from "node:assert/strict";

import { isMultiSeriesLine } from "../src/chartLayout.js";

test("identifies a line chart with a series", () => {
  assert.equal(isMultiSeriesLine({
    chart_type: "line",
    color: "product_category",
  }), true);
});

test("keeps single-series lines and other chart types at one column", () => {
  assert.equal(isMultiSeriesLine({ chart_type: "line", color: null }), false);
  assert.equal(isMultiSeriesLine({ chart_type: "bar", color: "review_score" }), false);
});
