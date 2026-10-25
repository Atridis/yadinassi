"""Explicit offline preflight plumbing only, never a runtime/native parity proof.

Fake runners test source/output admission on every OS without touching the fixed
Linux pathname. Real whole137 tests use the unmodified production owner instead.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


class OfflineFixtureError(Exception):
    pass


class OfflineOwner:
    directory = Path('/tmp/onec-smoke/db')

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def verify(self):
        pass


@contextmanager
def offline_fixture(full):
    module = SimpleNamespace(OwnedInfobase=OfflineOwner, FixtureError=OfflineFixtureError)
    with mock.patch.object(full, '_load_infobase_fixture', return_value=module):
        yield
