"""Explicit new contracts for the next recovery slice, not historical source parity."""
from yadinassi import Interpreter, native_bare_compiler as bare
from yadinassi.syntax.parser import parse
from yadinassi.native_bare_collections import BareArray, BareStructure

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


def bind(name, n, layer):
    bsl, py, cls, fixture_kind, result_kind, note = CASES[name]
    current = [None]
    before = [None]
    def snapshot(value):
        return list(dict.items(value)) if fixture_kind.startswith('structure') else list(value)
    def reset_fixture():
        if fixture_kind == 'none': value = None
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
        namespace = {'BareArray': BareArray, 'BareStructure': BareStructure}
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
        if result_kind in ('n','sum','sum_plus_n'):
            expected = {'n':n,'sum':n*(n-1)//2,'sum_plus_n':n*(n+1)//2}[result_kind]
            if type(value) is not int or value != expected: raise AssertionError((name,value,expected))
        elif result_kind in ('empty_structure','last_structure'):
            expected = {} if result_kind == 'empty_structure' else {'x':n-1}
            if list(dict.items(value)) != list(expected.items()): raise AssertionError('full Structure state')
        else:
            expected = list(reversed(range(n))) if result_kind == 'reverse' else []
            if list(value) != expected: raise AssertionError('full Array state')
    return reset,run,validate,source,note
