"""Authored bounded hierarchy contract; no native parity claim."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from sqlite_catalog_fixture import configuration_files
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.queries import BSLQuery


def hierarchy_files():
    files=configuration_files()
    files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<Hierarchical>false</Hierarchical>',b'<Hierarchical>true</Hierarchical><HierarchyType>HierarchyFoldersAndItems</HierarchyType>')
    return files


class HierarchyXMLTests(unittest.TestCase):
    def test_explicit_groups_profile(self):
        c=import_configuration(hierarchy_files())
        self.assertEqual([s.hierarchy for s in c.catalogs],['none','groups_v1'])
    def test_unsupported_hierarchy_modes(self):
        for value in ('','HierarchyItems','false','Unknown'):
            f=hierarchy_files();f['Catalogs/Products.xml']=f['Catalogs/Products.xml'].replace(b'HierarchyFoldersAndItems',value.encode())
            with self.subTest(value=value),self.assertRaises(ValueError):import_configuration(f)
    def test_invalid_boolean(self):
        f=hierarchy_files();f['Catalogs/Products.xml']=f['Catalogs/Products.xml'].replace(b'<Hierarchical>true',b'<Hierarchical>yes')
        with self.assertRaises(ValueError):import_configuration(f)
    def test_hierarchy_reserved_fields(self):
        for name in ('Parent','IsFolder','Родитель','ЭтоГруппа'):
            f=hierarchy_files();f['Catalogs/Products.xml']=f['Catalogs/Products.xml'].replace(b'<Name>Text</Name>',('<Name>'+name+'</Name>').encode())
            with self.subTest(name=name),self.assertRaises(ValueError):import_configuration(f)
    def test_flat_profile_unchanged(self):
        c=import_configuration(configuration_files());self.assertTrue(all(s.hierarchy=='none' for s in c.catalogs))


class CatalogHierarchyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'owned.sqlite'
        self.context=SQLiteDBContext.create(self.path,import_configuration(hierarchy_files()))
        self.out=[];self.vm=Interpreter(database_context=self.context,output=self.out.append)
    def tearDown(self):
        self.context.close();self.temp.cleanup()
    def seed(self):
        self.vm.execute('''A=Catalogs.Products.CreateFolder();A.Code="A";A.Description="Root";A.Write();
B=Catalogs.Products.CreateFolder();B.Code="B";B.Parent=A.Ref;B.Write();
C=Catalogs.Products.CreateItem();C.Code="C";C.Parent=B.Ref;C.Write();
D=Catalogs.Products.CreateItem();D.Code="D";D.Write();''')
    def rows(self,text,root=None):
        q=BSLQuery(self.vm._catalogs,text,documents=self.vm._documents,information_registers=self.vm._information_registers)
        if root is not None:q.set_parameter('Root',root)
        return q.execute()._rows
    def test_explicit_v10(self):self.assertEqual(self.context.backend.storage_version,10)
    def test_folder_and_item_defaults(self):
        self.vm.execute('F=Catalogs.Products.CreateFolder();I=Catalogs.Products.CreateItem();Message(F.IsFolder);Message(I.IsFolder);Message(F.Parent.IsEmpty());')
        self.assertEqual(self.out,['Да','Нет','Да'])
    def test_reopen_parent_and_kind(self):
        self.seed();self.context.close();self.context=SQLiteDBContext(self.path);v=Interpreter(database_context=self.context)
        self.assertEqual(v.execute('Catalogs.Products.FindByCode("C").Parent.Code'),'B')
        self.assertTrue(v.execute('Catalogs.Products.FindByCode("B").IsFolder'))
    def test_local_move_not_visible_until_write(self):
        self.seed();self.vm.execute('O=C.Ref.GetObject();O.Parent=A.Ref;Message(C.Ref.Parent.Code);O.Write();Message(C.Ref.Parent.Code);')
        self.assertEqual(self.out,['B','A'])
    def test_move_to_root(self):
        self.seed();self.vm.execute('B.Parent=Catalogs.Products.EmptyRef();B.Write();Message(B.Ref.Parent.IsEmpty());Message(C.Ref.Parent.Code);')
        self.assertEqual(self.out,['Да','B'])
    def test_group_move_preserves_descendants(self):
        self.seed();self.vm.execute('E=Catalogs.Products.CreateFolder();E.Code="E";E.Write();B.Parent=E.Ref;B.Write();')
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root) ORDER BY Code',self.vm.execute('E.Ref')),(('B',),('C',),('E',)))
    def test_parent_requires_same_catalog_reference(self):
        self.seed()
        for expr in ('Undefined','Null','1','True','"A"','Catalogs.Categories.EmptyRef()'):
            with self.subTest(expr=expr),self.assertRaises((ValueError,TypeError,BSLRuntimeError)):self.vm.execute('C.Parent='+expr+';')
    def test_nonexistent_parent_rejected(self):
        self.seed();self.vm.execute('X=Catalogs.Products.GetRef(New UUID("'+str(uuid4())+'"));C.Parent=X;')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('C.Write();')
        self.assertEqual(self.vm.execute('C.Ref.Parent.Code'),'B')
    def test_item_cannot_be_parent(self):
        self.seed();self.vm.execute('D.Parent=C.Ref;')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('D.Write();')
        self.assertTrue(self.vm.execute('D.Ref.Parent.IsEmpty()'))
    def test_self_cycle_rejected(self):
        self.seed();self.vm.execute('A.Parent=A.Ref;')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('A.Write();')
        self.assertTrue(self.vm.execute('A.Ref.Parent.IsEmpty()'))
    def test_descendant_cycle_rejected(self):
        self.seed();self.vm.execute('A.Parent=B.Ref;')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('A.Write();')
        self.assertTrue(self.vm.execute('A.Ref.Parent.IsEmpty()'))
    def test_kind_readonly(self):
        self.seed()
        for obj in ('A','C'):
            with self.subTest(obj=obj),self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute(obj+'.IsFolder=True;')
    def test_flat_create_folder_refuses(self):
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('Catalogs.Categories.CreateFolder();')
    def test_russian_members(self):
        self.vm.execute('Г=Справочники.Products.СоздатьГруппу();Г.Код="A";Г.Записать();Э=Справочники.Products.СоздатьЭлемент();Э.Код="B";Э.Родитель=Г.Ссылка;Э.Записать();Сообщить(Г.ЭтоГруппа);Сообщить(Э.Родитель.Код);')
        self.assertEqual(self.out,['Да','A'])
    def test_selection_parent_and_kind(self):
        self.seed();self.vm.execute('S=Catalogs.Products.Select();While S.Next() Do Message(S.Code+":"+String(S.IsFolder));EndDo;')
        self.assertEqual(self.out,['A:Да','B:Да','C:Нет','D:Нет'])
    def test_metadata_flag(self):
        self.assertTrue(self.vm.execute('Metadata.Catalogs.Products.Hierarchical'))
        self.assertFalse(self.vm.execute('Metadata.Catalogs.Categories.Hierarchical'))
    def test_stale_move_conflict(self):
        self.seed();self.vm.execute('X=C.Ref.GetObject();Y=C.Ref.GetObject();X.Parent=A.Ref;X.Write();Y.Parent=Catalogs.Products.EmptyRef();')
        with self.assertRaises((ValueError,BSLRuntimeError)):self.vm.execute('Y.Write();')
        self.assertEqual(self.vm.execute('C.Ref.Parent.Code'),'A')
    def test_mark_is_non_cascading(self):
        self.seed();self.vm.execute('A.DeletionMark=True;A.Write();Message(B.Ref.DeletionMark);Message(C.Ref.DeletionMark);')
        self.assertEqual(self.out,['Нет','Нет'])
    def test_query_system_fields(self):
        self.seed();rows=self.rows('SELECT Code, IsFolder, Parent FROM Catalog.Products ORDER BY Code')
        self.assertEqual([(r[0],r[1],r[2].is_empty()) for r in rows],[('A',True,True),('B',True,False),('C',False,False),('D',False,True)])
    def test_query_parent_equality(self):
        self.seed();self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Parent=&Root ORDER BY Code',self.vm.execute('B.Ref')),(('C',),))
    def test_hierarchy_includes_root_and_descendants(self):
        self.seed();self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root) ORDER BY Code',self.vm.execute('A.Ref')),(('A',),('B',),('C',)))
    def test_hierarchy_empty_root_is_whole_catalog(self):
        self.seed();self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root)',self.vm.execute('Catalogs.Products.EmptyRef()'))),4)
    def test_hierarchy_leaf_matches_itself(self):
        self.seed();self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root)',self.vm.execute('C.Ref')),(('C',),))
    def test_not_in_hierarchy(self):
        self.seed();self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Ref NOT IN HIERARCHY (&Root) ORDER BY Code',self.vm.execute('A.Ref')),(('D',),))
    def test_hierarchy_russian_query(self):
        self.seed();self.assertEqual(self.rows('ВЫБРАТЬ Код КАК Code ИЗ Справочник.Products ГДЕ Ссылка В ИЕРАРХИИ (&Root) УПОРЯДОЧИТЬ ПО Code',self.vm.execute('B.Ref')),(('B',),('C',)))
    def test_hierarchy_scalar_or_foreign_ref_refuses_even_empty(self):
        for root in (1,self.vm.execute('Catalogs.Categories.EmptyRef()')):
            with self.subTest(root=type(root).__name__),self.assertRaises((TypeError,ValueError)):self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root)',root)
    def test_hierarchy_flat_refuses(self):
        with self.assertRaises(ValueError):self.rows('SELECT Code FROM Catalog.Categories WHERE Ref IN HIERARCHY (&Root)',self.vm.execute('Catalogs.Categories.EmptyRef()'))
    def test_hierarchy_joins_derived_and_aggregation(self):
        self.seed();self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM (SELECT Ref FROM Catalog.Products WHERE Ref IN HIERARCHY (&Root)) AS T',self.vm.execute('A.Ref'))[0][0],3)
    def test_readonly_reopen(self):
        self.seed();self.context.close();self.context._backend=__import__("yadinassi.sqlite_catalog",fromlist=["SQLiteCatalogBackend"]).SQLiteCatalogBackend(self.path,read_only=True);v=Interpreter(database_context=self.context)
        self.assertEqual(v.execute('Catalogs.Products.FindByCode("C").Parent.Code'),'B')
        with self.assertRaises((ValueError,BSLRuntimeError)):v.execute('Catalogs.Products.CreateFolder();')
