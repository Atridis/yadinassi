"""Finite synchronous client command → qualified by-value scalar routine lane.

No general Interpreter admission change; no cache, session, global-module,
transport, database or legacy execution is provided here.
"""
from decimal import Decimal, localcontext
from types import MethodType
from threading import get_ident
from .experimental_naked_boundaries import BoundaryViolation
from .experimental_naked_collections import prepare
from .python_direct import REPAIRS, _snapshot, PythonDirectUnsupported
from .python_direct_configuration import ConfigurationBoundary, _COMMAND_SCOPE, check_owner
from .native_targets import target_context
from .runtime import Interpreter, _Module, _DIRECT_CONFIGURATION_MESSAGE_ABI
from .syntax import ast
from .syntax.parser import parse
from .values import HostFunction
from . import python_direct_configuration_metadata as metadata
from .errors import BSLRuntimeError

_MESSAGE = _DIRECT_CONFIGURATION_MESSAGE_ABI


def _deny():
    raise BoundaryViolation('direct configuration command requires synchronous client by-value scalar modules')


def _unsupported():
    raise PythonDirectUnsupported('direct configuration commands support only noDB client scalar modules with Val parameters and no defaults')


class _Scope:
    def __init__(self,app):
        from .configuration_runtime import ConfigurationApplication
        if type(app) is not ConfigurationApplication:_deny()
        from .configuration_xml import ConfigurationImport
        if type(app.configuration) is not ConfigurationImport:_deny()
        self.configuration=app.configuration
        if type(self.configuration.common_modules) is not tuple:_deny()
        self.definition_list=self.configuration.common_modules
        root=app.interpreter
        if type(root) is not Interpreter:_deny()
        self.app,self.root=app,root
        self.thread=get_ident()
        self.active=False
        self.token=None
        if type(app._modules) is not dict or type(app._definitions) is not dict:_deny()
        self.modules=tuple(dict.items(app._modules))
        self.definitions=tuple(dict.items(app._definitions))
        for key,_ in self.modules:
            if type(key) is not tuple or len(key)!=2 or any(type(part) is not str for part in key):_deny()
        for name,definition in self.definitions:
            if type(name) is not str or not any(definition is entry for entry in app.configuration.common_modules):_deny()
        if (app.side not in (None,'client') or root.execution_context!='client'
                or app._session_program or app.configuration.session_parameters
                or app._server_exchange is not None or app._global_names):_unsupported()
        for name,definition in self.definitions:
            if metadata.validate_definition(definition)[0].casefold()!=name:_deny()
            if (not definition.client or definition.server or definition.server_call
                    or definition.global_module or definition.return_values_reuse!='DontUse'):_unsupported()
        owners=[root]
        for (name,side),module in self.modules:
            if side!='client':_unsupported()
            if type(module) is not _Module:_deny()
            owner=module.interpreter
            if type(owner) is not Interpreter or owner._self_module is not module:_deny()
            owners.append(owner)
        for owner in owners:
            if owner.database_context is not None:_unsupported()
            if type(owner.routines) is not dict:_deny()
            for key,routine in dict.items(owner.routines):
                if (type(key) is not str or type(routine) is not ast.Routine
                        or type(routine.parameters) is not list
                        or any(type(p) is not ast.Parameter for p in routine.parameters)):_deny()
                if (routine.is_async or routine.is_dual or
                        any(not p.by_value or p.default is not None for p in routine.parameters)):_unsupported()
        self.owners=tuple(owners)
        self.plans=tuple(owner._direct_configuration_plan for owner in owners)
        self.functions=tuple(plan.function for plan in self.plans)
        self.routines=tuple(tuple(owner.routines.items()) for owner in owners)
        self._check_state(app,root)
        self.metadata=metadata.Readers(self)

    @staticmethod
    def values(values):
        for value in values:
            if not any(type(value) is kind for kind in (type(None),bool,str,Decimal)):_deny()

    def enter(self):
        if get_ident()!=self.thread or self.active or _COMMAND_SCOPE.get() is not None:_deny()
        self._check_state(self.app,self.root)
        self.token=_COMMAND_SCOPE.set(self)
        self.active=True

    def leave(self):
        if get_ident()!=self.thread or not self.active:_deny()
        _COMMAND_SCOPE.reset(self.token)
        self.active=False
        self.token=None

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
        if (app.interpreter is not root or app.state!='running' or app.side not in (None,'client')
                or root.execution_context!='client' or root.locals is not None
                or app._session_program or app.configuration.session_parameters
                or app._server_exchange is not None or app._global_names):_deny()
        if type(app._modules) is not dict or type(app._definitions) is not dict:_deny()
        if len(app._modules)!=len(self.modules) or len(app._definitions)!=len(self.definitions):_deny()
        for key,module in self.modules:
            if app._modules.get(key) is not module or module.interpreter._self_module is not module:_deny()
        for name,definition in self.definitions:
            if metadata.validate_definition(definition)[0].casefold()!=name:_deny()
            if (app._definitions.get(name) is not definition or not definition.client
                    or definition.server or definition.server_call or definition.global_module
                    or definition.return_values_reuse!='DontUse'):_deny()
        for current,plan,code,routines in zip(self.owners,self.plans,self.functions,self.routines):
            check_owner(app,current)
            if (type(current.variables) is not dict or type(current.functions) is not dict
                    or any(type(key) is not str for key in current.variables)):_deny()
            self.values(current.variables.values())
            for key,function in dict.items(current.functions):
                if (type(key) is not str or type(function) is not HostFunction
                        or type(function.name) is not str):_deny()
            if (current.database_context is not None or current.execution_context!='client'
                    or current._invocation_bindings or current.server_routines
                    or current._direct_configuration_plan is not plan or plan.function is not code
                    or type(current.routines) is not dict or len(current.routines)!=len(routines)):_deny()
            for key,routine in routines:
                if (current.routines.get(key) is not routine or type(routine) is not ast.Routine
                        or routine.is_async or routine.is_dual or routine.execution_context!='client'
                        or type(routine.parameters) is not list
                        or any(type(p) is not ast.Parameter or not p.by_value or p.default is not None for p in routine.parameters)):_deny()
        if type(root.variables) is not dict or any(type(key) is not str for key in root.variables):_deny()
        self.values(root.variables.values())

    def service(self,function,owner):
        # Message is the only host capability newly exposed by this lane.
        # Its existing owner/configuration host-service checks remain active.
        if type(function) is not HostFunction or type(function.name) is not str:_deny()
        method=function.function
        if (type(method) is not MethodType
                or method.__func__ is not _MESSAGE or method.__self__ is not owner
                or type(function.reference_parameters) is not frozenset or function.reference_parameters):_deny()


def _validate_command(program,app):
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
            elif type(callee) is ast.Name:
                if callee.name.casefold() not in ('message','сообщить'):_unsupported()
            else:_unsupported()
            for argument in node.arguments:expression(argument)
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


def execute_command(app,text,source):
    if _COMMAND_SCOPE.get() is not None or getattr(app.interpreter,'_direct_active',False):_deny()
    scope=_Scope(app)
    program=parse(text,source,compilation_profile=app.interpreter.compilation_profile)
    app.check_program(program);_validate_command(program,app)
    plan=prepare(text,source_name=source,parsed_ast=_snapshot(program),
        repairs=REPAIRS+('authority_checkpoints',),external_names=tuple(app._definitions)+metadata.ROOT_NAMES,
        _trusted_entry=True,_return_last_expression=True)
    owner=app.interpreter
    previous=getattr(owner,"_transaction_activation_allowed",True)
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
