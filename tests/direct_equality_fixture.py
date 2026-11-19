"""Instrument the actual direct compiler equality binding, not retired visitors."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from yadinassi.execution.codegen import experimental_naked_scalar_semantics as scalar

@contextmanager
def direct_equality():
    original = scalar.map_identity_operators
    service = SimpleNamespace(equal=original(array=True, structure=True)[0])
    def operators(**kwargs):
        return (lambda left, right: service.equal(left, right),
                lambda left, right: not service.equal(left, right))
    with patch.object(scalar, 'map_identity_operators', operators):
        yield service
