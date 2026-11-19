import unittest
from unittest.mock import patch
from types import SimpleNamespace
from decimal import Decimal
from yadinassi.execution.direct.source import python_direct_source_resources as resources
from yadinassi.streams.text_documents import BSLTextDocument
from yadinassi.streams.file_io import BSLBinaryData
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class SourceResourceSecurity(unittest.TestCase):
    def boundary(self):
        factory=HostFunction('TextDocument',BSLTextDocument)
        return SimpleNamespace(_check=lambda:None,vm=SimpleNamespace(types={name:factory for name in resources.CONSTRUCTOR_NAMES}))

    def test_methods_saved_method_and_binary_size(self):
        boundary=self.boundary();doc=resources.resolve_constructor(boundary,'new:textdocument')()
        resources.resolve(boundary,doc,'УстановитьТекст',argument_count=1)('one\ntwo')
        self.assertEqual(resources.resolve(boundary,doc,'LineCount',argument_count=0)(),Decimal(2))
        saved=resources.get(boundary,doc,'GetText')
        self.assertEqual(resources.captured(boundary,saved)(),'one\ntwo')
        data=BSLBinaryData.from_bytes(b'abc')
        self.assertEqual(resources.resolve(boundary,data,'Размер')(),Decimal(3))
        with self.assertRaises(ValueError):resources.resolve(boundary,data,'Write')

    def test_method_arity_and_procedure_contract(self):
        boundary=self.boundary();doc=BSLTextDocument()
        with self.assertRaises(TypeError):resources.resolve(boundary,doc,'SetText',require_value=True)
        with self.assertRaises(TypeError):resources.resolve(boundary,doc,'GetText',argument_count=1)
        self.assertEqual(doc.get_text(),'')

    def test_instance_class_saved_callback_and_fields_tampering(self):
        boundary=self.boundary();doc=BSLTextDocument();calls=[]
        bound=resources.resolve(boundary,doc,'GetText')
        with patch.object(BSLTextDocument,'get_text',lambda self:calls.append('class')):
            with self.assertRaises(BoundaryViolation):bound()
        doc.get_text=lambda:calls.append('instance')
        with self.assertRaises(BoundaryViolation):resources.get(boundary,doc,'GetText')
        del doc.get_text
        saved=resources.get(boundary,doc,'GetText');bound=resources.captured(boundary,saved)
        saved.function=lambda:calls.append('saved')
        with self.assertRaises(BoundaryViolation):bound()
        doc._spans=[('bad',0,0)]
        with self.assertRaises(BoundaryViolation):resources.resolve(boundary,doc,'GetText')
        self.assertEqual(calls,[])

    def test_factory_init_module_and_alias_replacement(self):
        from yadinassi.streams import text_documents
        boundary=self.boundary();create=resources.resolve_constructor(boundary,'textdocument');calls=[]
        with patch.object(BSLTextDocument,'__init__',lambda self:calls.append('init')):
            with self.assertRaises(BoundaryViolation):create()
        with patch.object(text_documents,'BSLTextDocument',lambda:calls.append('class')):
            with self.assertRaises(BoundaryViolation):resources.check_factories()
        boundary.vm.types['текстовыйдокумент']=HostFunction('other',lambda:calls.append('alias'))
        with self.assertRaises(BoundaryViolation):create()
        self.assertEqual(calls,[])

    def test_binary_factory_guard(self):
        calls=[]
        with patch.object(BSLBinaryData,'from_bytes',classmethod(lambda cls,value:calls.append(value))):
            with self.assertRaises(BoundaryViolation):resources.check_factories()
        self.assertEqual(calls,[])

    def test_factory_attribute_dispatch_rejected_before_callback(self):
        boundary=self.boundary();create=resources.resolve_constructor(boundary,'textdocument')
        calls=[]
        for cls in (BSLTextDocument,BSLBinaryData):
            for name in ('__getattribute__','__setattr__'):
                with self.subTest(cls=cls,name=name),patch.object(cls,name,lambda *args:calls.append(args)):
                    with self.assertRaises(BoundaryViolation):create()
        self.assertEqual(calls,[])

    def test_factory_field_descriptors_rejected_before_callback(self):
        boundary=self.boundary();create=resources.resolve_constructor(boundary,'textdocument')
        calls=[]
        descriptor=property(lambda obj:calls.append('get'),lambda obj,value:calls.append('set'))
        for cls,name in ((BSLTextDocument,'_text'),(BSLTextDocument,'_spans'),
                         (BSLTextDocument,'_units'),(BSLBinaryData,'_data')):
            with self.subTest(cls=cls,name=name),patch.object(cls,name,descriptor,create=True):
                with self.assertRaises(BoundaryViolation):create()
        self.assertEqual(calls,[])
