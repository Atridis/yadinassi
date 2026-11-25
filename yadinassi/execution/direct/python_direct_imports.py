"""Owned synchronous file imports; syntax-only namespaces, never host objects."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakKeyDictionary, ref

from yadinassi.syntax import ast
from yadinassi.runtime import (Interpreter, _Module, _Namespace,
                      _DIRECT_IMPORT_LOADER_ABI, _DIRECT_IMPORT_RECEIVER_ABI)
from yadinassi.types.values import Reference
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

_GRANTS=WeakKeyDictionary()
_SEALS=WeakKeyDictionary()
_PUBLIC=WeakKeyDictionary()
_LOADER_ABI=_DIRECT_IMPORT_LOADER_ABI
_CLASS_ABI=_DIRECT_IMPORT_RECEIVER_ABI
_MAX_MODULES=256
_MAX_DEPTH=64


def _receiver_hooks(classes):
    for cls,items,mro in classes:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(items) or any(current.get(k) is not v for k,v in items):
            raise BoundaryViolation('import receiver class hooks changed')


def _hooks(vm):
    if type(vm) is not Interpreter:raise BoundaryViolation('foreign import interpreter')
    if type(vm.imports) is not dict or type(vm._module_cache) is not dict or type(vm._loading) is not list:
        raise BoundaryViolation('custom import storage is not supported')
    _receiver_hooks(_CLASS_ABI)
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
    from yadinassi.syntax.lexer import KEYWORDS
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


def _module_declarations(program):
    """Declarations inside client module blocks share the import namespace."""
    pending=list(reversed(program))
    while pending:
        node=pending.pop()
        kind=type(node)
        if kind is ast.Var:
            yield tuple(name.casefold() for name in node.names),node.token
        elif kind is ast.Routine:
            yield (node.name.casefold(),),node.token
            # Routine locals and parameters have their own namespace.
        elif kind is ast.If:
            pending.extend(reversed(node.otherwise))
            for _,body in reversed(node.branches):
                pending.extend(reversed(body))
        elif kind is ast.Try:
            pending.extend(reversed(node.handler))
            pending.extend(reversed(node.body))
        elif kind in (ast.For,ast.ForEach,ast.While):
            pending.extend(reversed(node.body))


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
    names=import_names(vm,program)
    declarations=tuple(_module_declarations(program)) if names else ()
    imports=[]; routines=[]; variables=set(); roots=set()
    for node in program:
        if type(node) is ast.Import:
            imports.append((node.filename,node.token))
            roots.add(node.filename.split('.')[0].casefold())
        elif type(node) is ast.Routine:
            key=node.name.casefold()
            routines.append((key,node.exported))
        elif type(node) is ast.Var:
            variables.update(name.casefold() for name in node.exported_names)
    return PreparedImportFacts(tuple(imports),declarations,tuple(routines),
                               frozenset(variables),frozenset(roots),
                               program[0].token.source if program else '<строка>')


def _contract(vm):
    if any(type(value) is not str for value in (vm.native_target,vm.compilation_profile)):
        raise BoundaryViolation('invalid import execution contract')
    if type(vm._family_generation) is not int:raise BoundaryViolation('invalid import generation')
    if type(vm._module_cache) is not dict or type(vm._loading) is not list:
        raise BoundaryViolation('invalid import cache or loading stack')
    return (vm.native_target,vm.compilation_profile,id(vm.database_context),
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
    else:
        _GRANTS[child]=(*grant[:3],False,grant[4])
        if (getattr(child,'_direct_import_async',False)
                or any(module.async_names for module in
                       getattr(child,'_direct_routine_modules',{}).values())):
            parent._direct_import_async=True


def check_async_owner(child,root,*,published):
    # A task must not retain its transient caller lease. Its owning module
    # does retain the genuine import-grant chain for its entire lifetime.
    for _ in range(_MAX_DEPTH):
        grant=_GRANTS.get(child)
        if grant is None or grant[1]() is not root or not owned_child(child):
            break
        parent=grant[0]()
        if parent is None:break
        if published and (grant[3] or child._self_module.ready is not True):
            raise BoundaryViolation('async import is not published')
        check_live(parent)
        if parent is root:return
        child=parent
    raise BoundaryViolation('async import owner changed')


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


def _check_declarations(names,declarations):
    for declared,token in declarations:
        if any(name in names for name in declared):
            raise BSLError('Имя импорта конфликтует с объявлением',token.source,token.line,token.column)


def preflight(vm,program=(),*,facts=None):
    if facts is not None:
        if facts.imports:_hooks(vm)
        names=set(import_names(vm,facts=facts))
        if names:_check_declarations(names,facts.declarations)
        for filename,token in facts.imports:
            name=filename.split('.')[0].casefold()
            if name in vm.variables or name in vm.functions or name in getattr(vm,'_direct_routine_modules',{}):
                raise BSLError('Имя импорта уже занято: '+name,token.source,token.line,token.column)
        return
    if any(type(node) is ast.Import for node in program):_hooks(vm)
    names=set(import_names(vm,program))
    if names:_check_declarations(names,_module_declarations(program))
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
            from .python_direct_callback import CapturedRunCallback
            if args and type(args[0]) is CapturedRunCallback:
                return super().resolve_service(name,*args,**kwargs)
            if self._verify_context:self._check()
            raise ValueError('Переменная или функция не определена: '+name)
        return super().resolve_service(name,*args,**kwargs)

    def external_set(self,name,value):
        if name in self.vm.imports:raise ValueError('Нельзя присвоить значение имени импорта: '+name)
        return super().external_set(name,value)

    def _check_import_activation(self):
        # Namespace access carries an import lease even in the light mode.
        if self._verify_context:self._check()
        if (not getattr(self,'_imports_active',False) or self._revoked
                or self._epoch != self._admitted_epoch or self.vm._family_closed):
            raise BoundaryViolation('import activation expired')
        check_live(self.vm)

    def _import_target(self,path):
        self._check_import_activation()
        if type(path) is not tuple or not path or any(type(k) is not str for k in path):
            raise BoundaryViolation('invalid import path')
        value=self.vm.imports.get(path[0])
        for key in path[1:]:
            if type(value) is not _Namespace:raise ValueError('Вложенное имя допустимо только для пространства каталога')
            value=value.members.get(key)
        if value is None:raise ValueError('Импортированное имя не найдено: '+'.'.join(path))
        return value

    def _public_module(self,value,*,_lent=None):
        # This lane resolves only actual module values. Unrelated members do
        # not acquire a new context check, and no Python member is looked up.
        if _lent is None:self._check_effect()
        else:self._check(_lent=_lent)
        if not self._imports_active:raise BoundaryViolation('module activation ended')
        _receiver_hooks(_CLASS_ABI[:1])
        child=value.interpreter
        if (type(child) is not Interpreter or child._self_module is not value
                or child._family_owner is not self.vm._family_owner):
            raise BoundaryViolation('foreign module receiver')
        if child is not self.vm:
            self._check_import_activation()
            if not owned_child(child):raise BoundaryViolation('unavailable imported module receiver')
        if type(child.variables) is not dict or type(value.ready) is not bool:
            raise BoundaryViolation('module storage or readiness changed')
        return child

    def _public_field(self,value,name,*,_lent=None):
        child=self._public_module(value,_lent=_lent)
        if _lent is not None:
            # A later actual/callback can mutate the same dictionary without
            # replacing it. Check storage keys before any selected lookup.
            for stored in child.variables:
                if type(stored) is not str:raise BoundaryViolation('module field storage changed')
        key=name.casefold()
        public=_PUBLIC.get(child)
        if (not value.ready or key.startswith('_') or public is None or key not in public[1]
                or key not in child.variables):
            raise ValueError('Поле объекта не обнаружено: '+name)
        return child.variables,key

    def get_member(self,value,name):
        if type(value) is not _Module:return super().get_member(value,name)
        state,key=self._public_field(value,name)
        return state[key]

    def resolve_set_member(self,value,name):
        if type(value) is not _Module:return super().resolve_set_member(value,name)
        state,key=self._public_field(value,name)
        def write(new_value):
            live,_=self._public_field(value,name)
            if live is not state:raise BoundaryViolation('module field storage changed')
            state[key]=new_value
        return write

    def reference_member(self,value,name):
        if type(value) is not _Module:return super().reference_member(value,name)
        state,key=self._public_field(value,name)
        def address(lend=None):
            live,_=self._public_field(value,name,_lent=lend)
            if live is not state:raise BoundaryViolation('module field storage changed')
            return live
        def read():
            return address()[key]
        def write(new_value):
            address()[key]=new_value
        reference=Reference(read,write)
        if value is self.vm._self_module and getattr(self,'_check_lent_reference',False) is True:
            from .python_direct_lent_refs import remember
            def read_lent(lend):
                return address(lend)[key]
            def write_lent(value,lend):
                address(lend)[key]=value
                self._check(_lent=lend)
            remember(reference,self,read_lent,write_lent)
        return reference

    def resolve_member(self,value,name):
        if type(value) is _Module:
            self._public_module(value)
            raise ValueError('Метод объекта не обнаружен: '+name)
        return super().resolve_member(value,name)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if type(value) is not _Module:
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        if omitted:
            self._public_module(value)
            raise ValueError('Не поддерживаются пропущенные аргументы метода объекта модуля')
        return self.resolve_public_module_call(value,name,require_value=require_value,argument_count=None)

    def resolve_public_module_call(self,value,name,*,require_value,argument_count,local_omissions=False):
        if type(value) is not _Module:
            # A local declaration or an embedding-provided value can shadow
            # the name. Preserve its ordinary member lane, not a module grant.
            call=self.resolve_member_call(value,name,require_value=require_value)
            def ordinary(*actuals):return call(*actuals)
            ordinary.requires_reference=lambda index:False
            return ordinary
        child=self._public_module(value)
        key=name.casefold()
        if not value.ready or key.startswith('_'):
            raise ValueError('Метод объекта не обнаружен: '+name)
        return self._resolve_public_call(value,key,require_value=require_value,
                                         argument_count=argument_count,path=None,local_omissions=local_omissions)

    def import_callback_module(self,path):
        """Expose an owned module only in a canonical callback target slot."""
        owner=self._import_target(path)
        if type(owner) is not _Module:
            raise ValueError('Пространство импорта не является модулем оповещения')
        return owner

    def resolve_callback_target(self,target,name,*,require_value,argument_count,reusable=False):
        path=None
        if type(target) is str:
            # Lookup only existing canonical namespace bindings; never load a
            # path or resolve a configuration manager from a handler string.
            path=tuple(part.casefold() for part in target.split('.'))
            if not all(path):
                raise ValueError('Модуль оповещения не импортирован: '+target)
            try:target=self.import_callback_module(path)
            except ValueError:
                raise ValueError('Модуль оповещения не импортирован: '+target) from None
        if type(target) is not _Module:
            raise ValueError('ОписаниеОповещения: ожидается объект текущего модуля или импортированного модуля (не другого интерпретатора)')
        _receiver_hooks(_CLASS_ABI[:1])
        child=target.interpreter
        if type(child) is not Interpreter or child._family_owner is not self.vm._family_owner:
            raise ValueError('Модуль оповещения другого интерпретатора')
        if child is self.vm._family_owner and child is not self.vm:
            raise ValueError('Модуль оповещения не импортирован текущим модулем')
        self._public_module(target)
        if not target.ready or name.startswith('_'):
            raise ValueError('Метод объекта не обнаружен: '+name)
        return self._resolve_public_call(target,name.casefold(),require_value=require_value,
                                         argument_count=argument_count,path=path,
                                         callback_only=True,reusable=reusable)

    def _split_import(self,path):
        """Locate the module without treating its exported data as namespaces."""
        self._check_import_activation()
        if type(path) is not tuple or not path or any(type(key) is not str for key in path):
            raise BoundaryViolation('invalid import path')
        value=self.vm.imports.get(path[0])
        index=1
        while type(value) is _Namespace and index<len(path):
            value=value.members.get(path[index])
            index+=1
        if value is None:raise ValueError('Импортированное имя не найдено: '+'.'.join(path[:index]))
        if type(value) is not _Module or index==len(path):
            raise ValueError('Пространство импорта не является значением')
        return value,path[:index],path[index:]

    def _import_field(self,owner,key):
        child=owner.interpreter
        if type(child.variables) is not dict:raise BoundaryViolation('imported module storage changed')
        if key not in _PUBLIC[child][1] or key not in child.variables:
            raise ValueError('Поле объекта не обнаружено: '+key)
        return child.variables[key]

    def _import_data_receiver(self,owner,names):
        value=self._import_field(owner,names[0])
        for key in names[1:]:
            value=self._import_data_get(value,key)
        return value

    def _import_data_get(self,value,name):
        from yadinassi.execution.codegen.direct_structure import _DirectStructure,structure_get
        from yadinassi.collections.plain_value_list import PlainValueList,PlainValueListItem,_field
        if type(value) is _DirectStructure:return structure_get(value,name)
        if type(value) is PlainValueList:
            from .python_direct_database import _PLAIN_VALUE_LIST_DEFAULT_PROPERTIES
            if name.casefold() in _PLAIN_VALUE_LIST_DEFAULT_PROPERTIES:
                return self.get_member(value,name)
            raise ValueError('Поле объекта не обнаружено: '+name)
        if name.startswith('_') or type(value) is list:
            raise ValueError('Поле объекта не обнаружено: '+name)
        if type(value) is PlainValueListItem:return list.__getitem__(value,_field(name))
        return self.get_member(value,name)

    def _import_data_check(self,owner,prefix):
        # A bound member retains its already evaluated data receiver. Recheck
        # just this namespace path, not every import or stored data entry.
        epoch=self._imports_epoch
        child=owner.interpreter
        def check():
            self._check_effect()
            _receiver_hooks(_CLASS_ABI)
            if (not self._imports_active or self._imports_epoch is not epoch
                    or owner.ready is not True or owner.interpreter is not child or child._self_module is not owner
                    or child._family_released or child._family_owner is not self.vm._family_owner
                    or child._family_generation!=self.vm._family_generation or type(self.vm.imports) is not dict):
                raise BoundaryViolation('imported data owner changed')
            value=self.vm.imports.get(prefix[0])
            for key in prefix[1:]:
                if type(value) is not _Namespace or type(value.members) is not dict:
                    raise BoundaryViolation('imported data namespace changed')
                value=value.members.get(key)
            if value is not owner:raise BoundaryViolation('imported data binding changed')
        return check

    def import_get(self,path):
        owner,_,names=self._split_import(path)
        return self._import_data_receiver(owner,names)

    def _import_data_setter(self,value,name):
        from yadinassi.execution.codegen.direct_structure import _DirectStructure,structure_set_known
        from yadinassi.collections.plain_value_list import PlainValueListItem,_field,_ITEM_NORMALIZERS
        if type(value) is _DirectStructure:return lambda item:structure_set_known(value,name,name,item)
        if name.startswith('_'):raise ValueError('Поле объекта не обнаружено: '+name)
        if type(value) is PlainValueListItem:
            field=_field(name)
            normalizer=_ITEM_NORMALIZERS.get(field)
            if normalizer is not None:
                return lambda item:list.__setitem__(value,field,normalizer(item))
            return lambda item:list.__setitem__(value,field,item)
        return self.resolve_set_member(value,name)

    def _import_slot(self,path,*,for_reference=False):
        owner,prefix,names=self._split_import(path)
        check=self._import_data_check(owner,prefix)
        name=names[-1]
        if len(names)==1:
            child=owner.interpreter
            self._import_field(owner,name)
            state=child.variables
            def read():
                check()
                if child.variables is not state:raise BoundaryViolation('imported field storage changed')
                return self._import_field(owner,name)
            def write(value):
                read()
                state[name]=value
            return read,write
        receiver=self._import_data_receiver(owner,names[:-1])
        writer=None if for_reference else self._import_data_setter(receiver,name)
        def read():
            check()
            return self._import_data_get(receiver,name)
        def write(value):
            check()
            try:
                setter=self._import_data_setter(receiver,name) if writer is None else writer
                return setter(value)
            finally:check()
        return read,write

    def resolve_import_write(self,path):
        return self._import_slot(path)[1]

    def import_reference(self,path):
        read,write=self._import_slot(path,for_reference=True)
        read()
        return Reference(read,write)

    def link_import_call(self,path,*,require_value,argument_count):
        """Bind a context-free export for this generated standalone activation."""
        vm=self.vm
        if getattr(self,'_async_scheduler',None) is not None:return None
        if (vm.allow_extensions or vm._family_owner.__dict__.get('_standalone_script') is not True
                or getattr(self,'_server_side',False)
                or getattr(self,'module_context',True) is False):
            return None
        if len(path)<2:return None
        owner,_,names=self._split_import(path)
        if len(names)!=1:return None
        child=owner.interpreter;name=names[0]
        public=_PUBLIC[child][0].get(name)
        if public is None:return None
        module=child._direct_routine_modules[name]
        returns_value,_,maximum,references=public[1]
        if (references or argument_count!=maximum or not returns_value
                or name in module.server_names or name in module.dual_names):
            return None
        from .python_direct import _admit_vm
        from .python_direct_routines import validate_calls
        _admit_vm(child,_transaction_owner=self._direct_transaction_owner)
        validate_calls(child,(name,))
        # Constructing exports in bind-only mode does not execute module source.
        # An export closing over state, a context, or other routines still needs
        # the complete import protocol. Constants alone are parser-owned values.
        exports=self._routine_exports.get((child,id(module)))
        if exports is None:
            exports=module.plan.function(child.variables,module.plan.constants,[],None,True)
            self._routine_exports[child,id(module)]=exports
        function=exports[name]
        if set(function.__code__.co_freevars)-{'_constants'}:return None
        from yadinassi.execution.codegen.direct_errors import convert_error
        def linked(*args):
            try:return function(*args)
            except Exception as error:
                converted=convert_error(error,module.plan.source_name,module.plan.source_text)
                if converted is error:raise
                raise converted from None
        return linked

    def resolve_import_call(self,path,*,require_value,argument_count,omitted=()):
        owner,prefix,names=self._split_import(path)
        if len(names)==1:
            return self._resolve_public_call(owner,names[0],require_value=require_value,
                                             argument_count=argument_count,path=prefix,local_omissions=bool(omitted))
        receiver=self._import_data_receiver(owner,names[:-1])
        name=names[-1]
        if name.startswith('_'):raise ValueError('Метод объекта не обнаружен: '+name)
        from .python_direct_import_collections import bind
        function=bind(receiver,name,argument_count,omitted,require_value)
        if function is None:
            from .python_direct_database import _CALL_TABLE,_CALL_COLUMNS,_CALL_ROW
            if not any(type(receiver) is cls for cls in (_CALL_TABLE,_CALL_COLUMNS,_CALL_ROW)):
                raise ValueError('Метод объекта не обнаружен: '+name)
            function=self.resolve_member_call(receiver,name,require_value=require_value,omitted=omitted)
        check=self._import_data_check(owner,prefix)
        def invoke(*values):
            check()
            try:return function(*values)
            finally:check()
        invoke.requires_reference=lambda index:False
        if omitted:
            # Existing bounded collection resolvers own their per-slot defaults.
            invoke.prepare_omissions=lambda bound,positions,count:(bound,dict.fromkeys(positions,None))
        return invoke

    def _resolve_public_call(self,owner,name,*,require_value,argument_count,path,
                             callback_only=False,reusable=False,local_omissions=False):
        child=owner.interpreter
        exports=_PUBLIC.get(child)
        public=None if exports is None else exports[0].get(name)
        if public is None:raise ValueError('Метод объекта не обнаружен: '+name)
        from .python_direct import _admit_vm
        from .python_direct_routines import validate_calls, resolve
        local=path is None and child is self.vm
        async_guard=None
        async_task=getattr(self,'_async_task',False)
        if not local:
            if getattr(self,'_async_scheduler',None) is not None:
                from .python_direct_async import import_guard
                async_guard=import_guard(self,child)
            _admit_vm(child,_transaction_owner=getattr(self,'_direct_transaction_owner',None),
                      _async_guard=async_guard)
        validate_calls(child,(name,))
        module=child._direct_routine_modules.get(name)
        if id(module)!=public[0] or module.signatures.get(name) is not public[1]:
            raise BoundaryViolation('module routine declaration changed')
        if name in module.async_names:
            if callback_only:
                raise ValueError('Асинхронный обработчик обратного вызова пока не поддерживается')
            if getattr(self,'_async_scheduler',None) is None:
                raise ValueError('Асинхронный импорт требует активного клиентского запуска')
        if name in module.dual_names or ((path is None or callback_only) and name in module.server_names):
            raise ValueError('Двухконтекстная подпрограмма через объект модуля пока не поддерживается')
        returns_value,minimum,maximum,references=public[1]
        if async_task and name in module.server_names and (
                local or path is None or name not in module.nocontext_names or references):
            raise ValueError('Серверный вызов из асинхронного задания пока не поддерживается')
        if require_value and not returns_value:raise TypeError('Процедура не возвращает значение: '+name)
        if argument_count is not None and not minimum<=argument_count<=maximum:
            raise TypeError('Неверное количество аргументов: '+name)
        if argument_count is None and references:
            raise ValueError('Ожидается явный вызов метода модуля с параметрами без Знач')
        epoch=self._imports_epoch
        used=False
        def validate():
            if path is None:
                if self._public_module(owner) is not child or not owner.ready:
                    raise BoundaryViolation('module routine receiver changed')
            else:
                if self._verify_context:self._check()
                check_live(child)
                if self._import_target(path) is not owner:raise BoundaryViolation('import binding changed')
            current=_PUBLIC.get(child)
            if (self._imports_epoch is not epoch or current is None or current[0].get(name) is not public
                    or child._direct_routine_modules.get(name) is not module):
                raise BoundaryViolation('module routine binding changed')
        def invoke(*args):
            nonlocal used
            validate()
            if not minimum<=len(args)<=maximum:raise TypeError('Неверное количество аргументов: '+name)
            if used and not reusable:raise BoundaryViolation('module call already consumed')
            used=True
            if local:
                function=resolve(self,name,require_value=require_value,allow_references=True,argument_count=len(args),local_omissions=local_omissions)
                try:return function(*args)
                finally:validate()
            _admit_vm(child,_transaction_owner=getattr(self,'_direct_transaction_owner',None),
                      _async_guard=async_guard);validate_calls(child,(name,))
            from .python_direct import make_boundary
            context=make_boundary(child,_parent_check=validate,
                                  _transaction_owner=getattr(self,'_direct_transaction_owner',None),
                                  _async_guard=async_guard)
            if async_task:
                context._async_task=True
                if path is not None and name in module.nocontext_names and not references:
                    context._async_import_nocontext=name
            if (not self._verify_context and not child.allow_extensions
                    and self.policy is None and child.database_context is None
                    and child._family_owner is self.vm._family_owner
                    and name not in module.server_names):
                # Entry/exit pin the parent lease; effects revalidate it.
                context._verify_context=False
                context._verify_dynamic_context=False
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
                    function=resolve(context,name,require_value=require_value,allow_references=True,argument_count=len(args),local_omissions=local_omissions)
                    return function(*args)
                finally:
                    try:validate()
                    finally:context.leave()
            finally:
                context.revoke()
                child._direct_active=active;context._routine_exports.clear()
        if reusable:invoke.check_binding=validate
        invoke.requires_reference=lambda index:index in references
        def omissions(bound,positions,count):
            validate()
            if name in module.server_names:
                # Local exported defaults use the generated routine marker;
                # the client/server transfer must not see that private value.
                raise TypeError('omitted imported server routine argument is unsupported')
            from yadinassi.execution.codegen.direct_collections import _OMITTED_REF
            return bound,{index:_OMITTED_REF for index in positions}
        invoke.prepare_omissions=omissions
        return invoke
