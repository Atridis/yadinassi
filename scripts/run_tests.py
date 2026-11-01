"""Standard unittest discovery/CLI with completed-test timings for CI.

No test selection, retries or result classification is implemented here. Timing
covers startTest through stopTest, including per-test fixtures and cleanups;
module/class fixtures and discovery remain outside individual timings.
"""
import heapq
from time import perf_counter
import unittest


class TimedTextTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slowest = []
        self._active = None
        self._statuses = []
        self._sequence = 0

    def _without_progress(self, method, *args):
        show_all, dots = self.showAll, self.dots
        if show_all:
            self.showAll = self.dots = False
        try:
            return method(*args)
        finally:
            self.showAll, self.dots = show_all, dots

    def startTest(self, test):
        self._active = test
        # Test fixtures may legitimately assign self.id (e.g. a tree column).
        # Use the standard class implementation before fixtures, never a user
        # instance override; FunctionTestCase has its own standard identity.
        if isinstance(test, unittest.FunctionTestCase):
            self._test_id = unittest.FunctionTestCase.id(test)
        elif isinstance(test, unittest.TestCase):
            self._test_id = unittest.TestCase.id(test)
        else:
            self._test_id = str(test)
        self._description = self.getDescription(test).replace('\n', ' ') if self.showAll else None
        self._statuses = []
        self._started = perf_counter()
        self._without_progress(super().startTest, test)

    def _outcome(self, label, method, test, *args):
        if self._active is None:
            # Class/module fixture failures have no startTest/stopTest pair.
            return method(test, *args)
        if label not in self._statuses:
            self._statuses.append(label)
        return self._without_progress(method, test, *args)

    def addSuccess(self, test):
        self._outcome('ok', super().addSuccess, test)

    def addError(self, test, err):
        self._outcome('ERROR', super().addError, test, err)

    def addFailure(self, test, err):
        self._outcome('FAIL', super().addFailure, test, err)

    def addSkip(self, test, reason):
        self._outcome('skipped {!r}'.format(reason), super().addSkip, test, reason)

    def addExpectedFailure(self, test, err):
        self._outcome('expected failure', super().addExpectedFailure, test, err)

    def addUnexpectedSuccess(self, test):
        self._outcome('unexpected success', super().addUnexpectedSuccess, test)

    def addSubTest(self, test, subtest, err):
        if err is None:
            return self._without_progress(super().addSubTest, test, subtest, err)
        label = 'FAIL' if issubclass(err[0], test.failureException) else 'ERROR'
        self._outcome(label + ' (subtest)', super().addSubTest, test, subtest, err)

    def stopTest(self, test):
        elapsed = perf_counter() - self._started
        try:
            super().stopTest(test)
            self._sequence += 1
            entry = (elapsed, self._sequence, self._test_id)
            if len(self.slowest) < 20:
                heapq.heappush(self.slowest, entry)
            else:
                heapq.heappushpop(self.slowest, entry)
            if self.showAll:
                description = self._description
                status = '; '.join(self._statuses) or 'interrupted'
                self.stream.writeln(f'{description} ... {status} ... {elapsed:.3f} s')
                self.stream.flush()
        finally:
            self._active = None
            self._statuses = []


class TimedTextTestRunner(unittest.TextTestRunner):
    resultclass = TimedTextTestResult

    def run(self, test):
        result = super().run(test)
        if self.verbosity and result.slowest:
            self.stream.writeln('\nSlowest tests (up to 20; includes per-test setup/teardown/cleanup):')
            for elapsed, _, test_id in sorted(result.slowest, reverse=True):
                self.stream.writeln(f'  {elapsed:.3f} s  {test_id}')
            self.stream.flush()
        return result


if __name__ == '__main__':
    unittest.main(module=None, testRunner=TimedTextTestRunner)
