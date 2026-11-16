"""Live admission and invalidation for closed translated scalar regions."""
import sys
import signal
import gc
from contextlib import contextmanager
from types import MethodType
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind

_SCALARS = (Decimal, bool, str, type(None))
_PROCESS_SIGNALS = tuple(signal.valid_signals())

def closed_process_context():
    # A second Python thread or a custom signal handler can revoke authority
    # without an explicit BSL service boundary. Keep per-node execution there.
    # Query before the remaining ABI audit, since Python auditing may run here.
    if type(gc.callbacks) is not list or gc.callbacks:return False
    if len(sys._current_frames()) != 1:return False
    for signum in _PROCESS_SIGNALS:
        handler=signal.getsignal(signum)
        if not any(handler is trusted for trusted in
                   (signal.SIG_DFL,signal.SIG_IGN,signal.default_int_handler,None)):
            return False
    return True

def scope(execution,names,optional,*,record=True,allow_module=False):
    from .compiled_backend import Engine, _SCALAR_GUARD_NAMES, _SCALAR_GUARD_ABI
    from .python_translation_blocks import Execution, _SCALAR_EXECUTION_NAMES, _SCALAR_EXECUTION_ABI
    from .python_translation_expressions import ExpressionExecution, _SCALAR_EXPRESSION_NAMES, _SCALAR_EXPRESSION_ABI
    if not closed_process_context():return None
    engine=execution.engine;vm=execution.vm
    if (type(engine) is not Engine or type(execution) is not Execution
            or type(execution.expressions) is not ExpressionExecution):return None
    for owner,names_,originals in ((engine,_SCALAR_GUARD_NAMES,_SCALAR_GUARD_ABI),
                                  (execution,_SCALAR_EXECUTION_NAMES,_SCALAR_EXECUTION_ABI),
                                  (execution.expressions,_SCALAR_EXPRESSION_NAMES,_SCALAR_EXPRESSION_ABI)):
        for name,original in zip(names_,originals):
            if name in vars(owner) or vars(type(owner)).get(name) is not original:return None
    guard=execution.expressions.guard
    if (type(guard) is not MethodType or guard.__self__ is not execution
            or guard.__func__ is not _SCALAR_EXECUTION_ABI[2]):return None
    if sys.gettrace() is not None or sys.getprofile() is not None:return None
    if not engine.OWNED_SNAPSHOT or engine.ORIGIN_MUTATION_MONITOR:return None
    frame=engine._plain_scope_snapshot()
    if frame is None or not engine.fast_available(refresh=True):return None
    # A pure body still belongs to its current interpreter family. Revocation
    # must not be hidden merely because it performs no explicit routine call.
    owner=vm._family_owner
    if type(owner) is not type(vm):return None
    owner_fields=vars(owner)
    if any(type(key) is not str for key in owner_fields):return None
    if (vm._family_closed is not False or vm._family_released is not False
            or owner._family_closed is not False):return None
    if (type(vm._family_generation) is not int or type(owner._family_generation) is not int
            or vm._family_generation != owner._family_generation):return None
    local=frame[0]
    module=local is None
    if module:
        if not allow_module or not vm._has_module_context:return None
        local=vm.variables
    if type(local) is not dict:return None
    if any(type(key) is not str for key in local):return None
    if any((not module and name in vm.module_names) or name in vm.imports or name in ('thisobject','этотобъект') for name in names):return None
    if any(name not in local and name not in optional for name in names):return None
    if any(name in local and not any(type(local[name]) is scalar for scalar in _SCALARS) for name in names):return None
    if record:engine.stats['python_scalar_regions']=engine.stats.get('python_scalar_regions',0)+1
    return local


@contextmanager
def closed_gc_lease():
    enabled=gc.isenabled()
    gc.disable()
    try:yield
    finally:
        if enabled:gc.enable()
        else:gc.disable()

class ClosedLease:
    """Revalidate a closed region on backedges and before publishing its writes.

    This is not a thread lock. Unexpected concurrent authority/state changes
    invalidate the region, reject without replay, and suppress its uncommitted
    writes. Instrumented/policy execution never enters this representation.
    """
    def __init__(self,execution,plan,local,*,allow_module=False):
        self.execution=execution;self.plan=plan;self.local=local
        self.allow_module=allow_module;self.valid=True;self.ticks=0
        self.initial=tuple((name,name in local,local.get(name)) for name in plan.names)
    def check(self):
        from .compiled_backend import CompiledUnsupported
        try:
            if not self.valid:raise CompiledUnsupported(None,'synchronous region lease invalidated')
            local=scope(self.execution,self.plan.names,self.plan.names-set(self.plan.parameters),
                        record=False,allow_module=self.allow_module)
            unchanged=(local is self.local and not gc.isenabled()
                and all((name in local) is present and (not present or local[name] is value)
                        for name,present,value in self.initial))
            if not unchanged:raise CompiledUnsupported(None,'synchronous region authority or storage changed')
            engine=self.execution.engine
            engine._verify_active_plans()
            for node in self.plan.nodes:engine.verify_node(node)
            for container in self.plan.containers:engine._verify_owned_identity(container)
        except BaseException:
            self.valid=False
            raise
    def publish(self,name,value):
        # Publishing is an explicit storage-service boundary. Use the ordinary
        # setter so even a concurrent policy/reference change between validation
        # and this write retains its normal authority checks.
        self.check()
        try:
            self.execution.vm.set_variable(name,value)
            self.initial=tuple((key,True,value) if key==name else (key,present,old)
                               for key,present,old in self.initial)
        except BaseException as error:
            self.valid=False
            if not isinstance(error,Exception) or isinstance(error,MemoryError):raise
            from .compiled_backend import CompiledUnsupported
            raise CompiledUnsupported(None,'live storage publication rejected') from error
    def backedge(self):
        self.ticks+=1
        if self.ticks % 64 == 0:self.check()
