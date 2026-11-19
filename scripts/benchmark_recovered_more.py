"""Explicit new contracts for the next recovery slice, not historical source parity."""
from yadinassi import Interpreter
from yadinassi.execution.codegen import native_bare_compiler as bare
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.native_bare_collections import BareArray, BareStructure, BareMap, BareValueList
from yadinassi.execution.codegen.native_bare_table import BareTable

# BSL source, Python source, classes source, fixture kind, result kind, description.
CASES = {}
def case(name, bsl, py, cls, fixture, result, note):
    CASES[name] = (bsl, py, cls or py, fixture, result, note)

case('method.array.create', 'For I=0 To N-1 Do R=New Array; EndDo;',
     'for i in range(n):\n    r = []', 'for i in range(n):\n    r = BareArray()',
     'none', 'empty_array', 'N empty Array constructions; only last result retained')
case('method.array.find', 'R=0; For I=0 To N-1 Do R=R+A.Find(I); EndDo;',
     'r=0\nfor i in range(n):\n    r += a.index(i)', 'r=0\nfor i in range(n):\n    r += a.find(i)',
     'array_read', 'sum', 'N ascending successful linear searches in N prefilled values; quadratic total work')
case('method.array.insert', 'For I=0 To N-1 Do A.Insert(0,I); EndDo; R=A;',
     'for i in range(n):\n    a.insert(0,i)\nr=a', None,
     'array_empty', 'reverse', 'N inserts at index zero; full reverse order validated')
case('method.array.delete', 'For I=0 To N-1 Do A.Delete(N-I-1); EndDo; R=A;',
     'for i in range(n):\n    del a[n-i-1]\nr=a', 'for i in range(n):\n    a.delete(n-i-1)\nr=a',
     'array_full', 'empty_array', 'N deletions at computed descending index; no constant pop shortcut')
case('method.structure.create', 'For I=0 To N-1 Do R=New Structure; EndDo;',
     'for i in range(n):\n    r={}', 'for i in range(n):\n    r=BareStructure()',
     'none', 'empty_structure', 'N empty Structure constructions; only last result retained')
case('method.structure.insert', 'For I=0 To N-1 Do A.Insert("X",I); EndDo; R=A;',
     'for i in range(n):\n    a["x"]=i\nr=a', 'for i in range(n):\n    a.insert("X",i)\nr=a',
     'structure_empty', 'last_structure', 'N Insert calls on the same name X, overwriting after first; not N distinct fields')
case('method.structure.get', 'R=0; For I=0 To N-1 Do R=R+A.X; EndDo;',
     'r=0\nfor i in range(n):\n    r += a["x"]', 'r=0\nfor i in range(n):\n    r += a.get_member("x")',
     'structure_read', 'n', 'N named reads of prefilled X=1; Python canonical dict key')
case('method.structure.set', 'For I=0 To N-1 Do A.X=I; EndDo; R=A;',
     'for i in range(n):\n    a["x"]=i\nr=a', 'for i in range(n):\n    a.set_member("x",i)\nr=a',
     'structure_full', 'last_structure', 'N named writes to existing X; Python canonical dict key')
case('method.structure.property', 'R=0; For I=0 To N-1 Do If A.Property("X") Then R=R+1; EndIf; EndDo;',
     'r=0\nfor i in range(n):\n    if "x" in a: r += 1', 'r=0\nfor i in range(n):\n    if a.property("X"): r += 1',
     'structure_read', 'n', 'N successful Property membership checks; no output/byref parameter')
case('method.structure.delete', 'For I=0 To N-1 Do A.Delete("X"); EndDo; R=A;',
     'for i in range(n):\n    a.pop("x",None)\nr=a', 'for i in range(n):\n    a.delete("X")\nr=a',
     'structure_full', 'empty_structure', 'N deletes of X: first exists, remaining missing; not N distinct deletes')
case('method.structure.iterate', 'R=0; For Each P In A Do R=R+P.Value; EndDo;',
     'r=0\nfor v in a.values():\n    r += v', 'r=0\nfor p in a:\n    r += p.get_member("value")',
     'structure_many_read', 'sum', 'One traversal of N fields; Python values, classes lightweight pairs, BSL projections')
case('calls', 'Function F(Val X) Return X+1; EndFunction; R=0; For I=0 To N-1 Do R=R+F(I); EndDo;',
     'def f(x):\n    return x+1\nr=0\nfor i in range(n):\n    r += f(i)', None,
     'none', 'sum_plus_n', 'N value-argument function calls; definition included in all timed layers')
case('byref', 'Procedure Inc(X) X=X+1; EndProcedure; R=0; For I=0 To N-1 Do Inc(R); EndDo;',
     'def inc(x):\n    x[0] += 1\ncell=[0]\nfor i in range(n):\n    inc(cell)\nr=cell[0]', None,
     'none', 'n', 'N scalar byref increments; Python uses one mutable list cell, not a scalar-return substitute')


case('method.map.create', 'For I=0 To N-1 Do R=New Map; EndDo;',
     'for i in range(n):\n    r={}', 'for i in range(n):\n    r=BareMap()',
     'none', 'empty_structure', 'N empty Map constructions; last result retained')
case('method.map.delete', 'For I=0 To N-1 Do A.Delete(I); EndDo; R=A;',
     'for i in range(n):\n    a.pop(i,None)\nr=a', 'for i in range(n):\n    a.delete(i)\nr=a',
     'map_full', 'empty_structure', 'N distinct integer key deletions, prefilled Map')
case('method.valuelist.create', 'For I=0 To N-1 Do R=New ValueList; EndDo;',
     'for i in range(n):\n    r=[]', 'for i in range(n):\n    r=BareValueList()',
     'none', 'empty_array', 'N empty ValueList constructions; last result retained')
case('method.valuelist.delete', 'For I=0 To N-1 Do A.Delete(N-I-1); EndDo; R=A;',
     'for i in range(n):\n    del a[n-i-1]\nr=a', 'for i in range(n):\n    a.delete(n-i-1)\nr=a',
     'list_full', 'empty_array', 'N deletions at computed descending item indices')
case('method.valuelist.insert', 'For I=0 To N-1 Do A.Insert(0,I); EndDo; R=A;',
     'for i in range(n):\n    a.insert(0,[i,"",False,None])\nr=a', 'for i in range(n):\n    a.insert(0,i)\nr=a',
     'list_empty', 'list_reverse', 'N insertions at index zero; four default fields retained')
case('method.valuelist.set', 'For I=0 To N-1 Do A.Get(I).Value=I; EndDo; R=A;',
     'for i in range(n):\n    a[i][0]=i\nr=a', 'for i in range(n):\n    a.get(i).set_member("value",i)\nr=a',
     'list_zero', 'list_ascending', 'N Value field writes on existing four-field items')
case('method.valuelist.sort', 'A.SortByValue(); R=A;',
     'a.sort(key=lambda item:item[0])\nr=a', 'a.sort_by_value()\nr=a',
     'list_reverse', 'list_ascending', 'One ascending value sort of N reverse-ordered items')
case('method.valuelist.find', 'R=0; For I=0 To N-1 Do R=R+A.FindByValue(I).Value; EndDo;',
     'r=0\nfor i in range(n):\n    r += next(item for item in a if item[0]==i)[0]',
     'r=0\nfor i in range(n):\n    r += a.find_by_value(i).get_member("value")',
     'list_read', 'sum', 'N successful linear searches plus returned Value read; quadratic total work')
case('method.valuetable.create', 'For I=0 To N-1 Do R=New ValueTable; R.Columns.Add("N"); EndDo;',
     'for i in range(n):\n    r={"schema":{"n":0},"rows":[]}',
     'for i in range(n):\n    r=BareTable()\n    r.add_column("N")',
     'none', 'table_empty', 'N one-column table constructions; Python allocates schema and rows, last table retained')
case('method.valuetable.delete', 'For I=0 To N-1 Do A.Delete(N-I-1); EndDo; R=A;',
     'for i in range(n):\n    del a[n-i-1]\nr=a', 'for i in range(n):\n    a.delete(n-i-1)\nr=a',
     'table_full', 'table_empty', 'N deletions at computed descending row indices')
case('method.valuetable.insert', 'For I=0 To N-1 Do A.Insert(0); EndDo; R=A;',
     'for i in range(n):\n    a.insert(0,[None])\nr=a', 'for i in range(n):\n    a.insert(0)\nr=a',
     'table_empty', 'table_null', 'N default one-cell row insertions at zero')
case('method.valuetable.set', 'For I=0 To N-1 Do A.Get(I).N=I; EndDo; R=A;',
     'for i in range(n):\n    a[i][columns["n"]]=i\nr=a', 'for i in range(n):\n    a.get(i).set_member("n",i)\nr=a',
     'table_zero', 'table_ascending', 'N named cell writes; Python resolves the column via a prebuilt schema dictionary on each write')
case('method.valuetable.set_positional', 'For I=0 To N-1 Do A.Get(I)[0]=I; EndDo; R=A;',
     'for i in range(n):\n    a[i][0]=i\nr=a', 'for i in range(n):\n    a.get(i).set(0,i)\nr=a',
     'table_zero', 'table_ascending', 'N positional cell writes in prefilled one-column table')
case('method.valuetable.sort', 'A.Sort("N"); R=A;',
     'a.sort(key=lambda row:row[0])\nr=a', 'a.sort("N")\nr=a',
     'table_reverse', 'table_ascending', 'One ascending named-column sort of N reverse-ordered rows')
case('method.valuetable.find', 'R=0; For I=0 To N-1 Do R=R+A.Find(I,"N").N; EndDo;',
     'r=0\nfor i in range(n):\n    r += next(row for row in a if row[0]==i)[0]',
     'r=0\nfor i in range(n):\n    r += a.find(i,"N").get_member("n")',
     'table_read', 'sum', 'N successful linear searches and named cell reads; N4096 deliberately skipped')

case('arithmetic', 'R=0; For I=0 To N-1 Do R=R+(I*3+2)-I; EndDo;',
     'r=0\nfor i in range(n):\n    r=r+(i*3+2)-i', None,
     'none', 'arithmetic', 'N integer multiply/add/subtract iterations; sum of 2*i+2, no division/Decimal')
case('string.concat', 'R=""; For I=0 To N-1 Do R=R+"x"; EndDo;',
     'r=""\nfor i in range(n):\n    r=r+"x"', None,
     'none', 'concat', 'N repeated immutable string concatenations; final x repeated N times')
case('array', 'For I=0 To N-1 Do A.Add(I); EndDo; R=0; For Each X In A Do R=R+X; EndDo;',
     'for i in range(n):\n    a.append(i)\nr=0\nfor x in a:\n    r += x',
     'for i in range(n):\n    a.add(i)\nr=0\nfor x in a:\n    r += x',
     'array_empty', 'array_sum', 'Build N integer elements then sum one traversal; empty fixture outside timing; final storage checked')
case('map', 'For I=0 To N-1 Do A.Insert(I,I); EndDo; R=0; For Each P In A Do R=R+P.Value; EndDo;',
     'for i in range(n):\n    a[i]=i\nr=0\nfor value in a.values():\n    r += value',
     'for i in range(n):\n    a.insert(i,i)\nr=0\nfor pair in a:\n    r += pair.get_member("value")',
     'map_empty', 'map_sum', 'Build N integer entries then sum values; Python values/classes pairs/BSL field projection; empty fixture excluded')

case('string.slice', 'R=""; For I=0 To N-1 Do R=Mid("abcdef",2,3); EndDo;',
     'r=""\nfor i in range(n):\n    r="abcdef"[1:4]', None,
     'none', 'slice', 'N slices of fixed ASCII string, 1-based BSL offset2/count3 versus Python[1:4]; last result bcd')
case('string.replace', 'R=""; For I=0 To N-1 Do R=StrReplace("abcabc","a","xy"); EndDo;',
     'r=""\nfor i in range(n):\n    r="abcabc".replace("a","xy")', None,
     'none', 'replace', 'N fixed ASCII replacements a->xy; last result xybcxybc')


def bind(name, n, layer):
    bsl, py, cls, fixture_kind, result_kind, note = CASES[name]
    current = [None]
    before = [None]
    def snapshot(value):
        return list(dict.items(value)) if fixture_kind.startswith(('structure','map')) else [list(row) for row in value] if fixture_kind.startswith(('table','list')) else list(value)
    def reset_fixture():
        if fixture_kind == 'none': value = None
        elif fixture_kind in ('map_full','map_empty'):
            data = {} if fixture_kind=='map_empty' else {i:i for i in range(n)}
            value = data if layer=='python' else BareMap(data)
        elif fixture_kind.startswith(('table','list')):
            table = fixture_kind.startswith('table')
            data = ([] if fixture_kind.endswith('empty') else [0]*n if fixture_kind.endswith('zero')
                    else list(reversed(range(n))) if fixture_kind.endswith('reverse') else list(range(n)))
            if layer == 'python': value = [[i] if table else [i,'',False,None] for i in data]
            else:
                value = BareTable() if table else BareValueList()
                if table: value.add_column('N')
                for i in data:
                    if table: value.add()[0]=i
                    else: value.add(i)
        elif fixture_kind.startswith('array'):
            data = [] if fixture_kind == 'array_empty' else list(range(n))
            if layer == 'python': value = data
            else: value = BareArray(); value._data = data
        else:
            data = ({'k'+str(i): i for i in range(n)} if fixture_kind == 'structure_many_read'
                    else {} if fixture_kind == 'structure_empty' else {'x': 1})
            value = data if layer == 'python' else BareStructure(data)
        current[0] = value
        if fixture_kind.endswith('read'): before[0] = snapshot(value)
        return value
    if layer in ('python','classes'):
        source = py if layer == 'python' else cls
        namespace = {'BareArray': BareArray, 'BareStructure': BareStructure, 'BareMap':BareMap, 'BareValueList':BareValueList, 'BareTable':BareTable}
        if layer == 'python' and name == 'method.valuetable.set':
            namespace['columns'] = {'n': 0}
        exec('def run(n,a):\n'+'\n'.join('    '+line for line in source.splitlines())+'\n    return r', namespace)
        function = namespace['run']
        def reset(): reset_fixture()
        def run(): return function(n,current[0])
    else:
        source = bsl; vm = Interpreter(); program = parse(source)
        plan = bare.prepare_module(vm,program) if layer == 'prepared' else None
        def reset():
            vm.variables.clear(); vm.variables.update(n=n,a=reset_fixture())
        def run():
            if layer == 'prepared': bare.execute_prepared(vm,plan)
            else: bare.execute(vm,program)
            return vm.variables['r']
    def validate(value):
        if fixture_kind.endswith('read') and snapshot(current[0]) != before[0]:
            raise AssertionError('read workload mutated fixture')
        if fixture_kind.startswith('table') and layer != 'python':
            if current[0].schema != {'n':0} or any(row.table is not current[0] for row in current[0]):
                raise AssertionError('table schema/row ownership changed')
        if result_kind in ('slice','replace'):
            expected='bcd' if result_kind=='slice' else 'xybcxybc'
            if type(value) is not str or value != expected: raise AssertionError((name,value,expected))
        elif result_kind in ('arithmetic','concat','array_sum','map_sum'):
            expected = n*(n+1) if result_kind=='arithmetic' else 'x'*n if result_kind=='concat' else n*(n-1)//2
            if type(value) is not type(expected) or value != expected: raise AssertionError((name,value,expected))
            if result_kind=='array_sum' and list(current[0]) != list(range(n)): raise AssertionError('array build state')
            if result_kind=='map_sum' and list(dict.items(current[0])) != [(i,i) for i in range(n)]: raise AssertionError('map build state')
        elif result_kind.startswith(('table_','list_')):
            if result_kind == 'table_empty': expected=[]
            elif result_kind == 'table_null': expected=[[None] for _ in range(n)]
            elif result_kind == 'table_ascending': expected=[[i] for i in range(n)]
            else: expected=[[i,'',False,None] for i in (reversed(range(n)) if result_kind=='list_reverse' else range(n))]
            if result_kind.startswith('table') and layer != 'python':
                if value.schema != {'n':0} or any(row.table is not value for row in value): raise AssertionError('table result metadata')
            if name=='method.valuetable.create' and layer=='python':
                if value['schema'] != {'n':0}: raise AssertionError('Python schema')
                actual=value['rows']
            else: actual=[list(row) for row in value]
            if actual != expected: raise AssertionError('full nested collection state')
        elif result_kind in ('n','sum','sum_plus_n'):
            expected = {'n':n,'sum':n*(n-1)//2,'sum_plus_n':n*(n+1)//2}[result_kind]
            if type(value) is not int or value != expected: raise AssertionError((name,value,expected))
        elif result_kind in ('empty_structure','last_structure'):
            expected = {} if result_kind == 'empty_structure' else {'x':n-1}
            if list(dict.items(value)) != list(expected.items()): raise AssertionError('full Structure state')
        else:
            expected = list(reversed(range(n))) if result_kind == 'reverse' else []
            if list(value) != expected: raise AssertionError('full Array state')
    return reset,run,validate,source,note
