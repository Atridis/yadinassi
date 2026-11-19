"""Finite synchronous client command → qualified by-value scalar routine lane.

No general Interpreter admission change; no cache, session, global-module,
transport, database or legacy execution is provided here.
"""
from decimal import Decimal, localcontext
from types import MethodType
from threading import get_ident
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from .python_direct import REPAIRS, _snapshot, PythonDirectUnsupported
from .python_direct_configuration import ConfigurationBoundary, _COMMAND_SCOPE, check_owner, parameter_snapshot, parameter_entries
from yadinassi.execution.codegen.native_targets import target_context
from yadinassi.runtime import Interpreter, _Module, _DIRECT_CONFIGURATION_MESSAGE_ABI, _DIRECT_EXECUTION_SCOPE_ABI
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.types.values import HostFunction
from . import python_direct_configuration_metadata as metadata
from yadinassi.types.errors import BSLRuntimeError

_MESSAGE = _DIRECT_CONFIGURATION_MESSAGE_ABI


def _deny():
    raise BoundaryViolation('direct configuration command requires synchronous client by-value scalar modules')


def _unsupported():
    raise PythonDirectUnsupported('direct configuration commands support only client scalar modules with Val parameters and scalar literal defaults')


class _Scope:
    def __init__(self,app,*,starting=False):
        from yadinassi.configuration.configuration_runtime import ConfigurationApplication
        if type(app) is not ConfigurationApplication:_deny()
        from yadinassi.configuration.configuration_xml import ConfigurationImport
        if type(app.configuration) is not ConfigurationImport:_deny()
        self.configuration=app.configuration
        if type(self.configuration.common_modules) is not tuple:_deny()
        self.definition_list=self.configuration.common_modules
        root=app.interpreter
        if type(root) is not Interpreter:_deny()
        self.app,self.root=app,root
        self.expected_state='starting' if starting else 'running'
        if starting and app._cli_database is None:_deny()
        self.thread=get_ident()
        self.active=False
        self.token=None
        if type(app._modules) is not dict or type(app._definitions) is not dict:_deny()
        self.modules=()
        self.definitions=()
        self.owners=()
        self.plans=()
        self.functions=()
        self.parameters=()
        self.owner_records={}
        self.used_routines={}
        self._metadata=None
        self._reuse_request=None
        self.module_bindings={}
        self._admit_owner(root)
        self._check_state(app,root)

    @property
    def metadata(self):
        if self._metadata is None:self._metadata=metadata.Readers(self)
        return self._metadata

    def _admit_owner(self,owner):
        if any(owner is current for current in self.owners):return
        if type(owner) is not Interpreter or type(owner.routines) is not dict:_deny()
        plan=owner._direct_configuration_plan
        self.owners+=(owner,)
        self.plans+=(plan,)
        self.functions+=(plan.function,)
        self.parameters+=(parameter_snapshot(plan),)
        self.owner_records[id(owner)]=(owner,plan,plan.function,parameter_snapshot(plan))
        self.used_routines[id(owner)]={}

    def admit_module(self,name,module):
        self.check(self.app,self.root)
        key=name.casefold()
        definition=self.app._definitions.get(key)
        prior=self.module_bindings.get(id(module))
        if definition is None:_deny()
        if prior is None and not any(definition is entry for entry in self.definition_list):_deny()
        if prior is not None and (prior[0]!=(key,'client') or prior[1] is not module):_deny()
        if metadata.validate_definition(definition)[0].casefold()!=key:_deny()
        if (not definition.client or definition.server or definition.server_call
                or definition.global_module or definition.return_values_reuse not in ('DontUse','DuringRequest','DuringSession')):_unsupported()
        if (type(module) is not _Module or self.app._modules.get((key,'client')) is not module
                or type(module.interpreter) is not Interpreter or module.interpreter._self_module is not module):_deny()
        if not any(saved is module for _,saved in self.modules):
            self.modules+=(((key,'client'),module),)
            self.definitions+=((key,definition),)
            self._admit_owner(module.interpreter)
        self.module_bindings[id(module)]=((key,'client'),module)
        self._check_state(self.app,module.interpreter)

    @staticmethod
    def values(values):
        for value in values:
            if not any(type(value) is kind for kind in (type(None),bool,str,Decimal)):_deny()

    def enter(self):
        if get_ident()!=self.thread or self.active or _COMMAND_SCOPE.get() is not None:_deny()
        self._check_state(self.app,self.root)
        self.token=_COMMAND_SCOPE.set(self)
        self.active=True

    def request_reuse(self):
        self.check(self.app,self.root)
        if self._reuse_request is None:
            from .source.python_direct_source_requests import request_scope
            request=request_scope(self.root)
            request.__enter__()
            self._reuse_request=request

    def leave(self):
        if get_ident()!=self.thread or not self.active:_deny()
        _COMMAND_SCOPE.reset(self.token)
        self.active=False
        self.token=None
        if self._reuse_request is not None:
            request=self._reuse_request;self._reuse_request=None
            request.__exit__(None,None,None)

    def check(self,app,owner):
        if get_ident()!=self.thread or not self.active or _COMMAND_SCOPE.get() is not self:_deny()
        # A copied Context retains ContextVar values, but cannot reset the
        # origin Context's token. Rotate the token synchronously to validate
        # exact Context identity without executing foreign code or yielding.
        try:_COMMAND_SCOPE.reset(self.token)
        except (ValueError,RuntimeError):_deny()
        self.token=_COMMAND_SCOPE.set(self)
        self._check_state(app,owner)

    def _check_state(self,app,owner):
        if app is not self.app or not any(owner is item for item in self.owners):_deny()
        root=self.root
        if app.configuration is not self.configuration or self.configuration.common_modules is not self.definition_list:_deny()
        if (app.interpreter is not root or app.state!=self.expected_state or app.side not in (None,'client')
                or root.execution_context!='client' or root.locals is not None
):_deny()
        if type(app._modules) is not dict or type(app._definitions) is not dict:_deny()
        for key,module in self.modules:
            if app._modules.get(key) is not module or module.interpreter._self_module is not module:_deny()
        for name,definition in self.definitions:
            if metadata.validate_definition(definition)[0].casefold()!=name:_deny()
            if (app._definitions.get(name) is not definition or not definition.client
                    or definition.server or definition.server_call or definition.global_module
                    or definition.return_values_reuse not in ('DontUse','DuringRequest','DuringSession')):_deny()
        record=self.owner_records.get(id(owner))
        if record is None or record[0] is not owner:_deny()
        current,plan,code,parameters=record
        check_owner(app,current,allow_database=True)
        if (type(current.variables) is not dict or type(current.functions) is not dict
                or any(type(key) is not str for key in current.variables)):_deny()
        # Direct generated variable loads currently bypass a per-name boundary.
        # Retain scalar admission for this active owner until that compiler
        # interface can validate only actually read/written values.
        self.values(current.variables.values())
        if (current.execution_context!='client'
                or current._direct_configuration_plan is not plan or plan.function is not code
                or type(current.routines) is not dict
                or parameter_snapshot(plan) is not parameters):_deny()
        for routine in tuple(self.used_routines[id(owner)].values()):
            self.parameter_values(owner,routine)

    def parameter_values(self,owner,routine):
        if (type(routine) is not ast.Routine or type(routine.name) is not str
                or type(routine.parameters) is not list
                or any(type(p) is not ast.Parameter or type(p.name) is not str or type(p.by_value) is not bool for p in routine.parameters)):_deny()
        if type(owner._invocation_bindings) is not dict:_deny()
        if owner._invocation_bindings.get(routine.name.casefold()) is not None:_deny()
        if (routine.is_async or routine.is_dual or routine.execution_context!='client'
                or any(not p.by_value for p in routine.parameters)):_unsupported()
        record=self.owner_records.get(id(owner))
        if record is None or record[0] is not owner:_deny()
        if owner.routines.get(routine.name.casefold()) is not routine:_deny()
        entries=parameter_entries(record[1],routine)
        if len(entries)!=len(routine.parameters):_deny()
        self.used_routines[id(owner)][id(routine)]=routine
        for current,(saved,name,by_value,node,value) in zip(routine.parameters,entries):
            if (current is not saved or current.name is not name or current.by_value is not by_value
                    or current.default is not node):_deny()
            if node is not None:
                if type(node) is not ast.Literal:_unsupported()
                if node.value is not value:_deny()
                self.values((value,))
        return entries

    def omissions(self,owner,routine,omitted):
        entries=self.parameter_values(owner,routine)
        if type(omitted) is not tuple or any(type(i) is not int for i in omitted):_deny()
        if any(i<0 or i>=len(entries) for i in omitted):
            raise TypeError('common-module omission outside parameter list')

    def arguments(self,owner,routine,args,omitted):
        entries=self.parameter_values(owner,routine);self.omissions(owner,routine,omitted)
        if len(args)>len(entries):raise TypeError('common-module argument count mismatch')
        values=list(args)
        for index in omitted:
            if index>=len(values):raise TypeError('common-module omission outside argument list')
            values[index]=entries[index][4]
        for _,_,_,node,value in entries[len(values):]:
            if node is None:raise TypeError('required common-module argument missing')
            values.append(value)
        self.values(values)
        return tuple(values)

    def service(self,function,owner):
        # Message is the only host capability newly exposed by this lane.
        # Its existing owner/configuration host-service checks remain active.
        if type(function) is not HostFunction or type(function.name) is not str:_deny()
        method=function.function
        if (type(method) is not MethodType
                or method.__func__ is not _MESSAGE or method.__self__ is not owner
                or type(function.reference_parameters) is not frozenset or function.reference_parameters):_deny()


def _validate_command(program,app):
    referenced=set()
    def readonly(token,message='metadata is read-only'):
        raise BSLRuntimeError(message,token.source,token.line,token.column,source_line=token.source_line)
    def reader_kind(node):
        kind=type(node)
        if kind is ast.Name and node.name.casefold() in metadata.ROOT_NAMES:return 'root'
        if kind is ast.Group:return reader_kind(node.expression)
        if kind is ast.Attribute:
            parent=reader_kind(node.object);key=node.name.casefold()
            if parent=='root' and key in metadata.COLLECTION_NAMES:return 'collection'
            if parent=='collection':return 'item'
            if parent=='item' and key in metadata.SCALAR_FIELDS:return 'scalar'
            if parent is not None:_unsupported()
        if kind is ast.Index and reader_kind(node.object)=='collection':
            expression(node.index);return 'item'
        if kind is ast.Call:
            callee=node.callee
            while type(callee) is ast.Group:callee=callee.expression
            if type(callee) is ast.Attribute:
                parent=reader_kind(callee.object);key=callee.name.casefold()
                if parent=='collection' and key in metadata.COUNT:result,count='scalar',0
                elif parent=='collection' and key in metadata.FIND+metadata.GET:result,count='item',1
                elif parent=='item' and key in metadata.FULLNAME:result,count='scalar',0
                elif parent is not None:_unsupported()
                else:return None
                if len(node.arguments)!=count:_unsupported()
                for argument in node.arguments:expression(argument)
                return result
        return None
    def expression(node):
        reader=reader_kind(node)
        if reader=='scalar':return
        if reader is not None:_unsupported()
        kind=type(node)
        if kind is ast.Literal:_Scope.values((node.value,));return
        if kind is ast.Name:
            if node.name.casefold() in app._definitions:_unsupported()
            return
        if kind is ast.Group:expression(node.expression);return
        if kind is ast.Unary:expression(node.operand);return
        if kind is ast.Binary:expression(node.left);expression(node.right);return
        if kind is ast.Call:
            callee=node.callee
            while type(callee) is ast.Group:callee=callee.expression
            if type(callee) is ast.Attribute and type(callee.object) is ast.Name:
                if callee.object.name.casefold() not in app._definitions:_unsupported()
                referenced.add(callee.object.name.casefold())
            elif type(callee) is ast.Name:
                if callee.name.casefold() not in ('message','сообщить'):_unsupported()
            else:_unsupported()
            for argument in node.arguments:
                if type(argument) is ast.OmittedArgument and type(callee) is ast.Attribute:continue
                expression(argument)
            return
        _unsupported()
    def statements(nodes):
        for node in nodes:
            if type(node) is ast.Assign and type(node.target) is ast.Name:
                if node.target.name.casefold() in metadata.ROOT_NAMES:readonly(node.token)
                try:app.check_assignment(node.target.name.casefold(),app.interpreter)
                except ValueError as error:readonly(node.token,str(error))
                expression(node.value)
            elif type(node) is ast.Assign and reader_kind(node.target) is not None:readonly(node.token)
            elif type(node) is ast.ExpressionStatement:expression(node.expression)
            elif type(node) is ast.If:
                # Validate every condition/body before lowering, even branches
                # which will not run. Execution retains direct truth semantics.
                for condition,body in node.branches:
                    expression(condition);statements(body)
                statements(node.otherwise)
            elif type(node) is ast.Try:
                # Validate both branches before any effect, even unreachable
                # handlers. Execution uses the existing typed error lowering,
                # which never catches fail-closed BoundaryViolation.
                statements(node.body);statements(node.handler)
            elif type(node) is ast.Raise:
                if node.optional_arguments:_unsupported()
                if node.value is not None:expression(node.value)
            else:_unsupported()
    statements(program)
    return tuple(referenced)


def execute_command(app,text,source):
    program=parse(text,source,compilation_profile=app.interpreter.compilation_profile)
    return _execute_program(app,program,text,source)


def run_cli_initializer(app,program,text):
    return _execute_program(app,program,text,'<configuration:Ext/ManagedApplicationModule.bsl>',starting=True)


def _execute_program(app,program,text,source,*,starting=False):
    if _COMMAND_SCOPE.get() is not None or getattr(app.interpreter,'_direct_active',False):_deny()
    scope=_Scope(app,starting=starting)
    app.check_program(program);referenced=_validate_command(program,app)
    plan=compile_owned(_snapshot(program),source_text=text,source_name=source,
        external_names=referenced+metadata.ROOT_NAMES,authority_checks=True,configuration_calls=True,
        lean_configuration=app._cli_database is not None)
    owner=app.interpreter
    previous=getattr(owner,"_transaction_activation_allowed",True)
    with _DIRECT_EXECUTION_SCOPE_ABI(owner):
        scope.enter()
        owner._transaction_activation_allowed=False
        owner._direct_active=True
        try:
            context=ConfigurationBoundary(app,owner)
            with target_context(owner.native_target),localcontext():
                result=plan.run(owner.variables,context=context)
                scope.check(app,owner)
                if not program or type(program[-1]) is not ast.ExpressionStatement:return None
                scope.values((result,));return result
        finally:
            owner._direct_active=False
            owner._transaction_activation_allowed=previous
            scope.leave()
