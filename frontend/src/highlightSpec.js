const FIELD_ALIASES = {
  x: "__x__",
  series: "__series__",
  color: "__series__",
};

const HIGHLIGHT_STROKE = "#f59e0b";
const TRANSPARENT = "#00000000";

/**
 * Apply a resolved data-item highlight to a Vega-Lite spec.
 *
 * `highlightElement` remains backwards compatible with the current tool API:
 *   - "2026-01"
 *   - "North"
 *   - "period=2026-01"
 *   - "period=2026-01, group=North"
 *
 * A structured object is also accepted for future callers:
 *   { field: "period", value: "2026-01" }
 *   { x_value: "2026-01", series_value: "North" }
 */
export function applyHighlightToSpec(spec, view, highlightElement) {
  const highlight = resolveHighlight(view, highlightElement);
  if (!highlight || highlight.matchedCount < 1) return spec;

  const expression = highlightExpression(highlight.clauses);
  if (!expression) return spec;

  if (view.chart_type === "line") {
    return applyLineHighlight(spec, view, highlight, expression);
  }

  return applyMarkHighlight(spec, view, expression);
}

export function resolveHighlight(view, highlightElement) {
  if (!highlightElement) return null;
  if (highlightElement.__resolvedHighlight) return highlightElement;

  const data = Array.isArray(view?.data) ? view.data : [];
  if (!data.length) return null;

  const rawClauses = clausesFromElement(view, data, highlightElement);
  if (!rawClauses.length) return null;
  const clauses = rawClauses
    .map((clause) => normalizeClause(view, data, clause))
    .filter(Boolean);

  if (clauses.length !== rawClauses.length) return null;

  const matchedCount = data.filter((datum) => datumMatchesClauses(datum, clauses)).length;
  if (matchedCount < 1) return null;
  return {
    __resolvedHighlight: true,
    clauses,
    matchedCount,
    label: clauses.map(({ field, value }) => `${field}=${formatValue(value)}`).join(" · "),
  };
}

export function datumMatchesHighlight(datum, highlight) {
  return Boolean(
    datum &&
    highlight?.clauses?.length &&
    datumMatchesClauses(datum, highlight.clauses)
  );
}

function clausesFromElement(view, data, element) {
  if (Array.isArray(element)) {
    return element.flatMap((item) => clausesFromElement(view, data, item));
  }

  if (typeof element === "object" && element !== null) {
    if (Array.isArray(element.clauses)) return element.clauses;

    const clauses = [];
    if (element.field && element.value !== undefined) {
      clauses.push({ field: element.field, value: element.value });
    }
    if (element.x_value !== undefined && view?.x_field) {
      clauses.push({ field: view.x_field, value: element.x_value });
    }
    if (element.series_value !== undefined && view?.color) {
      clauses.push({ field: view.color, value: element.series_value });
    }
    return clauses;
  }

  const text = stripQuotes(String(element || "").trim());
  if (!text) return [];

  const explicitClauses = parseExplicitClauses(text);
  if (explicitClauses.length) return explicitClauses;

  const inferred = inferClauseFromData(view, data, text);
  return inferred ? [inferred] : [];
}

function parseExplicitClauses(text) {
  const segments = text
    .split(/\s*(?:,|;|&&|\band\b|和|且)\s*/i)
    .map((item) => item.trim())
    .filter(Boolean);

  const clauses = [];
  for (const segment of segments) {
    const match = segment.match(/^([A-Za-z_][\w-]*)\s*(?:=|:|为|是)\s*(.+)$/i);
    if (!match) return [];
    clauses.push({
      field: match[1],
      value: stripQuotes(match[2].trim()),
    });
  }
  return clauses;
}

function inferClauseFromData(view, data, rawValue) {
  const fields = unique([
    view?.x_field,
    view?.color,
    ...Object.keys(view?.columns || {}),
    ...data.flatMap((row) => Object.keys(row || {})),
  ]).filter((field) => field && data.some((row) => hasOwn(row, field)));

  for (const field of fields) {
    const actual = findActualValue(data, field, rawValue);
    if (actual.found) return { field, value: actual.value };
  }
  return null;
}

function normalizeClause(view, data, clause) {
  if (!clause || clause.value === undefined) return null;

  const field = resolveFieldAlias(view, clause.field);
  if (!field || !data.some((row) => hasOwn(row, field))) return null;

  const actual = findActualValue(data, field, clause.value);
  if (!actual.found) return null;
  return { field, value: actual.value };
}

function resolveFieldAlias(view, rawField) {
  const key = String(rawField || "").trim().toLowerCase();
  const alias = FIELD_ALIASES[key] || rawField;
  if (alias === "__x__") return view?.x_field || null;
  if (alias === "__series__") return view?.color || null;
  return alias || null;
}

function findActualValue(data, field, target) {
  for (const row of data) {
    if (!hasOwn(row, field)) continue;
    const value = row[field];
    if (valuesEqual(value, target)) return { found: true, value };
  }
  return { found: false, value: null };
}

function valuesEqual(left, right) {
  if (left === right) return true;
  if (left === null || left === undefined || right === null || right === undefined) return false;

  if (typeof left === "number" && Number.isFinite(left)) {
    const parsed = Number(right);
    if (Number.isFinite(parsed)) return left === parsed;
  }
  if (typeof left === "boolean") {
    return String(left).toLowerCase() === String(right).trim().toLowerCase();
  }

  return normalizeText(left) === normalizeText(right);
}

function normalizeText(value) {
  return stripQuotes(String(value ?? "").trim()).toLowerCase();
}

function stripQuotes(value) {
  return String(value || "").replace(/^["'“”‘’]+|["'“”‘’]+$/g, "").trim();
}

function datumMatchesClauses(datum, clauses) {
  return clauses.every(({ field, value }) => valuesEqual(datum?.[field], value));
}

function highlightExpression(clauses) {
  return clauses
    .map(({ field, value }) => `datum[${JSON.stringify(field)}] === ${literal(value)}`)
    .join(" && ");
}

function clauseExpression(clause) {
  return clause ? highlightExpression([clause]) : "";
}

function literal(value) {
  if (value instanceof Date) return JSON.stringify(value.toISOString());
  const encoded = JSON.stringify(value);
  return encoded === undefined ? "null" : encoded;
}

function applyMarkHighlight(spec, view, expression) {
  const encoding = { ...(spec.encoding || {}) };
  encoding.opacity = {
    condition: { test: expression, value: 1 },
    value: 0.16,
  };
  encoding.stroke = {
    condition: { test: expression, value: HIGHLIGHT_STROKE },
    value: TRANSPARENT,
  };
  encoding.strokeWidth = {
    condition: { test: expression, value: 3 },
    value: 0,
  };

  if (view.chart_type === "scatter") {
    encoding.size = {
      condition: { test: expression, value: 180 },
      value: 36,
    };
  }

  return { ...spec, encoding };
}

function applyLineHighlight(spec, view, highlight, expression) {
  const { mark, encoding, ...rest } = spec;
  const xClause = highlight.clauses.find(({ field }) => field === view.x_field);
  const seriesClause = view.color
    ? highlight.clauses.find(({ field }) => field === view.color)
    : null;
  const seriesExpression = clauseExpression(seriesClause);

  const baseEncoding = { ...(encoding || {}) };
  const baseMark = {
    ...(typeof mark === "object" ? mark : { type: mark || "line" }),
    point: Boolean(seriesClause && !xClause),
  };

  if (seriesExpression) {
    baseEncoding.opacity = {
      condition: { test: seriesExpression, value: 1 },
      value: 0.13,
    };
    baseEncoding.strokeWidth = {
      condition: { test: seriesExpression, value: 4 },
      value: 1.25,
    };
  } else {
    baseMark.opacity = 0.36;
  }

  const layers = [
    {
      mark: baseMark,
      encoding: baseEncoding,
    },
  ];

  if (xClause) {
    const xExpression = clauseExpression(xClause);
    layers.push({
      transform: [{ filter: xExpression }],
      mark: {
        type: "rule",
        color: HIGHLIGHT_STROKE,
        strokeWidth: 2,
        opacity: 0.8,
      },
      encoding: {
        x: encoding.x,
      },
    });
  }

  if (xClause || !seriesClause) {
    const pointEncoding = { ...(encoding || {}) };
    delete pointEncoding.detail;
    layers.push({
      transform: [{ filter: expression }],
      mark: {
        type: "point",
        filled: true,
        size: 170,
        stroke: "#ffffff",
        strokeWidth: 2,
        tooltip: true,
      },
      encoding: pointEncoding,
    });
  }

  return {
    ...rest,
    layer: layers,
  };
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function hasOwn(value, key) {
  return Boolean(value && Object.prototype.hasOwnProperty.call(value, key));
}

function formatValue(value) {
  if (value instanceof Date) return value.toISOString();
  return String(value);
}
