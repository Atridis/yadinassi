"""Closed fixture snapshots, never shared SQLite connections or runtimes."""
from contextlib import closing
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory

from yadinassi import Interpreter
from yadinassi.configuration.configuration_inventory_application import (
    PROFILE as INVENTORY, import_inventory_application)
from yadinassi.configuration.configuration_inventory_enum_application import (
    PROFILE as INVENTORY_ENUM, import_inventory_application as import_inventory_enum)
from yadinassi.configuration.configuration_main_demo import (
    PROFILE as MAIN_DEMO, import_main_demo_configuration)
from yadinassi.db.database_context import SQLiteDBContext

import inventory_application_fixture
import inventory_enum_application_fixture
import test_main_demo_configuration


def _inventory_products(context):
    with closing(Interpreter(database_context=context, output=lambda value: None)) as vm:
        vm.execute(
            'P=Catalogs.Products.CreateItem();P.Code="P1";P.Description="Product";P.Write();'
            'W=Catalogs.Warehouses.CreateItem();W.Code="W1";W.Description="Warehouse";W.Write();'
        )
        refs = (vm.execute('P.Ref'), vm.execute('W.Ref'))
        return tuple((ref.value_type.metadata_uuid, ref.reference_uuid) for ref in refs)


@cache
def _snapshot(profile, seed):
    if profile == MAIN_DEMO:
        config = import_main_demo_configuration(test_main_demo_configuration.source(), profile=profile)
        create = SQLiteDBContext.create_main_demo
    elif profile == INVENTORY:
        config = import_inventory_application(inventory_application_fixture.source(), inventory_runtime=profile)
        create = SQLiteDBContext.create_inventory_application
    elif profile == INVENTORY_ENUM:
        config = import_inventory_enum(inventory_enum_application_fixture.source(), inventory_runtime=profile)
        create = SQLiteDBContext.create_inventory_enum_application
    else:
        raise ValueError(f'Unknown test database profile: {profile!r}')

    with TemporaryDirectory() as directory:
        path = Path(directory) / 'seed.sqlite'
        with create(path, config) as context:
            records = seed(context) if seed is not None else None
        if set(path.parent.iterdir()) != {path}:
            raise RuntimeError('Test database snapshot still has SQLite sidecars')
        return path.read_bytes(), records


def _copy(path, profile, seed=None):
    snapshot, records = _snapshot(profile, seed)
    # A copy starts with the same persistent database ID. Create real independent
    # databases for tests that compare IDs or cross database ownership boundaries.
    with Path(path).open('xb') as file:
        file.write(snapshot)
    return records


def copy_main_demo(path, *, seed=None):
    _copy(path, MAIN_DEMO, seed)


def copy_inventory(path, *, products=False):
    return _copy(path, INVENTORY, _inventory_products if products else None)


def copy_inventory_enum(path):
    _copy(path, INVENTORY_ENUM)
