"""Small reconstructed default compiler. Unsupported syntax never falls back.

This executes trusted code, not a sandbox. The old interpreter is a separate
explicit backend. This first recovery package deliberately supports only basic
scalars, arrays and control flow; it does not recreate the lost full snapshot.
"""
from dataclasses import dataclass, fields
from decimal import Decimal
from .syntax import ast as bsl
from .native_bare_collections import BareArray, BareMap, BareStructure, BareValueList, BareMapEntry
from .native_bare_table import BareTable
from .native_bare_structure_ops import bare_fill_property_values

METHODS = {}
for names, target in [
    (('add', 'добавить'), 'add'), (('insert', 'вставить'), 'insert'),
    (('get', 'получить'), 'get'), (('set', 'установить'), 'set'),
    (('delete', 'удалить'), 'delete'), (('clear', 'очистить'), 'clear'),
    (('count', 'количество'), 'count'), (('ubound', 'вграница'), 'ubound'),
    (('find', 'найти'), 'find'), (('copy', 'скопировать'), 'copy'),
    (('copycolumns', 'скопироватьколонки'), 'copy_columns'),
    (('total', 'итог'), 'total'), (('sort', 'сортировать'), 'sort'),
    (('owner', 'владелец'), 'owner'),
    (('property', 'свойство'), 'property'),
    (('unloadvalues','выгрузитьзначения'),'unload_values'),
    (('loadvalues','загрузитьзначения'),'load_values'),
    (('indexof','индекс'),'index_of'),
    (('findbyvalue','найтипозначению'),'find_by_value'),
    (('fillchecks','заполнитьпометки'),'fill_checks'),
    (('sortbyvalue','сортироватьпозначению'),'sort_by_value'),
    (('sortbypresentation','сортироватьпопредставлению'),'sort_by_presentation'),
    (('move','сдвинуть'),'move')]:
    METHODS.update(dict.fromkeys(names, target))


def unsupported(message):
    from .python_direct import PythonDirectUnsupported
    raise PythonDirectUnsupported('bare reconstruction: ' + message)


@dataclass(frozen=True)
class BarePrepared:
    function: object
    generated_source: str


class Compiler:
    def __init__(self):
        self.names = set()
        self.serial = 0
        self.constants = []
        self.routines = {}
        self.ref_names = set()
        self.allowed_names = None
        self.map_entries = {}
        self.kinds = {}
        self.ambiguous_entries = set()
    @staticmethod
    def raw_name(name):
        return '_v_' + name.casefold().encode().hex()
    @staticmethod
    def routine_name(name):
        return '_f_' + name.casefold().encode().hex()
    @staticmethod
    def walk(nodes):
        pending = list(nodes)
        while pending:
            value = pending.pop()
            if isinstance(value, bsl.Node):
                yield value
                pending.extend(getattr(value, f.name) for f in fields(value) if f.name != 'token')
            elif type(value) in (list, tuple): pending.extend(value)
    def references(self, nodes):
        result = set()
        for node in self.walk(nodes):
            if type(node) is bsl.Call and type(node.callee) is bsl.Name:
                routine = self.routines.get(node.callee.name.casefold())
                if routine:
                    for arg, parameter in zip(node.arguments, routine.parameters):
                        if not parameter.by_value and type(arg) is bsl.Name:
                            result.add(arg.name.casefold())
        return result
    def name(self, name):
        key = name.casefold()
        if key in self.ambiguous_entries: unsupported('branch-dependent iterator representation: '+name)
        if self.allowed_names is not None and key not in self.allowed_names:
            unsupported('routine free variable ' + name)
        self.names.add(key)
        return self.raw_name(key) + ('[0]' if key in self.ref_names else '')
    def temp(self):
        self.serial += 1
        return '_t' + str(self.serial)
    def expr(self, node):
        kind = type(node)
        if kind is bsl.Literal:
            value = node.value
            if type(value) is Decimal:
                if value.as_tuple().exponent == 0: return repr(int(value))
                self.constants.append(value)
                return '_constants[' + str(len(self.constants)-1) + ']'
            if type(value) in (str, int, float, bool, type(None)): return repr(value)
            unsupported('literal type ' + type(value).__name__)
        if kind is bsl.Name:
            key=node.name.casefold()
            value=self.name(node.name)
            if key in self.map_entries:
                flag=self.map_entries[key]
                fail="_unsupported('whole map entry escape requires an explicit assignment')"
                return fail if flag is None else '('+fail+' if '+flag+' else '+value+')'
            return value
        if kind is bsl.Group: return '(' + self.expr(node.expression) + ')'
        if kind is bsl.New:
            target = {'array':'_BareArray','массив':'_BareArray',
                      'valuetable':'_BareTable','таблицазначений':'_BareTable',
                      'map':'_BareMap','соответствие':'_BareMap',
                      'structure':'_BareStructure','структура':'_BareStructure',
                      'valuelist':'_BareValueList','списокзначений':'_BareValueList'}.get(node.name.casefold())
            if target is None: unsupported('constructor ' + node.name)
            return target + '(' + ', '.join(map(self.expr,node.arguments)) + ')'
        if kind is bsl.Attribute:
            if type(node.object) is bsl.Name and node.object.name.casefold() in self.map_entries:
                flag=self.map_entries[node.object.name.casefold()]
                value=self.name(node.object.name)
                index={'key':0,'ключ':0,'value':1,'значение':1}.get(node.name.casefold())
                projected=(value+'['+str(index)+']') if index is not None else "_unsupported('unknown map entry field')"
                return projected if flag is None else '('+projected+' if '+flag+' else '+value+'.get_member('+repr(node.name.casefold())+'))'
            return '(' + self.expr(node.object) + ').get_member(' + repr(node.name.casefold()) + ')'
        if kind is bsl.Index:
            return self.expr(node.object) + '[' + self.expr(node.index) + ']'
        if kind is bsl.Call:
            if type(node.callee) is bsl.Name and node.callee.name.casefold() in self.routines:
                routine = self.routines[node.callee.name.casefold()]
                if len(node.arguments) != len(routine.parameters): unsupported('routine arity/default arguments')
                args = []
                for arg, parameter in zip(node.arguments, routine.parameters):
                    if parameter.by_value: args.append(self.expr(arg))
                    elif type(arg) is bsl.Name:
                        if arg.name.casefold() in self.map_entries: unsupported('map entry by-reference escape')
                        self.name(arg.name)
                        self.kinds.pop(arg.name.casefold(),None)
                        args.append(self.raw_name(arg.name))
                    elif type(arg) in (bsl.Index,bsl.Attribute):
                        unsupported('indexed/member by-reference arguments')
                    else: args.append('[' + self.expr(arg) + ']')
                return self.routine_name(routine.name) + '(' + ', '.join(args) + ')'
            arguments = list(map(self.expr, node.arguments))
            args = ', '.join(arguments)
            if type(node.callee) is bsl.Attribute:
                method = METHODS.get(node.callee.name.casefold())
                if method is None: unsupported('method ' + node.callee.name)
                return '(' + self.expr(node.callee.object) + ').' + method + '(' + args + ')'
            if type(node.callee) is bsl.Name:
                name = node.callee.name.casefold()
                if name in ('fillpropertyvalues','заполнитьзначениясвойств'):
                    if len(arguments) not in (2,3,4):unsupported('FillPropertyValues arity')
                    return '_fill_properties('+args+')'
                if name in ('strreplace','стрзаменить'):
                    if len(arguments)!=3:unsupported('StrReplace arity')
                    return 'str.replace('+args+')'
                if name in ('mid','сред'):
                    if len(arguments) not in (2,3):unsupported('Mid arity')
                    bounds=node.arguments[1:]
                    if all(type(n) is bsl.Literal and type(n.value) is Decimal and n.value.as_tuple().exponent==0 for n in bounds):
                        start=max(0,int(bounds[0].value)-1)
                        stop='' if len(bounds)==1 else str(start+max(0,int(bounds[1].value)))
                        return '('+arguments[0]+')['+str(start)+':'+stop+']'
                    start=self.temp()
                    lower='('+start+' := max(0, '+arguments[1]+' - 1))'
                    upper='' if len(arguments)==2 else start+' + max(0, '+arguments[2]+')'
                    return '('+arguments[0]+')['+lower+':'+upper+']'
                target = {'strlen':'len','стрдлина':'len', 'upper':'str.upper','врег':'str.upper',
                          'lower':'str.lower','нрег':'str.lower','trimall':'str.strip','сокрлп':'str.strip'}.get(name)
                if target: return target + '(' + args + ')'
            unsupported('function call')
        if kind is bsl.Binary:
            op = {'=':'==','<>':'!=','и':'and','или':'or'}.get(node.operator.casefold(), node.operator.casefold())
            if op not in ('+','-','*','/','%','==','!=','<','>','<=','>=','and','or'): unsupported('operator '+op)
            left, right = self.expr(node.left), self.expr(node.right)
            if op == '/': left = '_Decimal(' + left + ')'
            return '(' + left + ' ' + op + ' ' + right + ')'
        if kind is bsl.Unary:
            op = {'не':'not'}.get(node.operator.casefold(), node.operator.casefold())
            if op not in ('+', '-', 'not'): unsupported('unary '+op)
            return '(' + op + ' ' + self.expr(node.operand) + ')'
        if kind is bsl.Conditional:
            return '(' + self.expr(node.when_true) + ' if ' + self.expr(node.condition) + ' else ' + self.expr(node.when_false) + ')'
        unsupported('expression '+kind.__name__)
    def invalidate_loop_inputs(self,nodes):
        # A later iteration can observe writes made at the end of an earlier one.
        for node in self.walk(nodes):
            if type(node) is bsl.Assign and type(node.target) is bsl.Name:
                self.kinds.pop(node.target.name.casefold(),None)
            elif type(node) in (bsl.For,bsl.ForEach):self.kinds.pop(node.name.casefold(),None)
            elif type(node) is bsl.Var:
                for name in node.names:self.kinds.pop(name.casefold(),None)
        for name in self.references(nodes):self.kinds.pop(name,None)
    def collection_kind(self,node):
        if type(node) is bsl.New:
            return 'map' if node.name.casefold() in ('map','соответствие') else 'other'
        if type(node) is bsl.Name:return self.kinds.get(node.name.casefold())
        return None
    def body(self, nodes, depth):
        lines=[]
        for node in nodes: lines.extend(self.stmt(node,depth))
        return lines or ['    '*depth+'pass']
    def stmt(self, node, depth):
        prefix='    '*depth; kind=type(node)
        if kind is bsl.Assign:
            if type(node.target) is bsl.Name and node.target.name.casefold() in self.map_entries:
                # Reassigning the iterator itself is outside this small projection contract.
                unsupported('map/collection iterator reassignment')
            if type(node.value) is bsl.Name and node.value.name.casefold() in self.map_entries:
                key=node.value.name.casefold(); raw=self.name(node.value.name); flag=self.map_entries[key]
                value='_BareMapEntry(*'+raw+')'
                if flag is not None: value='('+value+' if '+flag+' else '+raw+')'
            else: value=self.expr(node.value)
            if type(node.target) is bsl.Attribute:
                return [prefix + '(' + self.expr(node.target.object) + ').set_member(' + repr(node.target.name.casefold()) + ', ' + value + ')']
            if type(node.target) not in (bsl.Name,bsl.Index): unsupported('assignment '+type(node.target).__name__)
            target=self.expr(node.target)
            if type(node.target) is bsl.Name:
                kind_value=self.collection_kind(node.value)
                if kind_value is None:self.kinds.pop(node.target.name.casefold(),None)
                else:self.kinds[node.target.name.casefold()]=kind_value
            return [prefix+target+' = '+value]
        if kind is bsl.ExpressionStatement:
            call = node.expression
            # A discarded Columns.Add result does not require a column reference.
            if (type(call) is bsl.Call and type(call.callee) is bsl.Attribute
                    and call.callee.name.casefold() in ('add','добавить')
                    and type(call.callee.object) is bsl.Attribute
                    and call.callee.object.name.casefold() in ('columns','колонки')):
                return [prefix + '(' + self.expr(call.callee.object.object) + ').add_column(' + ', '.join(map(self.expr,call.arguments)) + ')']
            return [prefix+self.expr(node.expression)]
        if kind is bsl.Var:
            if node.execution_context != 'client': unsupported('server declaration')
            return [prefix+self.name(n)+' = None' for n in node.names]
        if kind is bsl.If:
            lines=[]; outcomes=[]
            remaining_kinds=dict(self.kinds);remaining_entries=dict(self.map_entries)
            remaining_ambiguous=set(self.ambiguous_entries)
            for index,(condition,branch) in enumerate(node.branches):
                self.kinds=dict(remaining_kinds);self.map_entries=dict(remaining_entries)
                self.ambiguous_entries=set(remaining_ambiguous)
                condition_source=self.expr(condition)
                # Condition calls can invalidate known variable kinds on both paths.
                remaining_kinds=dict(self.kinds);remaining_entries=dict(self.map_entries)
                remaining_ambiguous=set(self.ambiguous_entries)
                lines.append(prefix+('if ' if index==0 else 'elif ')+condition_source+':')
                lines.extend(self.body(branch,depth+1))
                outcomes.append((dict(self.kinds),dict(self.map_entries),set(self.ambiguous_entries)))
            self.kinds=dict(remaining_kinds);self.map_entries=dict(remaining_entries)
            self.ambiguous_entries=set(remaining_ambiguous)
            if node.otherwise:lines += [prefix+'else:']+self.body(node.otherwise,depth+1)
            outcomes.append((dict(self.kinds),dict(self.map_entries),set(self.ambiguous_entries)))
            self.kinds={k:v for k,v in outcomes[0][0].items() if all(o[0].get(k)==v for o in outcomes)}
            self.map_entries={k:v for k,v in outcomes[0][1].items() if all(k in o[1] and o[1][k]==v for o in outcomes)}
            all_entries=set().union(*(o[1].keys() for o in outcomes))
            self.ambiguous_entries=set().union(*(o[2] for o in outcomes)) | (all_entries-self.map_entries.keys())
            return lines
        if kind is bsl.For:
            # Start/end evaluate once and in source order; native int counters.
            name=self.name(node.name); limit=self.temp()
            lines=[prefix+name+' = '+self.expr(node.start),prefix+limit+' = '+self.expr(node.end)]
            before=dict(self.kinds)
            self.invalidate_loop_inputs(node.body)
            lines += [prefix+'for '+name+' in range('+name+', '+limit+' + 1):']+self.body(node.body,depth+1)
            self.kinds={k:v for k,v in before.items() if self.kinds.get(k)==v}
            return lines
        if kind is bsl.ForEach:
            collection=self.temp(); flag=self.temp(); key=node.name.casefold()
            collection_kind=self.collection_kind(node.collection)
            value=self.expr(node.collection); target=self.name(node.name)
            self.map_entries.pop(key,None)
            self.kinds.pop(key,None)
            lines=[prefix+collection+' = '+value]
            if collection_kind=='map':
                iterator='dict.items('+collection+')';self.map_entries[key]=None
            elif collection_kind=='other':iterator=collection
            else:
                lines += [prefix+flag+' = type('+collection+') is _BareMap']
                iterator='(dict.items('+collection+') if '+flag+' else '+collection+')'
                self.map_entries[key]=flag
            before=dict(self.kinds)
            self.invalidate_loop_inputs(node.body)
            result=lines+[prefix+'for '+target+' in '+iterator+':']+self.body(node.body,depth+1)
            self.kinds={k:v for k,v in before.items() if self.kinds.get(k)==v}
            return result
        if kind is bsl.While:
            condition=self.expr(node.condition);before=dict(self.kinds)
            self.invalidate_loop_inputs(node.body)
            result=[prefix+'while '+condition+':']+self.body(node.body,depth+1)
            self.kinds={k:v for k,v in before.items() if self.kinds.get(k)==v}
            return result
        if kind is bsl.Return:
            if self.allowed_names is None: unsupported('module Return')
            return [prefix+'return '+(self.expr(node.value) if node.value is not None else 'None')]
        if kind is bsl.Break: return [prefix+'break']
        if kind is bsl.Continue: return [prefix+'continue']
        unsupported('statement '+kind.__name__)
    def compile(self, nodes, source_name):
        self.routines = {node.name.casefold(): node for node in nodes if type(node) is bsl.Routine}
        module = [node for node in nodes if type(node) is not bsl.Routine]
        self.ref_names = self.references(module)
        definitions = []
        for routine in self.routines.values():
            if routine.is_async or routine.execution_context != 'client': unsupported('async/server routine')
            if any(p.default is not None for p in routine.parameters): unsupported('routine default arguments')
            compiler = Compiler()
            compiler.routines = self.routines
            compiler.constants = self.constants
            parameters = {p.name.casefold() for p in routine.parameters}
            compiler.allowed_names = set(parameters)
            for node in self.walk(routine.body):
                if type(node) is bsl.Assign and type(node.target) is bsl.Name: compiler.allowed_names.add(node.target.name.casefold())
                elif type(node) in (bsl.For,bsl.ForEach): compiler.allowed_names.add(node.name.casefold())
                elif type(node) is bsl.Var: compiler.allowed_names.update(n.casefold() for n in node.names)
            compiler.ref_names = compiler.references(routine.body) | {p.name.casefold() for p in routine.parameters if not p.by_value}
            body = compiler.body(routine.body,2)
            loads = []
            for key in sorted(compiler.ref_names):
                parameter = next((p for p in routine.parameters if p.name.casefold()==key),None)
                if parameter is None: loads.append('        '+compiler.raw_name(key)+' = [None]')
                elif parameter.by_value: loads.append('        '+compiler.raw_name(key)+' = ['+compiler.raw_name(key)+']')
            signature = ', '.join(compiler.raw_name(p.name) for p in routine.parameters)
            definitions += ['    def '+self.routine_name(routine.name)+'('+signature+'):', *loads, *body]
        body=self.body(module,2)
        if module and type(module[-1]) is bsl.ExpressionStatement:
            body[-1]='        return '+self.expr(module[-1].expression)
        loads=[]
        for key in sorted(self.names):
            value='_state.get('+repr(key)+', _unset)'
            if key in self.ref_names: value='['+value+']'
            loads.append('    '+self.raw_name(key)+' = '+value)
        publish=[]
        for key in sorted(self.names):
            var=self.raw_name(key)+('[0]' if key in self.ref_names else '')
            publish += ['        if '+var+' is not _unset:', '            _state['+repr(key)+'] = '+var]
        source='\n'.join(['def run(_state):', *loads, *definitions, '    try:', *body,
                         '    finally:', *(publish or ['        pass'])])+'\n'
        namespace={'_BareArray':BareArray,'_BareTable':BareTable,
                   '_fill_properties':bare_fill_property_values,'_BareMap':BareMap,'_BareMapEntry':BareMapEntry,'_unsupported':unsupported,'_BareStructure':BareStructure,'_BareValueList':BareValueList,'_Decimal':Decimal,'_constants':tuple(self.constants),'_unset':object()}
        exec(compile(source,source_name or '<bare>','exec'),namespace)
        return BarePrepared(namespace['run'],source)


def prepare_module(vm, program, *, source_text=None, source_name=None):
    if vm.execution_backend != 'python-direct': unsupported('prepare requires python-direct')
    return Compiler().compile(program,source_name)


def execute_prepared(vm, prepared):
    if type(prepared) is not BarePrepared: raise TypeError('expected BarePrepared')
    if vm.execution_backend != 'python-direct': unsupported('execute requires python-direct')
    # Lifecycle boundary only, not an input/environment walk.
    vm._require_family()
    return prepared.function(vm.variables)


def execute(vm, program, *, source_text=None, source_name=None):
    return execute_prepared(vm,prepare_module(vm,program,source_text=source_text,source_name=source_name))
