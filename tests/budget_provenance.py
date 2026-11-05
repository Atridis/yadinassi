"""Per-test immutable snapshots, never a production provenance cache."""
import json


def freeze_provenance(value):
    """Own immutable bytes; neither reports nor tampering tests can mutate them."""
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def copy_provenance(template):
    """Every report owns a fresh recursive dictionary/list graph."""
    return json.loads(template)


def one_provenance_build(full):
    """Count real hashing calls during one enumeration, without replacing it."""
    from functools import wraps
    from unittest import mock

    def decorate(method):
        @wraps(method)
        def measured(self):
            with mock.patch.object(full, 'interpreter_provenance',
                                   wraps=full.interpreter_provenance) as build:
                method(self)
            self.assertEqual(build.call_count, 1, 'one real provenance build per enumeration')
        return measured
    return decorate
