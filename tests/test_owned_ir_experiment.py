"""Owned IR probes use subprocess isolation for mode/patch independence."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PRELUDE = '''
from yadinassi.owned_syntax import enable_isolated_process_experiment, syntax_kind
from yadinassi.compiled_backend import Engine
enable_isolated_process_experiment()
Engine.OWNED_SNAPSHOT = True
Engine.ORIGIN_MUTATION_MONITOR = True
Engine.INLINE = True
Engine.FAST_INLINE = True
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
from yadinassi.compiled_backend import CompiledUnsupported
'''


class OwnedIRSubprocessTests(unittest.TestCase):
    def probe(self, source, *, enable=True):
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join((str(_ROOT), str(_ROOT / 'tests')))
        env['YADINASSI_OWNED_IR_EXPERIMENT'] = 'isolated-process-v1'
        # Optimize imported production modules with the parent, but retain probe
        # assertions even under -O/-OO. Otherwise a green probe could be vacuous.
        script = (_PRELUDE if enable else '') + source
        flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
        launcher = 'exec(compile(' + repr(script) + ', \"<owned-probe>\", \"exec\", optimize=0))'
        process = subprocess.run([sys.executable, *flags, '-c', launcher],
                                 cwd=_ROOT, env=env, capture_output=True, text=True,
                                 timeout=60)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_mode_contract_is_captured_per_engine_across_class_toggles(self):
        self.probe('''
Engine.OWNED_SNAPSHOT=False
ordinary=Interpreter(execution_backend='compiled-strict')
ordinary_engine=ordinary._compiled()
Engine.OWNED_SNAPSHOT=True
Engine.ORIGIN_MUTATION_MONITOR=True
full=Interpreter(execution_backend='compiled-strict')
full_engine=full._compiled()
full_program=parse('r=1;');full_engine.prepare(full_program)
Engine.ORIGIN_MUTATION_MONITOR=False
snapshot=Interpreter(execution_backend='compiled-strict')
snapshot_engine=snapshot._compiled()
snapshot_program=parse('r=1;');snapshot_engine.prepare(snapshot_program)
# Flip class defaults again while all three engines remain alive.
Engine.OWNED_SNAPSHOT=False
Engine.ORIGIN_MUTATION_MONITOR=True
assert ordinary_engine.OWNED_SNAPSHOT is False
assert full_engine.OWNED_SNAPSHOT is True and full_engine.ORIGIN_MUTATION_MONITOR is True
assert snapshot_engine.OWNED_SNAPSHOT is True and snapshot_engine.ORIGIN_MUTATION_MONITOR is False
ordinary_program=parse('r=1;')
ordinary_engine.prepare(ordinary_program)
assert ordinary_engine.execution_view(ordinary_program[0]) is ordinary_program[0]
full_program[0].value.value=99
try:full_engine.verify_all()
except CompiledUnsupported:pass
else:raise AssertionError('full monitor silently changed to snapshot')
snapshot_program[0].value.value=99
snapshot_engine.verify_all()
snapshot.visit(snapshot_engine.execution_view(snapshot_program[0]))
assert snapshot.variables['r']==1
assert ordinary_engine.stats['owned_snapshot'] is False
assert full_engine.stats['active_ast_contract']=='fail-closed'
assert full_engine.stats['origin_mutation_monitor']=='full'
assert snapshot_engine.stats['active_ast_contract']=='snapshot'
assert snapshot_engine.stats['origin_mutation_monitor']=='off'
''')

    def test_off_rhs_mutation_keeps_admitted_assignment_target(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict');program=parse('target=Mutate();')
calls=[]
def mutate():
 calls.append('rhs');program[0].target.name='hijacked';return 42
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['rhs'] and vm.variables['target']==42 and 'hijacked' not in vm.variables
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_actual_mutation_does_not_redirect_admitted_callee(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict')
program=parse('Function Original(x) Return 1;EndFunction Function Hijack(x) Return 99;EndFunction r=Original(Mutate());')
calls=[]
def mutate():
 calls.append('actual');program[-1].value.callee.name='Hijack';return 0
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['actual'] and vm.variables['r']==1
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_actual_mutation_keeps_parameter_binding_flags_and_default(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict')
program=parse('Function F(Val x, trigger, Val y=7) x=9;Return y;EndFunction a=1;r=F(a,Mutate());')
calls=[]
def mutate():
 calls.append('actual')
 program[0].parameters[0].by_value=False
 program[0].parameters[0].name='renamed'
 program[0].parameters[2].default.value=99
 return 0
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['actual'] and vm.variables['r']==7 and vm.variables['a']==1
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_block_append_and_future_literal_do_not_change_snapshot(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict');program=parse('Mutate();final=1;')
calls=[]
def mutate():
 calls.append('append');program[-1].value.value=99;program.extend(parse('injected=42;'))
vm.register_function('Mutate',mutate);vm.execute_program(program)
assert calls==['append'] and vm.variables['final']==1 and 'injected' not in vm.variables
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_caught_bsl_host_error_uses_admitted_handler(self):
        self.probe('''
from yadinassi.errors import BSLRuntimeError
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict');program=parse('Try Boom();Except caught=1;EndTry;')
calls=[]
def boom():
 calls.append('boom');program[0].handler[0].target.name='hijacked';program[0].handler[0].value.value=99
 raise BSLRuntimeError('expected host BSL error')
vm.register_function('Boom',boom);vm.execute_program(program)
assert calls==['boom'] and vm.variables['caught']==1 and 'hijacked' not in vm.variables
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_opaque_value_callbacks_cannot_inject_changed_syntax(self):
        self.probe('''
from decimal import Decimal
Engine.ORIGIN_MUTATION_MONITOR=False
for mode in ('equality','decimal','metaclass'):
 vm=Interpreter(execution_backend='compiled-strict');calls=[]
 source={'equality':'r=(x=x);final=1;','decimal':'r=-x;final=1;','metaclass':'r=Construct();final=1;'}[mode]
 program=parse(source)
 def change():
  calls.append(mode);program[-1].value.value=99
 class HostValue:
  def __eq__(self,other):change();return True
 class HostDecimal(Decimal):
  def copy_negate(self):change();return Decimal(-1)
 class Meta(type):
  def __call__(cls):change();return Decimal(3)
 class Construct(metaclass=Meta):pass
 if mode=='equality':vm.variables['x']=HostValue()
 elif mode=='decimal':vm.variables['x']=HostDecimal(1)
 else:vm.register_function('Construct',Construct)
 vm.execute_program(program)
 assert calls==[mode] and vm.variables['final']==1
 assert vm.variables['r']=={'equality':True,'decimal':Decimal(-1),'metaclass':Decimal(3)}[mode]
 assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_routine_selection_reads_frozen_dual_metadata(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
for initially_dual in (False,True):
 vm=Interpreter(execution_backend='compiled-strict')
 program=parse('Function F() Return 7;EndFunction Mutate();r=F();')
 program[0].is_dual=initially_dual
 if initially_dual:program[0].module_context=False
 def mutate():
  program[0].is_dual=not initially_dual
  program[0].execution_context='server'
 vm.register_function('Mutate',mutate);vm.execute_program(program)
 assert vm.variables['r']==7 and vm.routines['f'] is program[0]
 assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_off_module_export_gate_and_ready_remain_separate(self):
        self.probe('''
from yadinassi.runtime import _Module
Engine.ORIGIN_MUTATION_MONITOR=False
for exported in (False,True):
 vm=Interpreter(execution_backend='compiled-strict')
 program=parse('Function F() Return 7;EndFunction Mutate();Try r=m.F();Except rejected=True;EndTry;')
 program[0].exported=exported
 module=_Module(vm);module.ready=True;vm.imports['m']=module
 def mutate():
  program[0].exported=not exported
  # Mutating non-dual to dual must not change receiver admission either.
  program[0].is_dual=True
 vm.register_function('Mutate',mutate);vm.execute_program(program)
 if exported:assert vm.variables['r']==7 and 'rejected' not in vm.variables
 else:assert vm.variables['rejected'] is True and 'r' not in vm.variables
 assert vm.compiled_backend_stats['interpreter_fallbacks']==0
# Readiness is live authority, not frozen syntax metadata.
vm=Interpreter(execution_backend='compiled-strict')
program=parse('Function F() Export Return 7;EndFunction Revoke();Try r=m.F();Except rejected=True;EndTry;')
module=_Module(vm);module.ready=True;vm.imports['m']=module
vm.register_function('Revoke',lambda:setattr(module,'ready',False))
vm.execute_program(program)
assert vm.variables['rejected'] is True and 'r' not in vm.variables
''')

    def test_off_json_and_completion_validation_use_admitted_metadata(self):
        self.probe('''
from yadinassi.runtime import _Module
Engine.ORIGIN_MUTATION_MONITOR=False
for kind in ('completion','json'):
 vm=Interpreter(execution_backend='compiled-strict')
 if kind=='completion':
  source='Function F(Result,Extra) Export Return Result;EndFunction Mutate();c=New CallbackDescription("F",m);r=RunCallback(c,7);'
 else:
  source='Function F(Property,Value,Extra) Export Return Value;EndFunction Mutate();reader=New JSONReader;reader.SetString("7");r=ReadJSON(reader,False,,,"F",m);'
 program=parse(source)
 module=_Module(vm);module.ready=True;vm.imports['m']=module
 calls=[]
 def mutate():
  calls.append(kind)
  routine=program[0]
  routine.exported=False;routine.is_async=True;routine.is_function=False
  routine.execution_context='server';routine.module_context=False
  routine.parameters.clear()
 vm.register_function('Mutate',mutate);vm.execute_program(program)
 assert calls==[kind] and vm.variables['r']==7
 assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_full_nonfast_active_ancestor_checks_original_before_effects(self):
        self.probe('''
Engine.FAST_INLINE=False
vm=Interpreter(execution_backend='compiled-strict')
program=parse('target=Mutate();')
def mutate():
 program[0].target.name='hijacked'
 return 42
vm.register_function('Mutate',mutate)
try:vm.execute_program(program)
except CompiledUnsupported:pass
else:raise AssertionError('nonfast active original target mutation accepted')
assert 'target' not in vm.variables and 'hijacked' not in vm.variables
''')

    def test_owned_plan_execution_does_not_rehash_owned_shape(self):
        self.probe('''
from unittest.mock import patch
import yadinassi.compiled_backend as compiler
from yadinassi.owned_syntax import is_owned,OwnedList
Engine.ORIGIN_MUTATION_MONITOR=False
Engine.FAST_INLINE=False
vm=Interpreter(execution_backend='compiled-strict')
engine=vm._compiled();program=parse('r=1+2;')
engine.prepare(program)
original_signature=compiler._signature
original_block=compiler._verify_block
counts=[]
def signature(node,*args,**kwargs):
 if is_owned(node):raise AssertionError('owned view shape rehashed')
 counts.append('origin');return original_signature(node,*args,**kwargs)
def block(items,expected):
 if is_owned(items):raise AssertionError('owned block shape rehashed')
 return original_block(items,expected)
with patch.object(compiler,'_signature',signature),patch.object(compiler,'_verify_block',block):
 for statement in program:
  generator=engine.run_node(statement)
  try:next(generator)
  except StopIteration:pass
 generator=engine.run_block(program)
 try:next(generator)
 except StopIteration:pass
assert vm.variables['r']==3 and counts==[]
# Unknown owned graph cannot enter another engine without explicit admission.
foreign=Interpreter(execution_backend='compiled-strict')._compiled()
view=engine.execution_view(program[0])
try:foreign.verify_node(view)
except CompiledUnsupported:pass
else:raise AssertionError('unknown owned view accepted')
# A forged sequence is never registered merely because its class is OwnedList.
forged=list.__new__(OwnedList)
try:engine._verify_owned_identity(forged)
except CompiledUnsupported:pass
else:raise AssertionError('unregistered owned sequence accepted')
''')

    def test_full_known_owned_node_requires_saved_origin_fingerprint(self):
        self.probe('''
vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
original=parse('r=1;')[0];engine.prepare_node(original)
view=engine.execution_view(original)
# Internal-corruption robustness probe, not a Python sandbox boundary.
saved=engine._origin_signatures.pop(id(original))
try:engine.verify_node(view)
except CompiledUnsupported as error:assert 'no origin fingerprint' in error.reason
else:raise AssertionError('missing full-monitor fingerprint silently accepted')
engine._origin_signatures[id(original)]=saved
engine.verify_node(view)
assert vm.variables=={}
''')

    def test_only_off_skips_ancestor_scan_but_not_current_admission(self):
        self.probe('''
from unittest.mock import patch
for owned,monitor in ((False,True),(True,True),(True,False)):
 Engine.OWNED_SNAPSHOT=owned;Engine.ORIGIN_MUTATION_MONITOR=monitor
 vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
 program=parse('target=1;');engine.prepare(program)
 node=engine.execution_view(program[0])
 plan=engine._nodes[id(node)]
 engine._active_plans.append(plan)
 with patch.object(engine,'verify_node',wraps=engine.verify_node) as verify:
  engine._verify_active_plans()
  assert verify.call_count==(0 if owned and not monitor else 1)
 engine._active_plans.clear()
 # Unknown current nodes reject in every mode, including OFF.
 unknown=parse('other=2;')[0]
 try:engine.verify_node(unknown)
 except CompiledUnsupported:pass
 else:raise AssertionError('unknown node admitted by scan optimization')
 if owned:
  from yadinassi.owned_syntax import OwnedList
  fake=list.__new__(OwnedList)
  try:engine._verify_owned_identity(fake)
  except CompiledUnsupported:pass
  else:raise AssertionError('unknown owned block admitted')
''')

    def test_off_nonfast_keeps_policy_hooks_and_live_authority_checks(self):
        self.probe('''
from yadinassi.runtime import _Module
Engine.ORIGIN_MUTATION_MONITOR=False
from unittest.mock import patch
events=[]
original_before=Interpreter.compiled_before
def before(vm,node):
 events.append(type(node).__name__)
 return original_before(vm,node)
vm=Interpreter(execution_backend='compiled-strict')
program=parse('Function F() Export Return 7;EndFunction Revoke();Try r=m.F();Except rejected=True;EndTry;')
module=_Module(vm);module.ready=True;vm.imports['m']=module
vm.register_function('Revoke',lambda:setattr(module,'ready',False))
with patch.object(Interpreter,'compiled_before',before):
 vm.execute_program(program)
 assert vm._compiled().fast_available() is False
assert 'Call' in events and 'Assign' in events
assert vm.variables['rejected'] is True and 'r' not in vm.variables
assert vm.compiled_backend_stats['interpreter_fallbacks']==0
''')

    def test_admission_journal_restores_overwritten_inserted_and_nested_state(self):
        self.probe('''
from unittest.mock import patch
vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
existing=parse('r=1;')[0];engine.prepare_node(existing)
def maps():return (engine._owned.memo,engine._origin_signatures,engine._origin_blocks,engine._nodes,engine._blocks)
original_maps=maps();before=[dict(mapping) for mapping in original_maps]
fresh=parse('other=2;')[0]
def reject_after_writes(*args,**kwargs):
 for mapping in maps():
  mapping[-100]=('inserted',)
  key=next(iter(mapping),None)
  if key is not None:mapping[key]=('overwritten',)
 raise CompiledUnsupported(None,'late synthetic rejection')
with patch.object(engine,'_lower_node',reject_after_writes):
 try:engine.prepare_node(fresh)
 except CompiledUnsupported:pass
 else:raise AssertionError('late rejection missing')
assert all(now is old for now,old in zip(maps(),original_maps))
assert all(dict(now)==saved for now,saved in zip(maps(),before))
# Fresh-root clear remains provisional until all lowering succeeds.
with patch.object(engine,'_lower_node',reject_after_writes):
 try:engine.prepare([fresh])
 except CompiledUnsupported:pass
 else:raise AssertionError('fresh-root rejection missing')
assert all(dict(now)==saved for now,saved in zip(maps(),before))
# A successful nested preparation must also roll back with its outer unit.
original_lower=engine._lower_node
nested=parse('nested=3;')[0]
def nested_then_reject(*args,**kwargs):
 with patch.object(engine,'_lower_node',original_lower):engine.prepare_node(nested)
 raise RuntimeError('unexpected compiler failure')
with patch.object(engine,'_lower_node',nested_then_reject):
 try:engine.prepare_node(fresh)
 except RuntimeError:pass
 else:raise AssertionError('unexpected failure missing')
assert all(dict(now)==saved for now,saved in zip(maps(),before))
assert not engine.has_node(nested) and engine.has_node(existing)
engine.prepare_node(fresh);assert engine.has_node(fresh)
''')

    def test_late_admission_never_copies_existing_registry(self):
        self.probe('''
vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
engine.prepare(parse(';'.join('r%d=%d'%(i,i) for i in range(40))+';'))
class NoTraversal(dict):
 def __iter__(self):raise AssertionError('whole registry iteration')
 def keys(self):raise AssertionError('whole registry copy')
 def items(self):raise AssertionError('whole registry items')
 def values(self):raise AssertionError('whole registry values')
engine._owned.memo=NoTraversal(engine._owned.memo)
engine._origin_signatures=NoTraversal(engine._origin_signatures)
engine._origin_blocks=NoTraversal(engine._origin_blocks)
engine._nodes=NoTraversal(engine._nodes);engine._blocks=NoTraversal(engine._blocks)
node=parse('fresh=42;')[0];engine.prepare_node(node)
assert engine.has_node(node)
''')

    def test_owned_ir_memo_skips_recursive_resnapshot_only_for_owned_nodes(self):
        self.probe('''
from unittest.mock import patch
import dataclasses
from yadinassi.compiled_inline import snapshot
vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
program=parse('r=(1+2)*(3+4);');engine.prepare(program)
view=engine.execution_view(program[0]);engine._inline_ir.clear()
with patch.object(dataclasses,'fields',wraps=dataclasses.fields) as fields:
 first=snapshot(view,engine);count=fields.call_count
 assert count>1
 assert snapshot(view,engine) is first and fields.call_count==count
 child=snapshot(view.value,engine)
 assert fields.call_count==count and child.node is view.value
# Ordinary mutable source is never stored in this memo.
raw=parse('r=1;')[0]
one=snapshot(raw,engine);raw.value.value=99;two=snapshot(raw,engine)
assert one is not two and id(raw) not in engine._inline_ir
''')

    def test_owned_ir_memo_is_per_engine_and_preserves_payload_source_and_release(self):
        self.probe('''
import gc,weakref
from yadinassi.compiled_inline import snapshot
class Payload:pass
refs=[]
for source in ('first.bsl','second.bsl'):
 vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
 node=parse('r=1;',source)[0].value;payload=Payload();node.value=payload
 engine.prepare_node(node);view=engine.execution_view(node);ir=snapshot(view,engine)
 assert dict(ir.fields)['value'] is payload and ir.node.token.source==source
 refs.extend((weakref.ref(payload),weakref.ref(view)))
 engine.release();assert not engine._inline_ir
 del vm,engine,node,payload,view,ir
 gc.collect()
assert all(ref() is None for ref in refs)
''')

    def test_owned_ir_cache_rollback_limits_and_generated_budgets(self):
        self.probe('''
from unittest.mock import patch
from yadinassi.compiled_inline import snapshot,Emitter
vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
node=parse('r=1;')[0];engine.prepare_node(node)
before=dict(engine._inline_ir)
new=parse('fresh=2+3;')[0]
with patch.object(engine,'MAX_INLINE_UNIT_BYTES',1):
 try:engine.prepare_node(new)
 except CompiledUnsupported:pass
 else:raise AssertionError('failed admission unexpectedly accepted')
assert set(engine._inline_ir)==set(before)
assert all(engine._inline_ir[key] is value for key,value in before.items())
view=engine.execution_view(node)
# A cache hit never bypasses emission budgets.
for field in ('MAX_INLINE_FUNCTION_BYTES','MAX_INLINE_UNIT_BYTES'):
 with patch.object(engine,field,1):
  try:Emitter(engine).compile(view)
  except CompiledUnsupported:pass
  else:raise AssertionError('IR hit bypassed generated-source budget')
engine._inline_ir.clear()
with patch.object(engine,'MAX_REGISTRY_ENTRIES',1):
 try:snapshot(view,engine)
 except CompiledUnsupported as error:assert 'IR registry limit' in error.reason
 else:raise AssertionError('IR entries unbounded')
assert len(engine._inline_ir)<=1
''')

    def test_flag_alone_never_installs_process_global_guard(self):
        self.probe('''
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.compiled_backend import Engine, CompiledUnsupported
assert '__setattr__' not in vars(ast.Node)
Engine.OWNED_SNAPSHOT=True
vm=Interpreter(execution_backend='compiled-strict')
vm.execute('r=1;')
assert vm.variables['r']==1
assert '__setattr__' not in vars(ast.Node)
''', enable=False)

    def test_exact_types_original_mutability_owned_readonly_and_release(self):
        self.probe('''
import gc, weakref
vm=Interpreter(execution_backend='compiled-strict')
node=parse('r=1;')[0]
engine=vm._compiled();engine.prepare_node(node)
view=engine.execution_view(node)
assert type(node) is ast.Assign
assert type(view) is not ast.Assign and isinstance(view, ast.Assign)
assert syntax_kind(view) is ast.Assign
assert engine.origin_node(view) is node
assert type(view.value) is not ast.Literal and isinstance(view.value,ast.Literal)
assert syntax_kind(view.value) is ast.Literal
node.value.value=7
try: view.value.value=9
except TypeError: pass
else: raise AssertionError('owned field is mutable')
assert view.value.value == 1
body=engine._owned.freeze([node])
for action in (lambda:setattr(body,'_owned_provenance',None),lambda:delattr(body,'_owned_provenance')):
 try:action()
 except TypeError:pass
 else:raise AssertionError('owned list provenance is mutable')
try: body.append(node)
except TypeError: pass
else: raise AssertionError('owned list is mutable')
try: body.__init__([node])
except TypeError: pass
else: raise AssertionError('owned list can be reinitialized')
ref=weakref.ref(view);del view,body
engine.release();gc.collect();assert ref() is None
node.value.value=11
assert node.value.value==11
''')

    def test_existing_custom_ast_setter_is_not_replaced(self):
        self.probe('''
def custom(self,name,value): object.__setattr__(self,name,value)
ast.Node.__setattr__=custom
vm=Interpreter(execution_backend='compiled-strict')
vm.execute('r=1;')
assert ast.Node.__setattr__ is custom
assert vm.variables['r']==1
''')

    def test_full_monitor_keeps_existing_codegen_and_mutation_contracts(self):
        self.probe('''
import unittest
suite=unittest.defaultTestLoader.loadTestsFromNames([
 'tests.test_compiled_codegen.StrictCodegenTests',
 'tests.test_compiled_codegen.MetadataMutationTests',
 'tests.test_compiled_policy_abi',
 'tests.test_compiled_lifecycle.ReentrantAdmissionTests'])
result=unittest.TextTestRunner(verbosity=1).run(suite)
assert result.wasSuccessful()
''')

    def test_configuration_authority_callbacks_and_form_quiescent_replacement(self):
        self.probe('''
import unittest
from yadinassi.execution_policy import execution_backend_policy
names=[
 'tests.test_compiled_contexts.StrictContextTests.test_configuration_cross_owner_defaults_and_callbacks',
 'tests.test_compiled_contexts.StrictContextTests.test_source_value_manager_references',
 'tests.test_form_app.FormControllerTests.test_server_error_keeps_authoritative_state_and_finite_reason']
for monitor in (True,False):
 Engine.ORIGIN_MUTATION_MONITOR=monitor
 with execution_backend_policy('compiled-strict'):
  result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
 assert result.wasSuccessful()
''')

    def test_authority_handles_and_multiple_vms_share_no_mutable_owned_syntax(self):
        self.probe('''
vm=Interpreter(execution_backend='compiled-strict')
program=parse('Function F() Return 7;EndFunction')
vm.execute_program(program)
assert vm.routines['f'] is program[0]
view=vm._compiled().execution_view(program[0])
assert vm._compiled().origin_node(view) is program[0]
class Forged: pass
fake=Forged();fake.origin=program[0]
assert vm._compiled().origin_node(fake) is fake
other=Interpreter(execution_backend='compiled-strict')
other._compiled().prepare_node(view)
assert other._compiled().origin_node(view) is program[0]
assert type(view) is not ast.Routine and isinstance(view,ast.Routine)
assert syntax_kind(view) is ast.Routine
other.execute('r=3;')
program[0].name='ChangedOutside'
assert view.name=='F'
vm._compiled().release()
''')

    def test_foreign_owned_graph_cannot_rebaseline_mutated_origins(self):
        self.probe('''
first=Interpreter(execution_backend='compiled-strict')
program=parse('r=1;')
first._compiled().prepare(program)
view=first._compiled().execution_view(program[0])
block=first._compiled()._owned.existing(program)
program[0].value.value=99
second=Interpreter(execution_backend='compiled-strict')
try:second._compiled().prepare_node(view)
except CompiledUnsupported:pass
else:raise AssertionError('foreign node rebaselined changed origin')
assert second.variables=={}
program[0].value.value=1
program.append(parse('other=2;')[0])
try:second._compiled().prepare_block(block)
except CompiledUnsupported:pass
else:raise AssertionError('foreign block rebaselined changed origin')
program[:]=[None]
try:second._compiled().prepare_block(block)
except CompiledUnsupported:pass
else:raise AssertionError('malformed foreign block rebaselined changed origin')
Engine.ORIGIN_MUTATION_MONITOR=False
third=Interpreter(execution_backend='compiled-strict')
third._compiled().prepare_node(view)
third.visit(view)
assert third.variables['r']==1 and 'other' not in third.variables
''')

    def test_opaque_literal_backlinks_are_collectible_without_losing_live_authority(self):
        self.probe('''
import gc,weakref
from yadinassi.owned_syntax import _ORIGINS
baseline=len(_ORIGINS)
def make():
 vm=Interpreter(execution_backend='compiled-strict')
 original=parse('r=1;')[0].value
 payload=[];original.value=payload
 engine=vm._compiled();engine.prepare_node(original)
 view=engine.execution_view(original);payload.append(view)
 refs=[weakref.ref(x) for x in (vm,engine,original,view)]
 engine.release()
 return refs
refs=[make() for _ in range(8)]
for _ in range(3):gc.collect()
assert all(ref() is None for group in refs for ref in group)
assert len(_ORIGINS)==baseline
# A genuinely surviving view must retain its original authority after release.
vm=Interpreter(execution_backend='compiled-strict')
original=parse('r=1;')[0]
engine=vm._compiled();engine.prepare_node(original)
view=engine.execution_view(original);reference=weakref.ref(original)
engine.release();del original,engine,vm;gc.collect()
assert reference() is not None
other=Interpreter(execution_backend='compiled-strict')
other._compiled().prepare_node(view)
assert other._compiled().origin_node(view) is reference()
other.visit(view);assert other.variables['r']==1
''')

    def test_prefreeze_collection_budget_and_host_fields_are_fail_closed(self):
        self.probe('''
vm=Interpreter(execution_backend='compiled-strict')
engine=vm._compiled()
engine.MAX_COLLECTION_ENTRIES=3
program=parse('Var a,b,c,d;')
try:engine.prepare(program)
except CompiledUnsupported as error:assert 'collection entry limit' in error.reason
else:raise AssertionError('prefreeze list budget missing')
assert not engine._owned.memo and not engine._origin_signatures
class Host:
 def __repr__(self):raise AssertionError('repr called')
 def __eq__(self,other):raise AssertionError('eq called')
program=parse('r=1;')
program[0].target.name=Host()
try:engine.prepare(program)
except CompiledUnsupported as error:assert 'field value' in error.reason
else:raise AssertionError('host metadata accepted')
assert not engine._owned.memo and not engine._origin_signatures
''')

    def test_reuse_rejects_forged_or_wrong_origin_execution_views(self):
        self.probe('''
from types import SimpleNamespace
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_source_runtime import SourceApplication
vm=Interpreter(execution_backend='compiled-strict')
first=parse('Function F() Return 1;EndFunction')[0]
second=parse('Function G() Return 2;EndFunction')[0]
correct=vm._compiled().execution_view(first)
wrong=vm._compiled().execution_view(second)
fake=SimpleNamespace(is_function=True,name='F',origin=first)
for method in (ConfigurationApplication.reusable_call, SourceApplication.reusable_call):
 holder=SimpleNamespace(_reuse_routines={})
 for candidate in (wrong,fake):
  try: method(holder,None,None,first,True,execution_routine=candidate)
  except ValueError as error: assert 'origin mismatch' in str(error)
  else: raise AssertionError('forged reuse execution view accepted')
 assert method(holder,None,None,first,True,execution_routine=correct) is None
''')

    def test_monitor_off_snapshot_is_explicit_not_silent_mutation_parity(self):
        self.probe('''
Engine.ORIGIN_MUTATION_MONITOR=False
vm=Interpreter(execution_backend='compiled-strict')
program=parse('target=Mutate(); final=1;')
def mutate():
 program[0].target.name='hijacked'
 program[-1].value.value=99
 return 42
vm.register_function('Mutate',mutate)
vm.execute_program(program)
assert vm.variables['target']==42 and 'hijacked' not in vm.variables
assert vm.variables['final']==1
stats=vm.compiled_backend_stats
assert stats['active_ast_contract']=='snapshot'
assert stats['origin_mutation_monitor']=='off'
assert stats['origin_monitor_checks']==0
assert stats['interpreter_fallbacks']==0
''')

    def test_quiescent_changed_routine_still_validates_before_arguments(self):
        self.probe('''
from yadinassi.errors import BSLError
for monitor in (True,False):
 Engine.ORIGIN_MUTATION_MONITOR=monitor
 output=[];vm=Interpreter(execution_backend='compiled-strict',output=output.append)
 vm.execute('Procedure P(Val ignored) Message("bad");Goto ~Done;~Done:EndProcedure')
 vm.routines['p'].body[1].name='Caller'
 try:vm.execute('P(Message("bad argument"));~Caller:Message("bad caller");')
 except BSLError as failure:assert 'Метка не определена' in str(failure)
 else:raise AssertionError('changed quiescent routine not validated')
 assert output==[] and vm.locals is None
''')


if __name__ == '__main__': unittest.main()
