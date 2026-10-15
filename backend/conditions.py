"""Study condition names at the external ingress and inside the runtime."""

TURN_TAKING = 'turn_taking'
REVISION_ENABLED = 'revision_enabled'
CANONICAL_CONDITIONS = frozenset({TURN_TAKING, REVISION_ENABLED})

_INGRESS_ALIASES = {
    'half_duplex': TURN_TAKING,
    'full_duplex_rrt': REVISION_ENABLED,
}


def normalize_ingress_condition(value):
    """Return a canonical condition for a WebSocket query value, or None."""
    if value in CANONICAL_CONDITIONS:
        return value
    return _INGRESS_ALIASES.get(value)


def require_canonical_condition(value):
    if value not in CANONICAL_CONDITIONS:
        raise ValueError('unknown study condition')
    return value
