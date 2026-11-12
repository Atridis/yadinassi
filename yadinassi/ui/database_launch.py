"""Launch only the UI authority already admitted in an existing database.

The materialized XML/BSL is a private copy, not a new import, migration or grant.
The writable child rechecks database identity and the complete source before it
constructs an application; a replacement database is not silently adopted.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

from ..sqlite_catalog import SQLiteCatalogBackend

BINDING_PROTOCOL = 'yadinassi-database-ui-launch/1'
# Closed route names are emitted only by the canonical backend admission.
ROUTES = {
    'catalog': None,
    'catalog-forms': '--catalog-objects',
    'application': '--application-host',
    'documents': '--document-objects',
    'business': '--business-application',
    'references': '--reference-application',
    'posting': '--posting-application',
    'inventory': '--inventory-application',
}


def configuration_route(*, catalog_objects=False, application_host=False,
                        document_objects=False, business_application=False,
                        reference_application=False, posting_application=False, inventory_application=False):
    selected = [name for name, enabled in (
        ('catalog-forms', catalog_objects), ('application', application_host),
        ('documents', document_objects), ('business', business_application),
        ('references', reference_application), ('posting', posting_application), ('inventory', inventory_application)) if enabled]
    if len(selected) != 1:
        raise ValueError('database UI requires one exact configuration grant')
    return selected[0]


def binding(snapshot):
    return json.dumps({'protocol': BINDING_PROTOCOL,
        'database': str(snapshot.database_id), 'generation': snapshot.configuration_generation,
        'profile': snapshot.profile, 'route': snapshot.route,
        'source': snapshot.source_digest}, sort_keys=True, separators=(',', ':'))


def verify_binding(backend, expected, files=None, *, route=None):
    if type(expected) is not str or not 1 <= len(expected) <= 1024:
        raise ValueError('invalid database UI binding')
    snapshot = backend.launch_snapshot()
    # Require canonical serialized bytes, not permissive JSON coercions or fields.
    if binding(snapshot) != expected or (route is not None and snapshot.route != route):
        raise ValueError('database UI source changed')
    if files is not None and {f.path: f.content for f in snapshot.files} != files:
        raise ValueError('materialized UI source changed')
    return snapshot


@contextmanager
def materialize(snapshot):
    # All source is already canonical. Still fail closed at the filesystem seam.
    with tempfile.TemporaryDirectory(prefix='yadinassi-ui-') as directory:
        root = Path(directory) / 'source'; root.mkdir(mode=0o700)
        for entry in snapshot.files:
            name = entry.path
            logical = PurePosixPath(name)
            if (type(name) is not str or logical.is_absolute() or str(logical) != name
                    or any(p in ('', '.', '..') for p in logical.parts)
                    or '\\' in name or ':' in name or '\x00' in name):
                raise ValueError('invalid UI source path')
            target = root.joinpath(*logical.parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(entry.content)
        yield root


def main(argv=None):
    parser = argparse.ArgumentParser(prog='yadinassi --ui', allow_abbrev=False,
        description='Open the supported UI already granted by an existing Yadinassi database.')
    parser.add_argument('--f', required=True, metavar='SQLITE_FILE')
    parser.add_argument('--form', help='Declared initial form, for configuration applications only')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args(argv)
    try:
        backend = SQLiteCatalogBackend(args.f, read_only=True)
        try:
            snapshot = backend.launch_snapshot()
        finally:
            backend.close()
        if snapshot.route not in ROUTES:
            raise ValueError('unsupported database UI profile')
        expected = binding(snapshot)
        options = ['--f', args.f, '--browser-session', '--launch-binding', expected]
        if args.open_browser:
            options.append('--open-browser')
        if snapshot.route == 'catalog':
            if args.form:
                parser.error('--form requires an admitted configuration-form application')
            from . import local_app
            return local_app.main(options)
        if args.form:
            options.extend(['--form', args.form])
        from . import configuration_app
        with materialize(snapshot) as root:
            return configuration_app.main([str(root), ROUTES[snapshot.route], *options])
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Database UI unavailable: the database must be active, intact and have a supported UI profile. '
              'No activation, migration or fallback was performed.', file=sys.stderr)
        return 1
