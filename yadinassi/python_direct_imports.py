"""Owned synchronous file imports; syntax-only namespaces, never host objects."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakKeyDictionary, ref

from .syntax import ast
from .runtime import (Interpreter, _Module, _Namespace,
                      _DIRECT_IMPORT_LOADER_ABI, _DIRECT_IMPORT_RECEIVER_ABI)
from .values import Reference
from .errors import BSLError
from .experimental_naked_boundaries import BoundaryViolation

_GRANTS=WeakKeyDictionary()
_SEALS=WeakKeyDictionary()
_PUBLIC=WeakKeyDictionary()
_LOADER_ABI=_DIRECT_IMPORT_LOADER_ABI
_CLASS_ABI=_DIRECT_IMPORT_RECEIVER_ABI
_MAX_MODULES=256
_MAX_DEPTH=64


def _hooks(vm):
    if type(vm) is not Interpreter:raise BoundaryViolation('foreign import interpreter')
    if type(vm.imports) is not dict or type(vm._module_cache) is not dict or type(vm._loading) is not list:
        raise BoundaryViolation('custom import storage is not supported')
    for cls,items,mro in _CLASS_ABI:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(items) or any(current.get(k) is not v for k,v in items):
            raise BoundaryViolation('import receiver class hooks changed')
    for name,expected in _LOADER_ABI:
        if name in vars(vm) or vars(Interpreter).get(name) is not expected:
            raise BoundaryViolation('import loader hooks changed')


def import_names(vm,program=(),*,facts=None):
    if type(vm.imports) is not dict or any(type(name) is not str for name in vm.imports):
        raise BoundaryViolation('invalid import root storage')
    names=set(vm.imports)
    if facts is not None:
        names.update(facts.roots)
        return tuple(sorted(names))
    from .syntax.lexer import KEYWORDS
    for node in program:
        if type(node) is not ast.Import:continue
        filename=node.filename
        if type(filename) is not str:raise BoundaryViolation('invalid import specification')
        parts=(filename[:-4] if filename.casefold().endswith('.bsl') else filename).split('.')
        if any(not p or not (p[0].isalpha() or p[0]=='_') or
               not all(c.isalnum() or c=='_' for c in p) or p.casefold() in KEYWORDS for p in parts):
            raise BSLError('Недопустимое имя импорта',node.token.source,node.token.line,node.token.column)
        names.add(parts[0].casefold())
    return tuple(sorted(names))


@dataclass(frozen=True, slots=True)
class PreparedImportFacts:
    """Syntax-only immutable summaries, never cached authority or live state."""
    imports: tuple
    declarations: tuple
    routine_exports: tuple
    variable_exports: frozenset
    roots: frozenset
    source: str


def prepare_facts(vm, program):
    # Validate filenames once against the same canonical syntax rules. Live
    # namespace storage/layout is still validated at every invocation.
    import_names(vm, program)
    imports=[]; declarations=[]; routines=[]; variables=set(); roots=set()
    for node in program:
        if type(node) is ast.Import:
            imports.append((node.filename,node.token))
            roots.add(node.filename.split('.')[0].casefold())
        elif type(node) is ast.Routine:
            key=node.name.casefold()
            declarations.append(((key,),node.token));routines.append((key,node.exported))
        elif type(node) is ast.Var:
            declarations.append((tuple(name.casefold() for name in node.names),node.token))
            variables.update(name.casefold() for name in node.exported_names)
    return PreparedImportFacts(tuple(imports),tuple(declarations),tuple(routines),
                               frozenset(variables),frozenset(roots),
                               program[0].token.source if program else '<строка>')


def _contract(vm):
    if any(type(value) is not str for value in (vm.execution_backend,vm.native_target,vm.compilation_profile)):
        raise BoundaryViolation('invalid import execution contract')
    if type(vm._family_generation) is not int:raise BoundaryViolation('invalid import generation')
    if type(vm._module_cache) is not dict or type(vm._loading) is not list:
        raise BoundaryViolation('invalid import cache or loading stack')
    return (vm.execution_backend,vm.native_target,vm.compilation_profile,id(vm.database_context),
            id(vm._module_cache),id(vm._loading),vm._family_generation)


def owned_child(vm):
    grant=_GRANTS.get(vm)
    if grant is None:return False
    parent,root,path,loading,contract=grant
    parent=parent();root=root()
    if root is None or (loading and parent is None):return False
    if any(type(value) is not bool for value in (root._family_closed,vm._family_closed,vm._family_released)):
        raise BoundaryViolation('invalid import lifetime state')
    if type(vm._family_generation) is not int or type(root._family_generation) is not int:
        raise BoundaryViolation('invalid import generation')
    if (root._family_closed or vm._family_closed
            or vm._family_released or vm._family_generation!=root._family_generation):return False
    if vm._family_owner is not root or vm._module_cache is not root._module_cache:return False
    if vm._loading is not root._loading or vm._self_module.path is not path:return False
    if _contract(vm)!=contract or _contract(root)!=contract:return False
    if (root._configuration_runtime is not None or vm._configuration_runtime is not None
            or root.execution_context!='client' or not root._has_module_context):
        return False
    if any(type(key) is not type(path) for key in root._module_cache):
        raise BoundaryViolation('invalid import cache key')
    return loading or root._module_cache.get(path) is vm._self_module


@contextmanager
def loading_child(parent,child,path):
    _hooks(parent)
    root=parent._family_owner
    if parent is not root and not owned_child(parent):raise BoundaryViolation('foreign import parent')
    if len(root._module_cache)+len(root._loading)>=_MAX_MODULES or len(root._loading)>=_MAX_DEPTH:
        raise ValueError('Импорт: превышен предел числа модулей или глубины')
    grant=(ref(parent),ref(root),path,True,
           _contract(child))
    _GRANTS[child]=grant
    try:
        yield
    except BaseException:
        _GRANTS.pop(child,None);_PUBLIC.pop(child,None);_SEALS.pop(child,None)
        raise
    else:_GRANTS[child]=(*grant[:3],False,grant[4])


def _tree(vm):
    rows=[];seen=set()
    def walk(members,depth):
        if type(members) is not dict or depth>_MAX_DEPTH:raise BoundaryViolation('invalid import namespace')
        if id(members) in seen:raise BoundaryViolation('cyclic import namespace')
        seen.add(id(members));rows.append(('members',id(members),len(members)))
        for name,item in members.items():
            if type(name) is not str:raise BoundaryViolation('invalid import name')
            if type(item) is _Namespace:
                rows.append((name,id(item),id(item.path)));walk(item.members,depth+1)
            elif type(item) is _Module:
                child=item.interpreter
                if type(child) is not Interpreter or child._self_module is not item or item.ready is not True or not owned_child(child):
                    raise BoundaryViolation('foreign or unavailable imported module')
                public=_PUBLIC.get(child)
                if public is None:raise BoundaryViolation('unsealed imported exports')
                registry=getattr(child,'_direct_routine_modules',{})
                for key,(identity,signature) in public[0].items():
                    module=registry.get(key)
                    if id(module)!=identity or module.signatures.get(key) is not signature:
                        raise BoundaryViolation('imported routine declaration changed')
                rows.append((name,id(item),id(child),id(item.path),tuple(public[0].items()),public[1]))
            else:raise BoundaryViolation('foreign import binding')
        seen.remove(id(members))
    try:walk(vm.imports,0)
    finally:del walk
    return tuple(rows)


def check_live(vm):
    if type(vm.imports) is not dict:raise BoundaryViolation('custom import root storage')
    if not vm.imports and vm._family_owner is vm and vm not in _SEALS:return
    _hooks(vm)
    if vm._family_owner is not vm and not owned_child(vm):raise BoundaryViolation('foreign import child')
    if vm.imports or vm in _SEALS:
        if _SEALS.get(vm)!=_tree(vm):raise BoundaryViolation('import namespace changed outside loader')


def preflight(vm,program=(),*,facts=None):
    if facts is not None:
        if facts.imports:_hooks(vm)
        names=set(import_names(vm,facts=facts))
        if names:
            for declared,token in facts.declarations:
                if any(name in names for name in declared):
                    raise BSLError('Имя импорта конфликтует с объявлением',token.source,token.line,token.column)
        for filename,token in facts.imports:
            name=filename.split('.')[0].casefold()
            if name in vm.variables or name in vm.functions or name in getattr(vm,'_direct_routine_modules',{}):
                raise BSLError('Имя импорта уже занято: '+name,token.source,token.line,token.column)
        return
    if any(type(node) is ast.Import for node in program):_hooks(vm)
    names=set(import_names(vm,program))
    for node in program:
        declared=([node.name] if type(node) is ast.Routine else node.names if type(node) is ast.Var else ())
        if any(name.casefold() in names for name in declared):
            raise BSLError('Имя импорта конфликтует с объявлением',node.token.source,node.token.line,node.token.column)
    for node in program:
        if type(node) is ast.Import:
            name=node.filename.split('.')[0].casefold()
            if name in vm.variables or name in vm.functions or name in getattr(vm,'_direct_routine_modules',{}):
                raise BSLError('Имя импорта уже занято: '+name,node.token.source,node.token.line,node.token.column)


def record_exports(vm,program=(),*,facts=None):
    routines,variables=_PUBLIC.get(vm,({},frozenset()))
    routines=dict(routines);variables=set(variables)
    registry=getattr(vm,'_direct_routine_modules',{})
    if facts is not None:
        for key,exported in facts.routine_exports:
            routines.pop(key,None)
            if exported:
                module=registry[key];routines[key]=(id(module),module.signatures[key])
        variables.update(facts.variable_exports)
        _PUBLIC[vm]=(routines,frozenset(variables))
        return
    for node in program:
        if type(node) is ast.Routine:
            key=node.name.casefold();routines.pop(key,None)
            if node.exported:
                module=registry[key];routines[key]=(id(module),module.signatures[key])
        elif type(node) is ast.Var:variables.update(name.casefold() for name in node.exported_names)
    _PUBLIC[vm]=(routines,frozenset(variables))


def initialize(vm,program=(),*,facts=None):
    imports=([ast.Import(token,filename) for filename,token in facts.imports] if facts is not None
             else [node for node in program if type(node) is ast.Import])
    if not imports:return
    check_live(vm)
    preflight(vm,program,facts=facts)
    source=facts.source if facts is not None else program[0].token.source if program else '<строка>'
    path=None if source.startswith('<') else Path(source).resolve()
    if path is not None:vm._loading.append(path)
    try:
        for node in imports:
            try:Interpreter.semantic_import(vm,node)
            except BSLError:raise
            except Exception as error:
                raise BSLError(str(error),node.token.source,node.token.line,node.token.column) from None
            _SEALS[vm]=_tree(vm)
    finally:
        if path is not None:vm._loading.pop()


class ImportBoundary:
    def enter(self):
        self._imports_active=True;self._imports_epoch=object()
        try:return super().enter()
        except BaseException:
            self._imports_active=False
            raise

    def leave(self):
        self._imports_active=False
        return super().leave()

    def resolve_service(self,name,*args,**kwargs):
        if (self.vm.imports and ':' not in name and name.casefold() not in self.vm.functions
                and name.casefold() not in getattr(self.vm,'_direct_routine_modules',{})):
            self._check()
            raise ValueError('Переменная или функция не определена: '+name)
        return super().resolve_service(name,*args,**kwargs)

    def external_set(self,name,value):
        if name in self.vm.imports:raise ValueError('Нельзя присвоить значение имени импорта: '+name)
        return super().external_set(name,value)

    def _import_target(self,path):
        self._check();check_live(self.vm)
        if not getattr(self,'_imports_active',False):raise BoundaryViolation('import activation expired')
        if type(path) is not tuple or not path or any(type(k) is not str for k in path):
            raise BoundaryViolation('invalid import path')
        value=self.vm.imports.get(path[0])
        for key in path[1:]:
            if type(value) is not _Namespace:raise ValueError('Вложенное имя допустимо только для пространства каталога')
            value=value.members.get(key)
        if value is None:raise ValueError('Импортированное имя не найдено: '+'.'.join(path))
        return value

    def import_get(self,path):
        if len(path)<2:raise ValueError('Пространство импорта не является значением')
        owner=self._import_target(path[:-1])
        if type(owner) is not _Module:raise ValueError('Пространство импорта не является значением')
        child=owner.interpreter
        if path[-1] not in _PUBLIC[child][1]:raise ValueError('Поле объекта не обнаружено: '+path[-1])
        return child.variables[path[-1]]

    def resolve_import_write(self,path):
        self.import_get(path)
        owner=self._import_target(path[:-1]);child=owner.interpreter
        def write(value):
            self.import_get(path)
            if self._import_target(path[:-1]) is not owner:raise BoundaryViolation('import binding changed')
            child.variables[path[-1]]=value
        return write

    def import_reference(self,path):
        self.import_get(path)
        return Reference(lambda:self.import_get(path),self.resolve_import_write(path))

    def resolve_import_call(self,path,*,require_value,argument_count):
        if len(path)<2:raise ValueError('Пространство импорта не является функцией')
        owner=self._import_target(path[:-1])
        if type(owner) is not _Module:raise ValueError('Импортированное имя не является модулем')
        child=owner.interpreter;name=path[-1]
        public=_PUBLIC[child][0].get(name)
        if public is None:raise ValueError('Метод объекта не обнаружен: '+name)
        from .python_direct import _admit_vm
        from .python_direct_routines import validate_calls
        _admit_vm(child,_transaction_owner=getattr(self,'_direct_transaction_owner',None));validate_calls(child,(name,))
        module=child._direct_routine_modules[name]
        if name in module.dual_names:raise ValueError('Двухконтекстная подпрограмма через объект модуля пока не поддерживается')
        returns_value,minimum,maximum,references=public[1]
        if require_value and not returns_value:raise TypeError('Процедура не возвращает значение: '+name)
        if not minimum<=argument_count<=maximum:raise TypeError('Неверное количество аргументов: '+name)
        epoch=self._imports_epoch
        used=False
        def validate():
            self._check();check_live(self.vm);check_live(child)
            if (self._imports_epoch is not epoch or self._import_target(path[:-1]) is not owner
                    or _PUBLIC[child][0].get(name)!=public):
                raise BoundaryViolation('imported routine binding changed')
        def invoke(*args):
            nonlocal used
            validate();_admit_vm(child,_transaction_owner=getattr(self,'_direct_transaction_owner',None));validate_calls(child,(name,))
            if used:raise BoundaryViolation('import call already consumed')
            used=True
            from .python_direct import make_boundary
            from .python_direct_routines import resolve
            context=make_boundary(child,_parent_check=validate,_transaction_owner=getattr(self,'_direct_transaction_owner',None))
            context._handled_errors=self._handled_errors
            for attribute in ('_execute_depth','_eval_depth'):
                shared=getattr(self,attribute,None)
                if shared is None:
                    shared=[0];setattr(self,attribute,shared)
                setattr(context,attribute,shared)
            active=getattr(child,'_direct_active',False);child._direct_active=True
            try:
                context.enter()
                try:
                    function=resolve(context,name,require_value=require_value,allow_references=True,argument_count=argument_count)
                    return function(*args)
                finally:
                    try:validate()
                    finally:context.leave()
            finally:
                context.revoke()
                child._direct_active=active;context._routine_exports.clear()
        invoke.requires_reference=lambda index:index in references
        def omissions(bound,positions,count):
            validate()
            from .experimental_naked_collections import _OMITTED_REF
            return bound,{index:_OMITTED_REF for index in positions}
        invoke.prepare_omissions=omissions
        return invoke
