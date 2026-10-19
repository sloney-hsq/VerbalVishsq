export function createDashboardRenderTracker(send) {
  let active = null;
  let expected = new Map();
  let emptySent = false;

  function activate(envelope) {
    active = validEnvelope(envelope) ? structuredClone(envelope) : null;
    expected = new Map((active?.expected_views || []).map(item => [item.view_id, item.view_revision]));
    emptySent = false;
    if (active && expected.size === 0) {
      emptySent = true;
      send('view.rendered', {
        render_token: active.token,
        dashboard_revision: active.dashboard_revision,
        view_id: null,
        view_revision: null,
        render_generation: 0,
        browser_duration_ms: 0,
        presentation: { mode: 'empty', page_index: null },
      });
    }
    return active;
  }

  function forward(kind, payload) {
    if (!active || !payload || !['rendered', 'render-failed'].includes(kind)) return false;
    if (payload.render_token !== active.token || payload.dashboard_revision !== active.dashboard_revision) return false;
    if (expected.get(payload.view_id) !== payload.view_revision) return false;
    send(kind === 'rendered' ? 'view.rendered' : 'view.render_failed', structuredClone(payload));
    return true;
  }

  function current() {
    return active ? structuredClone(active) : null;
  }

  return { activate, forward, current, get emptySent() { return emptySent; } };
}

function validEnvelope(value) {
  return Boolean(
    value && typeof value.token === 'string' && value.token
    && Number.isSafeInteger(value.dashboard_revision) && value.dashboard_revision >= 0
    && Array.isArray(value.expected_views)
    && value.expected_views.every(item => item && typeof item.view_id === 'string'
      && Number.isSafeInteger(item.view_revision) && item.view_revision >= 0),
  );
}
