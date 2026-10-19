const ERROR_CODES = new Set(['embed_failed', 'run_async_failed', 'render_failed']);

export function createChartRenderLifecycle(emit, now = () => performance.now()) {
  let generation = 0;
  let disposed = false;

  function start(metadata, startedAt = now()) {
    disposed = false;
    generation += 1;
    return Object.freeze({ ...metadata, generation, startedAt });
  }

  function current(ticket) {
    return !disposed && ticket?.generation === generation;
  }

  async function complete(ticket, view) {
    try {
      await view?.runAsync?.();
    } catch (_error) {
      fail(ticket, 'run_async_failed');
      return false;
    }
    if (!current(ticket)) return false;
    emit('rendered', payload(ticket, Math.max(0, now() - ticket.startedAt)));
    return true;
  }

  function fail(ticket, errorCode = 'render_failed') {
    if (!current(ticket)) return false;
    const safeCode = ERROR_CODES.has(errorCode) ? errorCode : 'render_failed';
    emit('render-failed', { ...payload(ticket, Math.max(0, now() - ticket.startedAt)), error_code: safeCode });
    return true;
  }

  function invalidate() {
    generation += 1;
  }

  function dispose() {
    disposed = true;
    invalidate();
  }

  return { start, current, complete, fail, invalidate, dispose };
}

function payload(ticket, duration) {
  return {
    render_token: ticket.renderToken,
    dashboard_revision: ticket.dashboardRevision,
    view_id: ticket.viewId,
    view_revision: ticket.viewRevision,
    render_generation: ticket.generation,
    browser_duration_ms: duration,
    presentation: ticket.presentation,
  };
}
