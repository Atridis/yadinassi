"""Nested source XDTO objects and lists retain native ownership without VM."""
from decimal import Decimal
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_python_direct_source_xdto_objects as flat
import test_source_xdto_packages as existing
from yadinassi.formats.xml import xdto_io, xdto_values
from yadinassi.types.values import HostFunction

BODY=flat.BODY.replace(b'</package>', b'''<objectType name="Tree"><property name="Label" type="xs:string" lowerBound="0"/><property name="Child" type="t:Flat" lowerBound="0" nillable="true"/><property name="Children" type="t:Flat" lowerBound="0" upperBound="-1"/><property name="Labels" type="xs:string" lowerBound="0" upperBound="-1"/></objectType><objectType name="Outer"><property name="Tree" type="t:Tree" lowerBound="0"/></objectType></package>''')

class GraphXDTOTests(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    def app(self):
        mapping=existing.SourceXDTOTests().mapping(False);mapping[existing.R]=BODY
        return basic.SourceScalarXDTOTests.app(self,mapping)
    def prepared(self):
        app=self.app();app.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Tree");F=XDTOFactory.Type("urn:owned:records","Flat");P=XDTOFactory.Create(T);C=XDTOFactory.Create(F);D=XDTOFactory.Create(F);')
        return app
    def test_named_object_reads_preserve_live_lists_and_single_value_identity(self):
        app=self.prepared();vm=app.interpreter;factory=app.xdto.factory
        before=factory._nodes
        self.assertFalse(vm.execute('P.IsSet("Children");'))
        self.assertIsNone(vm.execute('P.GetXDTO("Child");'))
        self.assertEqual(factory._nodes,before)
        vm.execute('L=P.GetList("Children");')
        self.assertEqual(factory._nodes,before+1)
        self.assertIs(vm.execute('P.ПолучитьСписок("Children");'),vm.variables['l'])
        self.assertIs(vm.execute('P.Children;'),vm.variables['l'])
        self.assertFalse(vm.execute('P.Установлено("Children");'))
        vm.execute('L.Add(C);P.Child=Undefined;')
        self.assertTrue(vm.execute('P.IsSet("Child");'))
        self.assertTrue(vm.execute('P.IsSet("Children");'))
        self.assertIs(vm.execute('C.Владелец();'),vm.variables['p'])
        self.assertEqual(vm.execute('C.ВладеющееСвойство().Имя;'),'Children')
        self.assertEqual(vm.execute('C.OwningProperty().URIПространстваИмен;'),
                         vm.variables['c']._owning._uri)
        self.assertIs(vm.execute('C.Тип();'),vm.variables['f'])
        vm.execute('P.Child=D;')
        self.assertIs(vm.execute('P.ПолучитьXDTO("Child");'),vm.variables['d'])
        for code in ('P.GetList("Child");','P.GetXDTO("Children");','P.IsSet("child");',
                     'P.IsSet("Child/Label");'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)

    def test_named_validation_is_a_procedure_and_checks_required_descendants(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('P.Child=C;')
        with self.assertRaisesRegex(basic.DENIED,'обязательное свойство'):
            vm.execute('P.Validate();')
        vm.execute('C.Label="valid";P.Проверить();')
        with self.assertRaisesRegex(basic.DENIED,'procedure cannot be used as value'):
            vm.execute('Result=P.Validate();')

    def test_owning_property_metadata_requires_current_descriptor_identity(self):
        app=self.prepared();other=self.prepared();vm=app.interpreter
        for owner in (app,other):owner.interpreter.execute('P.Child=C;')
        vm.execute('Descriptor=C.OwningProperty();')
        descriptor=vm.variables['descriptor']
        vm.variables['foreign']=other.interpreter.variables['c']._owning
        copy=object.__new__(type(descriptor));vars(copy).update(vars(descriptor))
        vm.variables['forged']=copy
        self.assertEqual(vm.execute('Descriptor.Name;'),'Child')
        for code in ('Foreign.Name;','Forged.NamespaceURI;','Descriptor.Type;',
                     'Descriptor.Name="Other";'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        with patch.object(descriptor,'_name','changed'):
            with self.assertRaises(basic.DENIED):vm.execute('Descriptor.Name;')

    def test_owned_wrapper_assignment_retains_derived_and_rewraps_base(self):
        app=self.prepared();vm=app.interpreter;factory=app.xdto.factory
        vm.execute('A=XDTOFactory.Create(XDTOFactory.Type("urn:owned:records","Code"),"alias");'
                   'B=XDTOFactory.Create(XDTOFactory.Type("'+flat.XS+'","string"),"base");'
                   'C.Label="old";')
        before=(factory._nodes,factory._units)
        with patch.object(xdto_io,'MAX_NODES',before[0]):
            vm.execute('P.Label=A;')
            self.assertIs(vm.execute('P.GetXDTO("Label");'),vm.variables['a'])
            with self.assertRaises(basic.DENIED):vm.execute('C.Label=B;')
            self.assertEqual(vm.execute('C.Label;'),'old')
        self.assertEqual((factory._nodes,factory._units),before)
        vm.execute('C.Label=B;')
        converted=vm.execute('C.GetXDTO("Label");')
        self.assertIsNot(converted,vm.variables['b'])
        self.assertIs(converted._type,vm.variables['a']._type)
        self.assertEqual(vm.execute('C.Label;'),'base')
        self.assertEqual((factory._nodes,factory._units),(before[0]+1,before[1]+4))

    def test_retained_derived_property_does_not_extend_source_wire(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('P.Label=XDTOFactory.Create(XDTOFactory.Type("urn:owned:records","Code"),"alias");'
                   'XW=New XMLWriter;XW.SetString();JW=New JSONWriter;JW.SetString();')
        for key,call in (('xw','WriteXML(XW,P,"Root","urn:owned:records")'),
                         ('jw','WriteJSON(JW,P)')):
            writer=vm.variables[key];before=dict(vars(writer))
            with self.subTest(codec=key),self.assertRaisesRegex(basic.DENIED,'retained derived'):
                vm.execute('XDTOFactory.'+call+';')
            self.assertEqual(vars(writer),before)

    def test_nested_attach_replace_and_detach(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('C.Label="child";P.Child=C;')
        self.assertEqual(vm.execute('P.Child.Label;'),'child')
        self.assertIs(vm.variables['c']._owner,vm.variables['p'])
        vm.execute('P.Child=D;')
        self.assertIsNone(vm.variables['c']._owner)
        self.assertIs(vm.variables['d']._owner,vm.variables['p'])
        vm.execute('P.Unset("Child");')
        self.assertIsNone(vm.variables['d']._owner)
        self.assertIsNone(vm.execute('P.Child;'))
    def test_same_child_assignment_is_native_noop(self):
        app=self.prepared();vm=app.interpreter;vm.execute('P.Child=C;');before=(app.xdto.factory._nodes,app.xdto.factory._units)
        vm.execute('P.Child=C;')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_cycle_and_multiple_owner_denied_atomically(self):
        app=self.prepared();vm=app.interpreter;vm.execute('P.Child=C;')
        vm.execute('Other=XDTOFactory.Create(T);')
        for code in ('C.Child=P;','Other.Child=C;','P.Child=P;'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertIs(vm.variables['p']._values['Child'],vm.variables['c'])
        self.assertIs(vm.variables['c']._owner,vm.variables['p'])
    def test_scalar_list_methods_index_and_iteration(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('L=P.Labels;L.Add("a");L.Insert(0,"b");L.Set(1,"c");')
        self.assertEqual(vm.execute('L.Count();'),Decimal(2))
        self.assertEqual(vm.execute('L.Get(0);'),'b')
        self.assertEqual(vm.execute('L[1];'),'c')
        vm.execute('L[1]="d";S="";For Each X In L Do S=S+X;EndDo;')
        self.assertEqual(vm.variables['s'],'bd')
        vm.execute('L.Delete(0);L.Clear();')
        self.assertEqual(vm.execute('L.Count();'),0)
    def test_object_list_attach_delete_clear(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;L.Add(C);L.Add(D);')
        self.assertIs(vm.variables['c']._owner,vm.variables['p'])
        self.assertIs(vm.execute('L.Get(0);'),vm.variables['c'])
        vm.execute('L.Delete(0);')
        self.assertIsNone(vm.variables['c']._owner)
        vm.execute('L.Clear();')
        self.assertIsNone(vm.variables['d']._owner)
    def test_foreign_child_list_and_forged_object_denied(self):
        app=self.prepared();other=self.prepared();vm=app.interpreter
        other.interpreter.execute('L=P.Children;')
        vm.variables['foreign']=other.interpreter.variables['c'];vm.variables['foreignlist']=other.interpreter.variables['l']
        for code in ('P.Child=Foreign;','P.Children.Add(Foreign);','ForeignList.Count();'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_list_insertion_tight_quota_preserves_state(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;L.Add("old");')
        factory=app.xdto.factory;before=(factory._nodes,factory._units);items=tuple(vm.variables['l']._items)
        with patch.object(xdto_io,'MAX_NODES',before[0]+1):
            with self.assertRaises(basic.DENIED):vm.execute('L.Add("new");')
        self.assertEqual(tuple(vm.variables['l']._items),items)
        self.assertEqual((factory._nodes,factory._units),before)
    def test_lazy_list_quota_preserves_object(self):
        app=self.prepared();vm=app.interpreter;factory=app.xdto.factory;before=factory._nodes
        with patch.object(xdto_io,'MAX_NODES',before):
            with self.assertRaises(basic.DENIED):vm.execute('P.Children;')
        self.assertNotIn('Children',vm.variables['p']._values)
        self.assertEqual(factory._nodes,before)
    def test_mutated_child_denied_before_rhs(self):
        app=self.prepared();vm=app.interpreter;vm.execute('P.Child=C;');effects=[]
        vm.variables['c']._owner=None
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('rhs') or 'x')
        with self.assertRaises(basic.DENIED):vm.execute('P.Label=Touch();')
        self.assertEqual(effects,[])
    def test_mutated_list_items_not_admitted(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;L.Add(C);')
        vm.variables['l']._items.append(vm.variables['d'])
        with self.assertRaises(basic.DENIED):vm.execute('L.Count();')
    def test_nested_unknown_property_no_effects(self):
        app=self.prepared();vm=app.interpreter;vm.execute('P.Child=C;');effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('rhs') or 'x')
        with self.assertRaises(basic.DENIED):vm.execute('P.Child.Unknown=Touch();')
        self.assertEqual(effects,[])
    def test_io_and_descriptor_surface_still_denied(self):
        app=self.prepared();vm=app.interpreter
        for code in ('New XMLWriter(Undefined);','XDTOFactory.WriteXML(Undefined,P);','T.Properties.Count();','P.Properties();'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_orphan_list_handle_cannot_attach_unreachable_child(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;L.Add(C);P.Unset("Children");')
        self.assertIsNone(vm.variables['c']._owner)
        self.assertEqual(vm.execute('L.Count();'),0)
        with self.assertRaises(basic.DENIED):vm.execute('L.Add(D);')
        self.assertIsNone(vm.variables['d']._owner)
        vm.execute('Fresh=P.Children;Fresh.Add(D);')
        self.assertIs(vm.variables['d']._owner,vm.variables['p'])
        self.assertEqual(vm.execute('L.Count();'),0)
    def test_add_scalar_return_has_scalar_provenance(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;V=L.Add("x");')
        self.assertEqual(vm.execute('V.Value;'),'x')
        vm.execute('Old=L.Delete(0);')
        self.assertEqual(vm.execute('Old.Value;'),'x')
    def test_clear_delete_and_unset_do_not_refund_quota(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;L.Add("x");L.Add("yy");')
        before=(app.xdto.factory._nodes,app.xdto.factory._units)
        vm.execute('L.Delete(0);L.Clear();P.Unset("Labels");')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_list_same_child_set_noop_even_at_cap(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;L.Add(C);')
        before=(app.xdto.factory._nodes,app.xdto.factory._units)
        with patch.object(xdto_io,'MAX_NODES',before[0]):vm.execute('L.Set(0,C);')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_mutation_after_argument_prevents_list_commit(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;');before=app.xdto.factory._nodes
        def touch():
            vm.variables['l']._items=[]
            return vm.variables['c']
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('L.Add(Touch());')
        self.assertIsNone(vm.variables['c']._owner)
        self.assertEqual(app.xdto.factory._nodes,before)
    def test_list_arity_checked_before_argument_effects(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;');effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or 'x')
        with self.assertRaises(basic.DENIED):vm.execute('L.Add(Touch(),Touch());')
        self.assertEqual(effects,[])
    def test_closed_foreign_handle_rejected(self):
        app=self.prepared();other=self.prepared();other.interpreter.execute('L=P.Children;')
        app.interpreter.variables['old']=other.interpreter.variables['l'];other.close()
        with self.assertRaises(basic.DENIED):app.interpreter.execute('Old.Count();')
    def test_unrelated_tampering_not_resealed_by_other_mutation(self):
        app=self.prepared();vm=app.interpreter;vm.execute('C.Label="old";')
        vm.variables['c']._values['Label']._value='host changed'
        try:vm.execute('D.Label="safe";')
        except basic.DENIED:pass
        with self.assertRaises(basic.DENIED):vm.execute('C.Label;')
    def test_list_container_subclass_never_invoked(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;');effects=[]
        class Evil(list):
            def __iter__(self):effects.append('iter');return super().__iter__()
            def __len__(self):effects.append('len');return super().__len__()
        vm.variables['l']._items=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('L.Count();')
        self.assertEqual(effects,[])
    def test_list_and_child_field_keys_never_compared(self):
        for selection in ('list','child'):
            app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;L.Add(C);');effects=[]
            class Key:
                def __hash__(self):return hash('_owner')
                def __eq__(self,other):effects.append('eq');return False
            obj=vm.variables['l' if selection=='list' else 'c']
            obj.__dict__[Key()]=None;effects.clear()
            with self.subTest(selection=selection),self.assertRaises(basic.DENIED):vm.execute('L.Count();')
            self.assertEqual(effects,[])
    def test_full_subtree_depth_checked_before_attach(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('OType=XDTOFactory.Type("urn:owned:records","Outer");O=XDTOFactory.Create(OType);P.Child=C;')
        before=(app.xdto.factory._nodes,app.xdto.factory._units)
        with patch.object(xdto_io,'MAX_DEPTH',1):
            with self.assertRaises(basic.DENIED):vm.execute('O.Tree=P;')
        self.assertIsNone(vm.variables['p']._owner)
        self.assertIs(vm.variables['c']._owner,vm.variables['p'])
        self.assertNotIn('Tree',vm.variables['o']._values)
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_saved_list_methods_and_wrapper_result(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('L=P.Labels;Add=L.Add;Add("saved");GetValue=L.GetXDTO;V=GetValue(0);')
        self.assertEqual(vm.execute('V.Value;'),'saved')
    def test_list_method_references_rechecked_after_argument(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;Add=L.Add;');effects=[]
        class Evil:
            def __bool__(self):effects.append('bool');return False
        def touch():vm.variables['add'].reference_parameters=Evil();return 'x'
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('Add(Touch());')
        self.assertEqual(effects,[])
        self.assertEqual(vm.execute('L.Count();'),0)
    def test_saved_method_hostfunction_descriptor_hook_not_invoked(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;Add=L.Add;');effects=[]
        with patch.object(HostFunction,'function',property(lambda _:effects.append('getter')),create=True):
            with self.assertRaises(basic.DENIED):vm.execute('Add("x");')
        self.assertEqual(effects,[])
    def test_mutated_inventory_denied_before_create_allocation(self):
        app=self.prepared();vm=app.interpreter;vm.execute('C.Label="old";')
        vm.variables['c']._values['Label']._value='host changed';before=app.xdto.factory._nodes
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.Create(T);')
        self.assertEqual(app.xdto.factory._nodes,before)
    def test_scalar_list_return_bad_field_key_no_callback(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Labels;V=L.Add("x");');effects=[]
        class Key:
            def __hash__(self):return hash('_value')
            def __eq__(self,other):effects.append('eq');return False
        fields=vm.variables['v'].__dict__;fields.pop('_value');fields[Key()]='bad';effects.clear()
        with self.assertRaises(basic.DENIED):vm.execute('V.Value;')
        self.assertEqual(effects,[])
    def test_existing_iterator_keeps_native_snapshot_after_unset(self):
        app=self.prepared();vm=app.interpreter;vm.execute('L=P.Children;C.Label="a";D.Label="b";L.Add(C);L.Add(D);S="";For Each X In L Do S=S+X.Label;P.Unset("Children");EndDo;')
        self.assertEqual(vm.variables['s'],'ab')
        self.assertIsNone(vm.variables['c']._owner)
        self.assertIsNone(vm.variables['d']._owner)
        self.assertEqual(vm.execute('L.Count();'),0)

    def test_selected_reads_do_not_validate_unrelated_value_inventory(self):
        from yadinassi.execution.direct.source import python_direct_source_xdto_objects as direct
        app=self.prepared();vm=app.interpreter
        vm.execute('C.Label="child";P.Child=C;L=P.Labels;L.Add("a");L.Add("b");')
        vm.execute('For I=1 To 12 Do Extra=XDTOFactory.Create(F);EndDo;')
        original=direct._validate_records
        with patch.object(direct,'_validate_records',wraps=original) as audit:
            vm.execute('For I=1 To 10 Do R=P.GetXDTO("Child").Label;EndDo;')
            self.assertEqual(vm.variables['r'],'child')
            self.assertTrue(vm.execute('P.Установлено("Labels");'))
            self.assertIs(vm.execute('P.GetList("Labels");'),vm.variables['l'])
            self.assertEqual(vm.execute('L[1];'),'b')
            vm.execute('S="";For Each X In L Do S=S+X;EndDo;')
            self.assertEqual(vm.variables['s'],'ab')
            audit.assert_not_called()
            vm.execute('P.Validate();')
            self.assertGreater(audit.call_count,0)

    def test_mutations_check_only_affected_ownership_graphs(self):
        from yadinassi.execution.direct.source import python_direct_source_xdto_objects as direct
        app=self.prepared();vm=app.interpreter
        vm.execute('L=P.Children;L.Add(C); Other=XDTOFactory.Create(T);'
                   'OtherList=Other.Children;OtherChild=XDTOFactory.Create(F);'
                   'OtherChild.Label="independent";OtherList.Add(OtherChild);')
        unrelated=tuple(vm.variables[name] for name in ('other','otherlist','otherchild'))
        original=direct._saved_fields
        seen=[]
        def observe(records,value):
            seen.append(value)
            return original(records,value)

        with patch.object(direct,'_saved_fields',observe):
            vm.execute('L.Set(0,D); Bound=L.Set; Bound(0,C); L[0]=D;'
                       'L.Insert(0,C); A=L.Delete(0); L.Clear(); P.Unset("Children");'
                       'P.Child=C; P.Child=D; P.Unset("Child");')
        self.assertTrue(seen)
        self.assertFalse(any(value is outside for value in seen for outside in unrelated))
        self.assertIs(vm.variables['a'],vm.variables['c'])
        self.assertIsNone(vm.variables['c']._owner)
        self.assertIsNone(vm.variables['d']._owner)
        self.assertEqual(vm.execute('L.Count();'),0)
        self.assertEqual(vm.execute('Other.Children[0].Label;'),'independent')

    def test_selected_reads_use_current_record_and_backlink(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('C.Label="child";D.Label="other";L=P.Children;L.Add(C);L.Add(D);')
        c,d=vm.variables['c'],vm.variables['d'];items=vm.variables['l']._items
        # A valid object is not a valid replacement for another position.
        items[1]=c
        self.assertIs(vm.execute('L.Get(0);'),c)
        for source in ('L.GetXDTO(1);','D.Label;','L.Count();'):
            with self.subTest(source=source),self.assertRaises(basic.DENIED):vm.execute(source)
        items[1]=d
        self.assertEqual(vm.execute('L[1].Label;'),'other')

    def test_selected_get_xdto_checks_receiver_again_after_arguments(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('C.Label="original";P.Child=C;R="before";')
        parent=vm.variables['p'];effects=[]
        def touch():
            effects.append('argument')
            parent._values=dict(parent._values)
            return 'Child'
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('R=P.GetXDTO(Touch()).Label;')
        self.assertEqual(effects,['argument'])
        self.assertEqual(vm.variables['r'],'before')

    def test_iterator_rechecks_selected_scalar_after_host_effect(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('L=P.Labels;L.Add("a");L.Add("b");S="";')
        calls=[]
        def touch():
            calls.append(True)
            vm.variables['l']._items[1]._value='changed'
        vm.functions['touch']=HostFunction('Touch',touch,returns_value=False)
        with self.assertRaises(basic.DENIED):
            vm.execute('For Each X In L Do S=S+X;Touch();EndDo;')
        self.assertEqual(calls,[True])
        self.assertEqual(vm.variables['s'],'a')

    def test_selected_read_rejects_removed_or_mismatched_record(self):
        from yadinassi.execution.direct.source import python_direct_source_xdto_objects as direct
        app=self.prepared();vm=app.interpreter
        vm.execute('C.Label="child";P.Child=C;')
        child=vm.variables['c'];other=vm.variables['d'];records=direct._RECORDS[app]
        del records[child]
        with self.assertRaises(basic.DENIED):vm.execute('P.GetXDTO("Child");')
        records[child]=records[other]
        with self.assertRaises(basic.DENIED):vm.execute('P.Child;')
