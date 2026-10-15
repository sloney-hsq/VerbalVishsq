/** Group a flat realtime timeline into user-led conversation turns. */
export function groupTranscriptItems(items = []) {
  const groups = [];
  const responseGroups = new Map();
  const requestGroups = new Map();
  let current = null;

  for (const item of Array.isArray(items) ? items : []) {
    if (item?.role === "user") {
      current = makeGroup(`turn-${item.id || groups.length + 1}`, item.startedAt);
      groups.push(current);
      if (item.requestId) requestGroups.set(item.requestId, current);
    } else if (!current) {
      current = makeGroup("turn-session-start", item?.startedAt);
      groups.push(current);
    }

    if (item?.role === "tool") {
      const target = requestGroups.get(item.requestId) || responseGroups.get(item.responseId) || current;
      target.actions.push(item);
      continue;
    }

    const target = requestGroups.get(item.requestId) || current;
    target.messages.push(item);
    if (item.requestId) requestGroups.set(item.requestId, target);
    if (item?.role === "assistant" && item.responseId) {
      responseGroups.set(item.responseId, target);
    }
  }

  groups.forEach((group) => {
    group.actionAnchorId = actionAnchorId(group.messages);
  });
  return groups;
}

function actionAnchorId(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "assistant") return messages[index].id || null;
  }
  return null;
}

function makeGroup(id, startedAt) {
  return {
    id,
    startedAt: startedAt ?? Date.now(),
    messages: [],
    actions: [],
    actionAnchorId: null,
  };
}
