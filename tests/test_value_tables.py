"""Ordinary ValueTable regressions grounded in the genuine owner checkpoint.

Expected state is independent of the active native output presentation format.
"""
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest
from unittest.mock import patch

from yadinassi.structures import BSLStructure
from yadinassi.type_descriptions import BSLTypeDescription as TD
from yadinassi.type_qualifiers import BSLStringQualifiers, BSLAllowedLength
from yadinassi.values import BSLArray, NULL
from yadinassi.value_tables import BSLValueTable, BSLValueTableRow, BSLValueTableColumn, BSLValueTableColumnCollection

D = Decimal


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


def sample():
    table = BSLValueTable()
    table.columns.add("Имя")
    table.columns.add("Число", TD("Число"))
    for i in range(1, 4):
        row = table.add()
        row.set_member("Имя", f"row{i}")
        row.set_member("Число", D(i))
    return table


def plain(value):
    if type(value) is BSLStructure:
        return {name: plain(item) for name, item in value._items.values()}
    if type(value) is BSLArray:
        return [plain(item) for item in value.items]
    if type(value) is BSLValueTable:
        return {"Count": D(len(value.rows)), "Columns": [plain(c) for c in value.columns], "Rows": [plain(r) for r in value]}
    if type(value) is BSLValueTableRow:
        return list(value)
    if type(value) is BSLValueTableColumn:
        return {"Name": value.name, "Title": value.title, "Width": value.width, "ValueType": value.value_type}
    return value


# Ordinary unit expectations transcribed from owner commit
# 195e4819794d7687eeafca89feb3d4b318355f18, collections.out table.mutate.*.
# Original SHA-256: 75babf916eac5b1f90defdd86f25829271f09ad1488770a00004136bf7ab2ce6.
# All 61 expanded records were checked against that genuine output before the
# research-format fixture dependency was removed. These builders contain only
# expected data, never ValueTable calls or a regenerated native oracle.
_BASE_ROWS = (("row1", D(1)), ("row2", D(2)), ("row3", D(3)))
_BASE_COLUMNS = (("Имя", "", D(0), TD()), ("Число", "", D(0), TD("Число")))
_DEFAULT_ROW = (None, D(0))


def expected_column(fields):
    return dict(zip(("Name", "Title", "Width", "ValueType"), fields))


def expected_table(rows=_BASE_ROWS, columns=_BASE_COLUMNS):
    return {"Count": D(len(rows)), "Columns": [expected_column(c) for c in columns],
            "Rows": [list(row) for row in rows]}


def mutation_expectations():
    """Compact baseline/deltas retain complete status, schema, rows and result."""
    expected = {}
    name, number = _BASE_COLUMNS
    row1, row2, row3 = _BASE_ROWS

    def cases(labels, *, rows=_BASE_ROWS, columns=_BASE_COLUMNS, result=None, status="ok"):
        for label in labels.split():
            if label in expected:
                raise AssertionError(f"Duplicate expectation: {label}")
            expected[label] = {"Status": status, "Table": expected_table(rows, columns),
                               "Result": result}

    # Same observed result does not merge the independent boundary actions.
    cases("row-add row-insert-end row-insert-negative row-insert-past",
          rows=(*_BASE_ROWS, _DEFAULT_ROW), result=list(_DEFAULT_ROW))
    cases("row-insert row-insert-fraction", rows=(row1, _DEFAULT_ROW, row2, row3),
          result=list(_DEFAULT_ROW))
    cases("row-name-index", rows=(("renamed", D(1)), row2, row3))
    cases("row-wrong-number row-null-number row-undefined-number load-invalid-values",
          rows=(("row1", D(0)), row2, row3))
    cases("row-missing-property row-index-out row-delete-past row-delete-negative "
          "row-delete-foreign row-move-wrap row-move-negative column-add-duplicate "
          "column-add-invalid column-add-number-name column-add-invalid-type "
          "column-rename-duplicate column-readonly-type columns-readonly "
          "column-delete-past column-delete-foreign column-move-wrap "
          "fill-unknown copy-unknown-column", status="error")
    cases("row-delete-index", rows=(row1, row3))
    cases("row-delete-object", rows=(row2, row3))
    cases("row-move", rows=(row2, row3, row1))
    cases("row-clear", rows=())

    new = ("Новая", "", D(0), TD())
    titled = ("Новая", "Заголовок", D(12), TD())
    anonymous = ("", "", D(0), TD())
    boolean = ("Булево", "", D(0), TD("Булево"))
    extended = tuple((*row, None) for row in _BASE_ROWS)
    cases("column-add", rows=extended, columns=(*_BASE_COLUMNS, titled),
          result=expected_column(titled))
    cases("column-add-default", rows=extended, columns=(*_BASE_COLUMNS, anonymous),
          result=expected_column(anonymous))
    cases("column-insert", rows=tuple((row[0], None, row[1]) for row in _BASE_ROWS),
          columns=(name, new, number), result=expected_column(new))
    cases("column-insert-past column-insert-negative", rows=extended,
          columns=(*_BASE_COLUMNS, new), result=expected_column(new))
    cases("column-rename-empty", columns=(anonymous, number))
    cases("column-negative-width", columns=(("Имя", "", D(4294967295), TD()), number))
    numeric_rows = tuple((row[1],) for row in _BASE_ROWS)
    cases("column-delete-name column-delete-object column-delete-index",
          rows=numeric_rows, columns=(number,))
    cases("column-move", rows=tuple((row[1], row[0]) for row in _BASE_ROWS),
          columns=(number, name))
    cases("column-clear", rows=(), columns=())
    cases("column-add-typed-existing", rows=tuple((*row, False) for row in _BASE_ROWS),
          columns=(*_BASE_COLUMNS, boolean), result=expected_column(boolean))

    cases("fill-all", rows=((D(7), D(7)),) * 3)
    cases("fill-selection", rows=tuple(("text", row[1]) for row in _BASE_ROWS))
    cases("fill-empty", rows=((D(8), D(8)),) * 3)
    cases("fill-duplicate", rows=tuple((row[0], D(9)) for row in _BASE_ROWS))
    cases("load-short", rows=(("row1", D(7)), row2, row3))
    cases("load-long", rows=(("row1", D(11)), ("row2", D(12)), ("row3", D(13))))
    cases("load-object-column", rows=(("loaded", D(1)), row2, row3))

    cases("copy-empty-columns", result=expected_table(rows=()))
    cases("copy-all", result=expected_table())
    cases("copy-columns", result=expected_table(rows=(), columns=(number, name)))
    cases("copy-selected", result=expected_table(rows=numeric_rows, columns=(number,)))
    cases("copy-filter", result=expected_table(rows=(row2,)))
    cases("copy-rows", result=expected_table(rows=(row3, row1, row1)))
    cases("copy-foreign", result=expected_table(rows=(row1,)))
    return expected


class ValueTableTests(unittest.TestCase):
    def test_owner_grounded_mutation_states(self):
        actions = {
            "row-add": lambda t,c,r,k: t.add(),
            "row-insert": lambda t,c,r,k: t.insert(D(1)),
            "row-insert-end": lambda t,c,r,k: t.insert(D(3)),
            "row-insert-negative": lambda t,c,r,k: t.insert(D(-1)),
            "row-insert-past": lambda t,c,r,k: t.insert(D(9)),
            "row-insert-fraction": lambda t,c,r,k: t.insert(D('1.9')),
            "row-name-index": lambda t,c,r,k: r.set_index("имя", "renamed"),
            "row-wrong-number": lambda t,c,r,k: r.set_member("Число", "bad"),
            "row-null-number": lambda t,c,r,k: r.set_member("Число", NULL),
            "row-undefined-number": lambda t,c,r,k: r.set_member("Число", None),
            "row-missing-property": lambda t,c,r,k: r.set_member("Missing", D(1)),
            "row-index-out": lambda t,c,r,k: r.set_index(D(2), D(1)),
            "row-delete-index": lambda t,c,r,k: t.delete(D(1)),
            "row-delete-object": lambda t,c,r,k: t.delete(r),
            "row-delete-past": lambda t,c,r,k: t.delete(D(9)),
            "row-delete-negative": lambda t,c,r,k: t.delete(D(-1)),
            "row-delete-foreign": lambda t,c,r,k: t.delete(sample().rows[0]),
            "row-move": lambda t,c,r,k: t.move(r, D(2)),
            "row-move-wrap": lambda t,c,r,k: t.move(D(0), D(5)),
            "row-move-negative": lambda t,c,r,k: t.move(D(0), D(-1)),
            "row-clear": lambda t,c,r,k: t.clear(),
            "column-add": lambda t,c,r,k: c.add("Новая", None, "Заголовок", D(12)),
            "column-add-default": lambda t,c,r,k: c.add(),
            "column-add-duplicate": lambda t,c,r,k: c.add("иМя"),
            "column-add-invalid": lambda t,c,r,k: c.add("bad name"),
            "column-add-number-name": lambda t,c,r,k: c.add(D(7)),
            "column-add-invalid-type": lambda t,c,r,k: c.add("Новая", "Строка"),
            "column-insert": lambda t,c,r,k: c.insert(D(1), "Новая"),
            "column-insert-past": lambda t,c,r,k: c.insert(D(9), "Новая"),
            "column-insert-negative": lambda t,c,r,k: c.insert(D(-1), "Новая"),
            "column-rename-duplicate": lambda t,c,r,k: k.set_member("Имя", "ЧИСЛО"),
            "column-rename-empty": lambda t,c,r,k: k.set_member("Имя", ""),
            "column-negative-width": lambda t,c,r,k: k.set_member("Ширина", D(-1)),
            "column-readonly-type": lambda t,c,r,k: k.set_member("ValueType", TD("Строка")),
            "columns-readonly": lambda t,c,r,k: t.set_member("Columns", sample().columns),
            "column-delete-name": lambda t,c,r,k: c.delete("Имя"),
            "column-delete-object": lambda t,c,r,k: c.delete(k),
            "column-delete-index": lambda t,c,r,k: c.delete(D(0)),
            "column-delete-past": lambda t,c,r,k: c.delete(D(9)),
            "column-delete-foreign": lambda t,c,r,k: c.delete(sample().columns.items[0]),
            "column-move": lambda t,c,r,k: c.move(k, D(1)),
            "column-move-wrap": lambda t,c,r,k: c.move(D(0), D(3)),
            "column-clear": lambda t,c,r,k: c.clear(),
            "column-add-typed-existing": lambda t,c,r,k: c.add("Булево", TD("Булево")),
            "copy-empty-columns": lambda t,c,r,k: t.copy_columns(""),
            "fill-all": lambda t,c,r,k: t.fill_values(D(7)),
            "fill-selection": lambda t,c,r,k: t.fill_values("text", "Имя"),
            "fill-empty": lambda t,c,r,k: t.fill_values(D(8), ""),
            "fill-unknown": lambda t,c,r,k: t.fill_values(D(8), "Имя,Нет"),
            "fill-duplicate": lambda t,c,r,k: t.fill_values(D(9), "Число,Число"),
            "load-short": lambda t,c,r,k: t.load_column(array(D(7)), "Число"),
            "load-long": lambda t,c,r,k: t.load_column(array(*map(D,range(11,16))), D(1)),
            "load-object-column": lambda t,c,r,k: t.load_column(array("loaded"), k),
            "load-invalid-values": lambda t,c,r,k: t.load_column(array("bad"), "Число"),
            "copy-all": lambda t,c,r,k: t.copy(),
            "copy-columns": lambda t,c,r,k: t.copy_columns("Число,Имя"),
            "copy-selected": lambda t,c,r,k: t.copy(None, "Число"),
            "copy-filter": lambda t,c,r,k: t.copy(BSLStructure("Имя", "row2")),
            "copy-rows": lambda t,c,r,k: t.copy(array(t.rows[2],r,r)),
            "copy-foreign": lambda t,c,r,k: t.copy(array(sample().rows[0])),
            "copy-unknown-column": lambda t,c,r,k: t.copy_columns("Имя,Нет"),
        }
        expected = mutation_expectations()
        self.assertEqual(set(expected), set(actions))
        self.assertEqual(len(actions), 61)
        self.assertEqual(sum(v["Status"] == "error" for v in expected.values()), 19)
        for scenario, action in actions.items():
            with self.subTest(scenario=scenario):
                table = sample()
                status, result = "ok", None
                try:
                    result = action(table,table.columns,table.rows[0],table.columns.items[0])
                except (TypeError, ValueError, IndexError):
                    status = "error"
                self.assertEqual({"Status": status,"Table": plain(table),"Result": plain(result)}, expected[scenario])

    def test_scalar_totals(self):
        for kind, value, assigned, total in [
            ("Строка", D(7), "7", D(7)), ("Строка", "bad", "bad", D(0)),
            ("Булево", "Истина", True, D(1)), ("Строка,Число", "7", "7", D(0)),
            ("Булево,Строка", "7", "7", None), ("Число", NULL, D(0), D(0))]:
            t = BSLValueTable(); t.columns.add("Value", TD(kind)); r = t.add()
            r.set_member("Value",value)
            self.assertEqual(r.get_member("Value"),assigned)
            self.assertEqual(t.total("Value"),total)
        t = BSLValueTable(); t.columns.add("Value")
        for v in [D(1), D(2), "3", True, NULL, None]:
            t.add().set_member("Value",v)
        self.assertEqual(t.total("Value"),D(3))

    def test_total_is_exact_under_hostile_decimal_context(self):
        t = BSLValueTable()
        t.columns.add("Value")
        large = D("1e4096")
        small = D((0, (1,) * 4096, -8191))
        for value in (large, small):
            t.add().set_member("Value", value)
        expected = D((0, (1,) + (0,) * 8191 + (1,) * 4096, -8191))
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.Emax, ctx.Emin = 2, -2
            ctx.traps[Inexact] = True
            ctx.traps[Rounded] = True
            self.assertEqual(t.total("Value"), expected)
            self.assertFalse(ctx.flags[Inexact])
            self.assertFalse(ctx.flags[Rounded])
            self.assertIs(t.get(D("1.9")), t.rows[1])
            single = BSLValueTable()
            single.columns.add("Value")
            single.add().set_member("Value", large)
            self.assertEqual(single.total("Value"), large)
        with patch("yadinassi.value_tables._MAX_TOTAL_PRECISION", 20):
            with self.assertRaises(ValueError):
                t.total("Value")

    def test_documented_method_selector_bounds(self):
        t = sample()
        for selector in (D(0), t.columns.items[0]):
            with self.assertRaises(TypeError):
                t.total(selector)
        # Native index checkpoint also confirms string column selectors here.
        t.columns.move("Имя", D(1))
        self.assertEqual([column.name for column in t.columns], ["Число", "Имя"])
        with self.assertRaises(IndexError):
            t.columns.move("Имя", D(1))
        self.assertEqual([column.name for column in t.columns], ["Число", "Имя"])

    def test_clear_columns_also_clears_zero_column_rows(self):
        t = BSLValueTable()
        row = t.add()
        t.columns.clear()
        self.assertEqual(t.rows, [])
        with self.assertRaises(ValueError):
            row.owner()

    def test_fixed_default(self):
        t = BSLValueTable()
        t.columns.add("Value", TD("Строка",None,BSLStringQualifiers(D(4),BSLAllowedLength.FIXED)))
        r=t.add(); self.assertEqual(r.get_member("Value"),"    ")
        r.set_member("Value","Я"); self.assertEqual(r.get_member("Value"),"Я   ")

    def test_identity_and_deletion(self):
        t=sample(); r=t.rows[0]; c=t.columns.items[0]
        c.set_member("Name","Other"); t.move(r,D(2)); t.columns.move(c,D(1))
        self.assertIs(t.rows[2],r); self.assertEqual(r.get_member("Other"),"row1")
        t.delete(r)
        self.assertEqual(t.index_of(r),D(-1))
        for f in [r.owner,lambda:r.get_member("Other"),lambda:r.set_member("Other",1)]:
            with self.assertRaises(ValueError): f()
        t.columns.delete(c)
        self.assertEqual(t.columns.index_of(c),D(4294967295))
        self.assertEqual(c.name,"")
        t.columns.delete(D(0)); self.assertEqual(t.rows,[])

    def test_lookup_copy_and_nested_sharing(self):
        t=sample(); r=t.rows[0]; nested=array(D(1)); r.set_member("Имя",nested)
        self.assertIs(t.find(nested),r)
        self.assertIs(t.find_rows(BSLStructure("Число",D(1))).items[0],r)
        self.assertEqual(len(t.find_rows(BSLStructure()).items),0)
        copied=t.copy(); self.assertIs(copied.rows[0].get_member("Имя"),nested)
        self.assertIs(t.unload_column("Имя").items[0],nested)
        copied.columns.items[0].set_member("Name","Changed")
        self.assertEqual(t.columns.items[0].name,"Имя")

    def test_protocol_and_budget(self):
        t=sample(); r=t.rows[0]; c=t.columns.items[0]
        for obj in [t,t.columns,r,c]:
            for field in ["__dict__","table","rows","cells","items"]:
                with self.assertRaises(ValueError): obj.get_member(field)
        for obj in [r,t.columns]:
            with self.assertRaises(TypeError): obj.get("Имя")
            self.assertIsNotNone(obj.get_index("Имя"))
        for v in [True,1,D('NaN'),D('Infinity'),D('1e999999')]:
            with self.assertRaises((TypeError,ValueError)): t.get(v)
        with patch('yadinassi.value_tables._MAX_CELLS',6):
            with self.assertRaises(ValueError): t.add()
            with self.assertRaises(ValueError): t.columns.add("Extra")
        self.assertEqual(len(t.rows),3); self.assertEqual(len(t.columns.items),2)
        t.columns.add("Get"); r.set_member("Get","property")
        self.assertEqual(r.get_member("Get"),"property")
        self.assertEqual(r.get_method("Get").function(D(0)),"row1")


if __name__ == '__main__':
    unittest.main()
