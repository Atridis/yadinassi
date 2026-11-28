"""Entry point for the separately reviewable BSL call exceptions."""
from . import (
    direct_call_exceptions,
    direct_named_routine_call,
    direct_notification_call,
    direct_optional_builtin_calls,
)


def lower(emit, key, arguments, want_value):
    # A published user routine wins over the builtin with the same name.
    lowered = direct_named_routine_call.lower(emit, key, arguments, want_value)
    if lowered is not None:
        return lowered
    for rule in (direct_call_exceptions, direct_notification_call, direct_optional_builtin_calls):
        lowered = rule.lower(emit, key, arguments)
        if lowered is not None:
            return lowered
    return None


HELPERS = {
    **direct_call_exceptions.HELPERS,
    **direct_named_routine_call.HELPERS,
    **direct_notification_call.HELPERS,
    **direct_optional_builtin_calls.HELPERS,
}
