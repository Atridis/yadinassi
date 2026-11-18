"""Untimed current-thread counters, independent of the recovering BSL runtime."""
import sys


def capture(run):
    """Return (result, counters); caller owns setup, warmup and validation.

    Python and C entries are separate. C exceptions/returns are NOT new calls.
    Counts include the supplied Python callable itself. Other threads are not
    observed. A pre-existing profiler is never replaced.
    """
    if sys.getprofile() is not None:
        raise RuntimeError('call counters require an unprofiled current thread')
    counts = {'python_calls': 0, 'c_calls': 0}
    def profile(frame, event, arg):
        if event == 'call':
            counts['python_calls'] += 1
        elif event == 'c_call':
            # Installation/cleanup belongs to instrumentation, not the workload.
            if arg is not sys.setprofile:
                counts['c_calls'] += 1
    sys.setprofile(profile)
    try:
        result = run()
    finally:
        sys.setprofile(None)
    return result, counts
