"""Database capabilities do not disable independent pure module facts."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
from yadinassi.execution.direct.python_direct_database import NAMES
import test_python_direct_database as dbfixture

KERNEL='a=New Array;For i=0 To 99 Do a.Add(i);EndDo;s=0;For j=0 To 99 Do s=s+a.Get(j);EndDo;'
class IndependentFactsTests(unittest.TestCase):
    def plan(self,source,**kwargs):
        return compile_owned(parse(source),source_text=source,source_name='facts.bsl',external_names=('External',),constructors=('Query',),**kwargs)
    def test_db_namespace_generates_same_pure_code(self):
        plain=compile_owned(parse(KERNEL),source_text=KERNEL,source_name='facts.bsl')
        db=compile_owned(parse(KERNEL),source_text=KERNEL,source_name='facts.bsl',external_names=tuple(NAMES),constructors=('query','запрос'))
        self.assertEqual(plain.generated_source,db.generated_source)
        numeric=self.plan('s=0;For i=1 To 100 Do s=s+i;EndDo;')
        self.assertEqual(numeric.run({},context=BoundaryContext())['s'],5050)
    def test_external_get_and_set_clear_array_facts(self):
        for effect in ('x=External;','External=1;'):
            with self.subTest(effect=effect):
                state={};calls=[]
                class Context(BoundaryContext):
                    def external_get(self,name):state['a']=object();return Decimal(1)
                    def external_set(self,name,value):state['a']=object()
                    def resolve_member(self,value,name):calls.append(name);raise BoundaryViolation('explicit host boundary')
                p=self.plan('a=New Array;'+effect+'a.Add(2);')
                self.assertIn('id(type(',p.generated_source)
                with self.assertRaisesRegex(BoundaryViolation,'explicit host boundary'):p.run(state,context=Context())
                self.assertEqual(calls,['Add'])
    def test_external_read_deletion_invalidates_scalar_right_operand(self):
        state={}
        class Context(BoundaryContext):
            def external_get(self,name):state.pop('x');return Decimal(2)
        p=self.plan('x=1;y=External+x;')
        with self.assertRaisesRegex(Exception,'не определена'):p.run(state,context=Context())
        self.assertNotIn('y',state)
    def test_external_loop_counter_cannot_prove_body(self):
        state={};calls=[]
        class Context(BoundaryContext):
            def external_set(self,name,value):self.counter=value;state['a']=object()
            def external_get(self,name):return self.counter
            def resolve_member(self,value,name):calls.append(name);raise BoundaryViolation('external counter effect')
        p=self.plan('a=New Array;For External=0 To 1 Do a.Add(External);EndDo;')
        self.assertIn('id(type(',p.generated_source)
        with self.assertRaisesRegex(BoundaryViolation,'external counter effect'):p.run(state,context=Context())
        self.assertEqual(calls,['Add'])
    def test_custom_array_and_authority_keep_dispatch(self):
        source='a=New Array;a.Add(1);'
        p=compile_owned(parse(source),source_text=source,source_name='facts.bsl',constructors=('Array',),external_names=tuple(NAMES))
        self.assertIn('id(type(',p.generated_source)
        p=compile_owned(parse(KERNEL),source_text=KERNEL,source_name='facts.bsl',external_names=tuple(NAMES),authority_checks=True)
        self.assertIn('id(type(',p.generated_source)
    def test_query_constructor_callback_clears_existing_facts(self):
        state={};calls=[]
        class Context(BoundaryContext):
            def resolve_member(self,value,name):calls.append(name);raise BoundaryViolation('query callback effect')
        def query():state['a']=object();return None
        p=self.plan('a=New Array;q=New Query;a.Add(1);')
        with self.assertRaisesRegex(BoundaryViolation,'query callback effect'):p.run(state,context=Context(services={'new:query':query}))
        self.assertEqual(calls,['Add'])
    def test_actual_db_query_with_array_preprocessing_and_host_mutation(self):
        f=dbfixture.DirectDatabaseTests();f.setUp();self.addCleanup(f.doCleanups)
        f.vm.execute('Before=Catalogs;'+KERNEL+'Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады");S1=Q.Execute().Select();S1.Next();Rows=S1.N;')
        self.assertEqual(f.vm.variables['s'],4950);self.assertEqual(f.vm.variables['rows'],0)
        extension_vm=f.interpreter(allow_extensions=True)
        def reset():extension_vm.variables.pop('x',None)
        extension_vm.register_function('Reset',reset)
        with self.assertRaisesRegex(Exception,'не определена'):extension_vm.execute('x=1;Reset();y=x;')
        self.assertNotIn('y',extension_vm.variables)

    def test_impure_get_argument_cannot_infer_old_scalar_contents(self):
        state={};calls=[]
        class Payload:
            def __add__(self,other):state['b']=object();return Decimal(3)
        class Context(BoundaryContext):
            def external_get(self,name):state['a'][0]=Payload();return Decimal(0)
            def resolve_member(self,value,name):calls.append(name);raise BoundaryViolation('changed array receiver')
        p=self.plan('a=New Array;a.Add(1);x=a.Get(External);b=New Array;y=x+1;b.Add(2);')
        with self.assertRaisesRegex(BoundaryViolation,'changed array receiver'):p.run(state,context=Context())
        self.assertEqual(calls,['Add'])
