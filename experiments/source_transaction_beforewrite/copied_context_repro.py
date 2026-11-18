"""Regression repro: copied pre-entry context must not acquire handler authority.

Run from this research checkout with PYTHONPATH=tests. The original prototype accepted this entry; the root witness must reject it.
"""
from contextvars import copy_context
from yadinassi.experimental_naked_boundaries import BoundaryViolation
import test_python_direct_catalog_preparation as fixtures

fixture=fixtures.DirectCatalogPreparationTests();fixture.setUp()
try:
    fixture.vm.register_function('Foreign',lambda:copy_context().run(fixture.card.write))
    try:fixture.vm.execute('BeginTransaction();Foreign();CommitTransaction();')
    except BoundaryViolation:pass
    else:raise AssertionError('copied context acquired handler authority')
    assert fixture.card.is_new() and fixture.db.backend._active is None
    print({'copied_context_handler_rejected':True,'original_journal_clean':True})
finally:
    fixture.doCleanups()
