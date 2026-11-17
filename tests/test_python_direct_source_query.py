"""Finite source-query protocols preserve caller grants without legacy dispatch."""
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_source_constant_store import configuration
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication, _SourceInterpreter
from yadinassi.python_direct_source import SourceBoundary, _compile
from yadinassi import source_transactions
from yadinassi import python_direct_source_query as bridge
from yadinassi.source_constant_queries import SourceConstantQuery
from yadinassi.source_constants_runtime import SourceConstants
from yadinassi.runtime import Interpreter
from yadinassi.experimental_naked_boundaries import BoundaryViolation


class DirectSourceQueryTests(unittest.TestCase):
    def app(self,*,scratch=False):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        app=SourceApplication(configuration() if scratch else source(),output=lambda value:None,
            scratch_database=Path(temporary.name)/'source.sqlite' if scratch else None)
        self.addCleanup(app.close);app.start()
        owner=_SourceInterpreter(app,family_owner=app.interpreter);self.addCleanup(owner.close)
        owner._logical_side='server';owner._context_stack.append('server')
        self.addCleanup(owner._context_stack.pop)
        return app,owner

    @contextmanager
    def boundary(self,app,owner):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('VM program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM routine')), \
             source_transactions.execution(app),app.safe_mode.execution():
            context=SourceBoundary(owner,_compile(owner,[]));context.enter()
            try:yield context
            finally:context.leave()

    def new(self,boundary,name,*args):
        return bridge.resolve_constructor(boundary,name,argument_count=len(args))(*args)

    def call(self,boundary,value,name,*args):
        return bridge.resolve_member(boundary,value,name,argument_count=len(args))(*args)

    def test_constants_query_selection_unload_and_detached_table_protocol(self):
        app,owner=self.app(scratch=True);app.constant_store.set('Text','stored')
        with self.boundary(app,owner) as b:
            query=self.new(b,'Query','SELECT Text AS N FROM Constants')
            result=self.call(b,query,'Execute');selection=self.call(b,result,'Select')
            self.assertTrue(self.call(b,selection,'Next'));self.assertEqual(bridge.get_member(b,selection,'N'),'stored')
            table=self.call(b,result,'Unload');columns=bridge.get_member(b,table,'Columns')
            self.assertEqual(self.call(b,columns,'Count'),1)
            row=bridge.resolve_member(b,table,'__getitem__')(Decimal(0))
            self.assertEqual(bridge.get_member(b,row,'N'),'stored')
            bridge.resolve_set_member(b,row,'N')('edited')
            self.assertEqual(bridge.get_member(b,row,'N'),'edited')
            self.assertEqual(list(bridge.iterate(b,table)),[row])
        self.assertEqual(app.constant_store.get('Text'),'stored')

    def test_in_memory_query_does_not_require_scratch_storage(self):
        app,owner=self.app()
        with self.boundary(app,owner) as b:
            query=self.new(b,'Query','SELECT N FROM &Input')
            table=self.new(b,'ValueTable');columns=bridge.get_member(b,table,'Columns')
            self.call(b,columns,'Add','N',self.new(b,'TypeDescription','Boolean'))
            row=self.call(b,table,'Add');bridge.resolve_set_member(b,row,'N')(True)
            self.call(b,query,'SetParameter','Input',table)
            result=self.call(b,query,'Execute');selection=self.call(b,result,'Select')
            self.assertTrue(self.call(b,selection,'Next'));self.assertIs(bridge.get_member(b,selection,'N'),True)

    def test_foreign_query_and_delayed_owner_change_refused(self):
        app,owner=self.app();other,other_owner=self.app()
        foreign=SourceConstantQuery(other_owner,other,'SELECT 9 AS N')
        with self.boundary(app,owner) as b:
            with self.assertRaises(BoundaryViolation):bridge.resolve_member(b,foreign,'Execute')
            query=self.new(b,'Query','SELECT 7 AS N');bound=bridge.resolve_member(b,query,'Execute')
            query._source_owner=SourceConstants(other)
            with self.assertRaises(BoundaryViolation):bound()

    def test_bound_call_does_not_outlive_boundary(self):
        app,owner=self.app()
        with self.boundary(app,owner) as b:
            query=self.new(b,'Query','SELECT 7 AS N');bound=bridge.resolve_member(b,query,'Execute')
        with self.assertRaises(BoundaryViolation):bound()

    def test_query_constructor_registration_checked_before_and_after_binding(self):
        app,owner=self.app()
        with self.boundary(app,owner) as b:
            factory=owner.types['query'];bound=bridge.resolve_constructor(b,'Query')
            factory.function=lambda *args:None
            with self.assertRaises(BoundaryViolation):bound()
            with self.assertRaises(BoundaryViolation):bridge.resolve_constructor(b,'Query')

    def test_temp_manager_foreign_ownership_and_close_contract(self):
        app,owner=self.app();other,other_owner=self.app()
        with self.boundary(other,other_owner) as b:foreign=self.new(b,'TempTablesManager')
        with self.boundary(app,owner) as b:
            query=self.new(b,'Query','SELECT 7 AS N');manager=self.new(b,'TempTablesManager')
            bridge.resolve_set_member(b,query,'TempTablesManager')(manager)
            with self.assertRaises(BoundaryViolation):bridge.resolve_set_member(b,query,'TempTablesManager')(foreign)
            with self.assertRaises(TypeError):bridge.resolve_member(b,manager,'Close',require_value=True)
            self.call(b,manager,'Close');self.assertTrue(manager._closed)

    def test_type_description_and_new_table_are_only_data_protocols(self):
        app,owner=self.app()
        with self.boundary(app,owner) as b:
            description=self.new(b,'TypeDescription','String')
            types=self.call(b,description,'Types');self.assertEqual(len(list(bridge.iterate(b,types))),1)
            table=self.new(b,'ValueTable');columns=bridge.get_member(b,table,'Columns')
            self.call(b,columns,'Add','Name',description)
            row=self.call(b,table,'Add');bridge.resolve_set_member(b,row,'Name')('value')
            self.assertEqual(bridge.get_member(b,row,'Name'),'value')
            with self.assertRaises(BoundaryViolation):bridge.get_member(b,table,'__dict__')

    def test_base_query_and_subclasses_are_not_admitted(self):
        from yadinassi.queries import BSLQuery
        app,owner=self.app()
        class ForeignQuery(SourceConstantQuery):pass
        with self.boundary(app,owner) as b:
            self.assertFalse(bridge.supports(BSLQuery(owner._catalogs)))
            self.assertFalse(bridge.supports(ForeignQuery(owner,app)))
            with self.assertRaises(BoundaryViolation):bridge.resolve_member(b,BSLQuery(owner._catalogs),'Execute')


if __name__=='__main__':unittest.main()
