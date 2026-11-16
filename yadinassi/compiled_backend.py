"""Strict whole-unit Python-AST lowering; never calls legacy AST visitors.

Generated control flow uses the existing VM node boundary for source diagnostics
and contextual before/after-node policy. Host/value operations use explicitly
named semantic adapters. Those are reported separately from emitted operations.
This module does not make Python compile/exec a security sandbox.
"""
from __future__ import annotations

import ast as python_ast
from dataclasses import dataclass, fields
from decimal import Decimal

from .errors import BSLRuntimeError
from .syntax import ast
from .owned_syntax import AdmissionMap, OwnedStore, OwnedList, syntax_kind, is_owned, owned_provenance, origin_node as syntax_origin, creation_fingerprint


class CompiledUnsupported(BSLRuntimeError):
    """An explicit strict-backend rejection, never an interpreter fallback."""

    def __init__(self, node, reason):
        token = getattr(node, 'token', None)
        super().__init__(f'Compiled backend: {reason}',
                         getattr(token, 'source', '<compiled>'),
                         getattr(token, 'line', 1), getattr(token, 'column', 1),
                         source_line=getattr(token, 'source_line', ''))
        self.reason = reason
        self.node_kind = syntax_kind(node).__name__


_HELPERS = {
    ast.Name: 'semantic_name', ast.Attribute: 'semantic_attribute',
    ast.Index: 'semantic_index', ast.Assign: 'semantic_assign',
    ast.New: 'semantic_new', ast.DynamicNew: 'semantic_dynamic_new',
    ast.Import: 'semantic_import', ast.Raise: 'semantic_raise',
    ast.Execute: 'semantic_execute',
}
_SYNTAX_ONLY = frozenset((ast.Parameter, ast.OmittedArgument, ast.ServerInitializer))
_EMITTED = frozenset((ast.Literal, ast.Group, ast.Unary, ast.Binary, ast.Conditional,
                     ast.If, ast.For, ast.ForEach, ast.While, ast.Break,
                     ast.Continue, ast.Return, ast.Try, ast.Label, ast.Goto,
                     ast.Var, ast.Routine, ast.ExpressionStatement, ast.Await))
_SUPPORTED = _EMITTED | _SYNTAX_ONLY | frozenset(_HELPERS) | {ast.Call}


def _signature_value(value, *, metadata=False):
    # Never call equality/repr/hash on a host value held by a literal.
    if type(value) in (str, int, bool, type(None)):
        return (id(type(value)), value)
    if syntax_kind(value) in _SUPPORTED:
        identity = (id(type(value)), id(value))
        return (*identity, _signature(value, metadata=True)) if metadata else identity
    if type(value) in (tuple, list, OwnedList):
        return (id(type(value)), id(value), tuple(
            _signature_value(v, metadata=metadata) for v in value))
    return (id(type(value)), id(value))


# These descendants are inspected as metadata by semantic adapters, without a
# normal _visit boundary. Other children validate their own shallow signature
# when entered; hashing an entire loop body on every expression is quadratic.
_METADATA_FIELDS = {
    ast.Call: frozenset(('callee',)),
    ast.Assign: frozenset(('target',)),
    ast.Routine: frozenset(('parameters',)),
    ast.ExpressionStatement: frozenset(('expression',)),
}


def _signature(node, *, metadata=False):
    try:
        kind = syntax_kind(node)
        selected = _METADATA_FIELDS.get(kind, ())
        return (id(kind), tuple((field.name,
                    (id(type(node.value)), id(node.value)) if kind is ast.Literal and field.name == 'value'
                    else _signature_value(getattr(node, field.name),
                                          metadata=metadata or field.name in selected))
                    for field in fields(node)))
    except RecursionError:
        raise CompiledUnsupported(node, 'cyclic or excessive AST signature') from None


def _verify_node(node, expected):
    if _signature(node) != expected:
        raise CompiledUnsupported(node, 'AST changed after compilation-unit admission')


def _verify_block(statements, expected):
    if tuple((id(type(node)), id(node)) for node in statements) != expected:
        raise CompiledUnsupported(statements[0] if statements else None,
                                  'block changed after compilation-unit admission')


_ABSENT_ADMISSION = object()

class _TransientAdmission:
    """A dynamic admission lease, retaining dependencies of later live units."""
    def __init__(self, engine):
        self.engine = engine
        self.entries = []
        self.dependencies = {}
        self.introduced = set()
        self.origins = {}
        self.owned_registry = engine._owned.versions
        self.owned_key_registries = (engine._owned.versions, engine._nodes, engine._blocks,
                                    engine._inline_ir, engine._plain_routines, engine._plain_modules)
        self.origin_key_registries = (engine._owned.memo, engine._origin_signatures, engine._origin_blocks)
        self.unit_registry = engine._python_units

    def activate(self):
        for registry, key, previous, admitted in self.entries:
            if registry is self.owned_registry and previous is _ABSENT_ADMISSION:
                self.introduced.add(key)
                self.origins[key] = id(admitted[0])
        self.engine._transient_leases.append(self)

    def observe(self, owned_ids, anchors):
        shared = self.introduced.intersection(owned_ids)
        if not shared:return
        # Prune ended/replaced transient dependents; retain only live anchors.
        self.dependencies = {key:entry for key,entry in self.dependencies.items()
                             if entry[0].get(entry[1], _ABSENT_ADMISSION) is entry[2]}
        shared=frozenset(shared)
        for registry,key,value in anchors:
            self.dependencies[(id(registry),key)] = (registry,key,value,shared)

    def close(self):
        self.engine._transient_leases[:] = [lease for lease in self.engine._transient_leases if lease is not self]
        if not self.entries:return
        protected=set()
        for registry,key,value,shared in self.dependencies.values():
            if registry.get(key, _ABSENT_ADMISSION) is value:protected.update(shared)
        protected_origins={self.origins[key] for key in protected}
        entries, self.entries = self.entries, []
        self.dependencies.clear()
        for registry, key, previous, admitted in reversed(entries):
            if registry.get(key, _ABSENT_ADMISSION) is not admitted:
                continue
            if any(registry is candidate for candidate in self.owned_key_registries) and key in protected:
                continue
            if any(registry is candidate for candidate in self.origin_key_registries) and key in protected_origins:
                continue
            if registry is self.unit_registry and id(admitted[0]) in protected:
                continue
            if previous is _ABSENT_ADMISSION:
                registry.pop(key, None)
            else:
                registry[key] = previous
        self.introduced.clear();self.origins.clear()


@dataclass(frozen=True)
class _NodePlan:
    node: ast.Node
    signature: tuple
    function: object | None
    tier: str


@dataclass(frozen=True)
class _BlockPlan:
    statements: list
    signature: tuple
    function: object
    role: str = 'structural'
    entries: tuple = ()
    labels: object = None


# One compiled compatibility entry for metadata/argument lists explicitly passed
# to public block(). Child entry remains strictly compiled, never old visitors.
_METADATA_BLOCK_SOURCE = """def generated(vm, engine, plan):
    result = None
    position = 0
    while position < len(plan.entries):
        engine._check_block_plan(plan)
        try:
            result = yield from vm._visit(plan.entries[position])
        except Goto as jump:
            if jump.name not in plan.labels: raise
            position = plan.labels[jump.name]
        else:
            position += 1
    engine._check_block_plan(plan)
    return result
"""

def _make_metadata_block_entry():
    from .runtime import _Goto
    namespace = {'Goto': _Goto}
    exec(compile(_METADATA_BLOCK_SOURCE, '<bsl-metadata-block>', 'exec',
                 dont_inherit=True), namespace)
    return namespace['generated']

_METADATA_BLOCK_ENTRY = _make_metadata_block_entry()


def _translated_literal_value(vm,node):
    return node.value


def _translated_name_value(vm,node):
    return vm.semantic_name(node)


class Engine:
    # Broad integration branch: ordinary strict execution uses Python translation.
    FORCE_PYTHON_TRANSLATION = True

    def _force_translation_gap(self, node, route):
        if not self.FORCE_PYTHON_TRANSLATION:
            return
        kind = syntax_kind(node).__name__ if node is not None else "EmptyBlock"
        gaps = self.stats.setdefault("force_translation_gaps", {})
        key = route + ":" + kind
        gaps[key] = gaps.get(key, 0) + 1
        raise CompiledUnsupported(node, "force Python translation unsupported " + key)

    """One VM's strict compiler registry; no user bindings live in code caches.

    ``prepare`` is transactional and must be called for each newly materialized
    compilation unit before that unit's first effect. Registries are retained for
    active routines/imports while new units are prepared, not silently cleared.
    """
    OWNED_SNAPSHOT = False
    ORIGIN_MUTATION_MONITOR = True
    INLINE = True
    FAST_INLINE = True
    DETAILED_INLINE_STATS = False
    MAX_NODES = 100_000
    MAX_COLLECTION_ENTRIES = 1_000_000
    MAX_DEPTH = 256
    MAX_REGISTRY_ENTRIES = 100_000
    MAX_INLINE_FUNCTION_BYTES = 4 * 1024 * 1024
    MAX_INLINE_UNIT_BYTES = 64 * 1024 * 1024
    MAX_PLAIN_SOURCE_BYTES = 1024 * 1024

    def __init__(self, vm):
        from .runtime import _Reference
        self._reference_type = _Reference
        # Class flags select new engines only; never change a live contract.
        ast_contract = vm.compiled_ast_contract
        from .execution_policy import AST_CONTRACTS
        if type(ast_contract) is not str or ast_contract not in AST_CONTRACTS:
            raise ValueError('unsupported compiled AST contract')
        self.OWNED_SNAPSHOT = ast_contract == 'snapshot'
        self.ORIGIN_MUTATION_MONITOR = ast_contract == 'mutable'
        self._owned = OwnedStore(_signature, self._block_signature)
        self._origin_signatures = {}
        self._origin_blocks = {}
        self._inline_ir = {}
        self._plain_routines = {}
        self._plain_modules = {}
        self._python_units = {}
        self._transient_leases = []
        self.vm = vm
        self._nodes = {}
        self._blocks = {}
        self._active_frames = 0
        self._active_plans = []
        self._fast_ready = None
        self._opaque_epoch = 0
        self.stats = {'prepared_units': 0, 'prepared_nodes': 0,
                      'emitted_executions': 0, 'helper_executions': 0,
                      'block_executions': 0, 'rejected_units': 0,
                      'unsupported_executions': 0, 'interpreter_fallbacks': 0,
                      'node_kinds': {}, 'inline_blocks': 0, 'inline_fragments': 0,
                      'node_coverage': 'observed' if self.DETAILED_INLINE_STATS else 'unobserved',
                      'compiled_node_functions': 0, 'compiled_block_functions': 0,
                      'reused_node_plans': 0, 'reused_block_plans': 0,
                      'owned_snapshot': self.OWNED_SNAPSHOT,
                      'origin_mutation_monitor': 'full' if self.ORIGIN_MUTATION_MONITOR else 'off',
                      'active_ast_contract': 'snapshot' if self.OWNED_SNAPSHOT and not self.ORIGIN_MUTATION_MONITOR else 'fail-closed',
                      'origin_monitor_checks': 0, 'metadata_block_plans': 0,
                      'metadata_block_executions': 0}

    def origin_node(self, node):
        return syntax_origin(node)

    def execution_view(self, node):
        if not self.OWNED_SNAPSHOT:
            return node
        view = self._owned.existing(node)
        if view is None:
            self.prepare_node(node)
            view = self._owned.existing(node)
        return view

    @staticmethod
    def lowering_inventory():
        """Declaration inventory, NOT evidence that a suite executed each kind."""
        result = {kind.__name__: 'emitted' for kind in _EMITTED}
        result.update({kind.__name__: 'semantic-helper' for kind in _HELPERS})
        result['Call'] = 'semantic-helper'
        result['ExpressionStatement'] = 'emitted-or-call-helper'
        result.update({kind.__name__: 'syntax-only' for kind in _SYNTAX_ONLY})
        return result

    def _owned_program(self, program, allow_reprepare):
        if allow_reprepare and not self._active_frames and self.ORIGIN_MUTATION_MONITOR:
            self._owned.clear()
            self._origin_signatures.clear()
            self._origin_blocks.clear()
            self._inline_ir.clear()
        seen, active, sequences = set(), set(), set()
        collection_entries = 0
        def visit(value, depth=0):
            nonlocal collection_entries
            if not self.ORIGIN_MUTATION_MONITOR:
                # An admitted identity denotes its immutable version. New
                # source requires a new graph; retained routines survive REPL.
                # Do not accept another engine's view as a local cache hit.
                entry = self._owned.memo.get(id(value))
                if entry is not None and entry[0] is value:
                    if allow_reprepare and not self._active_frames:
                        # An explicit quiescent unit admission publishes a new
                        # version of this graph only. Unrelated routines keep
                        # their previous version; admission journals rollback.
                        self._owned.memo.pop(id(value), None)
                    else:
                        return
            if depth > self.MAX_DEPTH:
                raise CompiledUnsupported(None, 'owned admission depth limit')
            if isinstance(value, ast.Node):
                if syntax_kind(value) not in _SUPPORTED or (type(value) not in _SUPPORTED and not is_owned(value)):
                    raise CompiledUnsupported(value, 'unsupported owned syntax node')
                declared_fields = {field.name for field in fields(value)}
                if is_owned(value): declared_fields.add('_owned_provenance')
                if any(name not in declared_fields for name in vars(value)):
                    raise CompiledUnsupported(value, 'owned syntax does not admit custom AST attributes')
                if id(value) in active: raise CompiledUnsupported(value, 'cyclic owned syntax')
                if id(value) in seen: return
                if len(seen) >= self.MAX_NODES: raise CompiledUnsupported(value, 'owned admission node limit')
                seen.add(id(value));active.add(id(value))
                # Budget and validate children before constructing signatures.
                for field in fields(value):
                    if field.name != 'token' and not (syntax_kind(value) is ast.Literal and field.name == 'value'):
                        visit(getattr(value, field.name), depth + 1)
                original = syntax_origin(value)
                admitted = creation_fingerprint(value) if is_owned(value) else None
                if admitted is not None and admitted[0] != 'node':
                    raise CompiledUnsupported(value, 'owned node provenance mismatch')
                expected = admitted[1] if admitted is not None else _signature(original)
                if admitted is not None and self.ORIGIN_MUTATION_MONITOR:
                    _verify_node(original, expected)
                previous = self._origin_signatures.get(id(original))
                if previous is not None and not allow_reprepare:
                    _verify_node(original, previous[1])
                self._origin_signatures[id(original)] = (original, expected)
                active.remove(id(value))
            elif type(value) in (list, tuple, OwnedList):
                if type(value) is OwnedList and not is_owned(value):
                    raise CompiledUnsupported(None, 'unregistered owned syntax sequence')
                if id(value) in active: raise CompiledUnsupported(None, 'cyclic owned syntax sequence')
                if id(value) in sequences: return
                sequences.add(id(value))
                collection_entries += len(value)
                if collection_entries > self.MAX_COLLECTION_ENTRIES:
                    raise CompiledUnsupported(None, 'owned admission collection entry limit')
                active.add(id(value))
                for item in value: visit(item, depth + 1)
                active.remove(id(value))
                original = syntax_origin(value)
                if type(original) is list and (is_owned(value) or all(isinstance(item, ast.Node) for item in original)):
                    admitted = creation_fingerprint(value) if is_owned(value) else None
                    if admitted is not None and admitted[0] != 'block':
                        raise CompiledUnsupported(None, 'owned block provenance mismatch')
                    expected = admitted[1] if admitted is not None else self._block_signature(original)
                    if admitted is not None and self.ORIGIN_MUTATION_MONITOR:
                        _verify_block(original, expected)
                    previous = self._origin_blocks.get(id(original))
                    if previous is not None and not allow_reprepare:
                        _verify_block(original, previous[1])
                    self._origin_blocks[id(original)] = (original, expected)
            elif value is not None and type(value) not in (str, bool):
                raise CompiledUnsupported(None, 'unsupported owned syntax field value')
        visit(program)
        try:
            return self._owned.freeze(program)
        except (TypeError, RuntimeError) as failure:
            raise CompiledUnsupported(None, str(failure)) from None

    def prepare(self, program, *, allow_reprepare=True, module_entry=False, _transient=None):
        if not self.OWNED_SNAPSHOT:
            return self._prepare(program, allow_reprepare=allow_reprepare, module_entry=module_entry)
        # Journal only this admission's writes, not the entire active registry.
        # Nested admission writes into these overlays; any outer failure discards
        # all of them. No AST/host code runs while publishing builtin-map writes.
        bases = (self._owned.memo, self._owned.versions, self._origin_signatures, self._origin_blocks,
                 self._nodes, self._blocks, self._inline_ir, self._plain_routines, self._plain_modules, self._python_units)
        journals = tuple(AdmissionMap(base) for base in bases)
        (self._owned.memo, self._owned.versions, self._origin_signatures, self._origin_blocks,
         self._nodes, self._blocks, self._inline_ir, self._plain_routines, self._plain_modules, self._python_units) = journals
        try:
            result = self._prepare(program, allow_reprepare=allow_reprepare, module_entry=module_entry)
            captured = []
            if _transient is not None:
                for base, journal in zip(bases, journals):
                    if journal.cleared or any(value is AdmissionMap._DELETED for value in journal.changes.values()):
                        raise CompiledUnsupported(None, 'transient admission cannot clear registries')
                    captured.extend((base, key, base.get(key, _ABSENT_ADMISSION), value)
                                    for key, value in journal.changes.items())
            # Record owned dependency edges before publication, using the
            # already-validated graph and only this admission's journal writes.
            owned_ids=set()
            anchors=[]
            if self._transient_leases:
                dependency_seen=set()
                def dependencies(value):
                    if id(value) in dependency_seen:return
                    dependency_seen.add(id(value))
                    if type(value) is tuple:
                        for child in value:dependencies(child)
                        return
                    if not is_owned(value):return
                    owned_ids.add(id(value))
                    kind=syntax_kind(value)
                    if kind in _SUPPORTED:
                        for field in fields(value):
                            if field.name != 'token' and not (kind is ast.Literal and field.name == 'value'):
                                dependencies(getattr(value,field.name))
                    elif type(value) is OwnedList:
                        for child in value:dependencies(child)
                dependencies(self._owned.existing(program))
                for index in (4,5,9):
                    anchors.extend((bases[index], key, value)
                                   for key,value in journals[index].changes.items()
                                   if value is not AdmissionMap._DELETED
                                   and bases[index].get(key, _ABSENT_ADMISSION) is not value)
            for journal in journals: journal.commit()
            for lease in self._transient_leases:
                lease.observe(owned_ids, anchors)
            if _transient is not None:
                _transient.entries.extend(captured)
            return result
        finally:
            (self._owned.memo, self._owned.versions, self._origin_signatures, self._origin_blocks,
             self._nodes, self._blocks, self._inline_ir, self._plain_routines, self._plain_modules, self._python_units) = bases

    def prepare_transient(self, program):
        """Admit declaration-free dynamic code with unchanged live-unit limits."""
        if not self.FORCE_PYTHON_TRANSLATION or not self.OWNED_SNAPSHOT or self.ORIGIN_MUTATION_MONITOR:
            raise CompiledUnsupported(None, 'transient unit requires force owned translation')
        # The caller supplies a fresh parse_expression/parse_fragment result.
        # No declaration/import unit may acquire this shorter lifetime.
        seen=set()
        def validate(value):
            if id(value) in seen:return
            seen.add(id(value))
            kind=syntax_kind(value)
            if kind in (ast.Routine, ast.Import, ast.ServerInitializer):
                raise CompiledUnsupported(value, 'transient unit cannot declare or import')
            if kind in _SUPPORTED:
                for field in fields(value):
                    if field.name != 'token' and not (kind is ast.Literal and field.name == 'value'):
                        validate(getattr(value, field.name))
            elif type(value) in (list, tuple, OwnedList):
                for child in value:validate(child)
        validate(program)
        lease=_TransientAdmission(self)
        self.prepare(program, allow_reprepare=False, _transient=lease)
        lease.activate()
        return lease

    def _prepare(self, program, *, allow_reprepare=True, module_entry=False):
        self._inline_unit_bytes = 0
        if self.OWNED_SNAPSHOT:
            try:
                program = self._owned_program(program, allow_reprepare)
            except CompiledUnsupported:
                self.stats['rejected_units'] += 1
                raise
        nodes, blocks, active = {}, {}, set()
        structural = {id(program)}
        metadata_budget_charged = False
        count = 0
        reserved = set()
        prepared_counts = dict(compiled_node_functions=0, compiled_block_functions=0,
                               reused_node_plans=0, reused_block_plans=0)

        def reserve(kind, identity, node=None):
            registry = self._nodes if kind == 'node' else self._blocks
            if identity not in registry:
                reserved.add((kind, identity))
            if len(self._nodes) + len(self._blocks) + len(reserved) > self.MAX_REGISTRY_ENTRIES:
                raise CompiledUnsupported(node, 'aggregate compiled registry limit')

        def charge_metadata_source():
            nonlocal metadata_budget_charged
            if metadata_budget_charged: return
            size = len(_METADATA_BLOCK_SOURCE.encode('utf-8'))
            if size > self.MAX_INLINE_FUNCTION_BYTES:
                raise CompiledUnsupported(None, 'metadata entry function source budget')
            self._inline_unit_bytes += size
            if self._inline_unit_bytes > self.MAX_INLINE_UNIT_BYTES:
                raise CompiledUnsupported(None, 'inline unit source budget')
            metadata_budget_charged = True

        def walk(value, depth=0):
            nonlocal count, metadata_budget_charged
            if depth > self.MAX_DEPTH:
                raise CompiledUnsupported(program[0] if program else None,
                                          'compilation unit depth limit')
            if isinstance(value, ast.Node):
                kind = syntax_kind(value)
                if kind not in _SUPPORTED:
                    raise CompiledUnsupported(value, f'unsupported AST node {kind.__name__}')
                identity = id(value)
                if not allow_reprepare and self.has_node(value):
                    self.verify_node(value)
                if identity in active:
                    raise CompiledUnsupported(value, 'cyclic AST')
                if identity in nodes:
                    return
                reserve('node', identity, value)
                count += 1
                if count > self.MAX_NODES:
                    raise CompiledUnsupported(value, 'compilation unit node limit')
                active.add(identity)
                for name in ('body', 'handler', 'otherwise'):
                    child = getattr(value, name, None)
                    if type(child) is list or type(child) is OwnedList: structural.add(id(child))
                if kind is ast.If:
                    for _, child in value.branches: structural.add(id(child))
                for field in fields(value):
                    if field.name != 'token' and not (kind is ast.Literal and field.name == 'value'):
                        walk(getattr(value, field.name), depth + 1)
                active.remove(identity)
                if not allow_reprepare and self.has_node(value):
                    nodes[identity] = self._nodes[identity]
                    prepared_counts['reused_node_plans'] += 1
                else:
                    if self.FORCE_PYTHON_TRANSLATION:
                        function, tier = None, self._node_tier(value)
                        if kind is ast.Literal:function,tier=_translated_literal_value,'shared-leaf'
                        elif kind is ast.Name:function,tier=_translated_name_value,'shared-leaf'
                    else:
                        function, tier = self._lower_node(value)
                    prepared_counts['compiled_node_functions'] += function is not None and tier != 'shared-leaf'
                    nodes[identity] = _NodePlan(value, _signature(value), function, tier)
            elif type(value) in (list, tuple, OwnedList):
                identity = id(value)
                if identity in active:
                    raise CompiledUnsupported(None, 'cyclic AST sequence')
                active.add(identity)
                for item in value:
                    walk(item, depth + 1)
                active.remove(identity)
                if type(value) in (list, OwnedList) and all(isinstance(item, ast.Node) for item in value):
                    # Argument/default lists can also be registered. Only explicit
                    # VM block entry executes a list as statements.
                    reserve('block', identity, value[0] if value else None)
                    role = 'structural' if identity in structural else 'metadata'
                    existing = self._blocks.get(identity)
                    if (not allow_reprepare and existing is not None
                            and existing.statements is value
                            and (existing.role == 'structural' or role == 'metadata')):
                        _verify_block(value, existing.signature)
                        if existing.role == 'metadata' and not self.FORCE_PYTHON_TRANSLATION: charge_metadata_source()
                        blocks[identity] = existing
                        prepared_counts['reused_block_plans'] += 1
                    elif role == 'metadata':
                        if not self.FORCE_PYTHON_TRANSLATION: charge_metadata_source()
                        entries = tuple(value)
                        labels = {node.name.casefold(): i for i,node in enumerate(entries)
                                  if syntax_kind(node) is ast.Label}
                        blocks[identity] = _BlockPlan(value, self._block_signature(value),
                                                     None if self.FORCE_PYTHON_TRANSLATION else _METADATA_BLOCK_ENTRY, role, entries, labels)
                        self.stats['metadata_block_plans'] += 1
                    else:
                        blocks[identity] = _BlockPlan(value, self._block_signature(value),
                                                      None if self.FORCE_PYTHON_TRANSLATION else self._lower_block(value))
                        prepared_counts['compiled_block_functions'] += not self.FORCE_PYTHON_TRANSLATION
        try:
            if type(program) not in (list, OwnedList):
                raise CompiledUnsupported(None, 'compilation unit must be a statement list')
            walk(program)
            # The forced whole-program path never dispatches optional scalar
            # plans. Do not generate or charge a second unused implementation.
            if not self.FORCE_PYTHON_TRANSLATION:self._prepare_plain_routines(nodes)
            if self.FORCE_PYTHON_TRANSLATION:
                self._prepare_python_unit(program, nodes, blocks, module_entry)
            elif module_entry:self._prepare_plain_module(program)
        except CompiledUnsupported:
            self.stats['rejected_units'] += 1
            raise
        except RecursionError:
            self.stats['rejected_units'] += 1
            raise CompiledUnsupported(program[0] if program else None,
                                      'compiler recursion limit') from None
        self._nodes.update(nodes)
        self._blocks.update(blocks)
        for key, value in prepared_counts.items(): self.stats[key] += value
        self.stats['prepared_units'] += 1
        self.stats['prepared_nodes'] += len(nodes)
        return self

    @property
    def active_frames(self):
        return self._active_frames

    def release(self, *, retain_routines=False):
        """Drop plans at a quiescent owner boundary; counters remain available."""
        if self._active_frames:
            raise RuntimeError('cannot release compiled plans with active frames')
        retained = {}
        retained_versions = {}
        if retain_routines and self.OWNED_SNAPSHOT and not self.ORIGIN_MUTATION_MONITOR:
            # Routine declarations outlive a quiescent scheduler activation.
            # Keep their immutable versions, not executable temporary plans.
            visited = set()
            def retain(value):
                if id(value) in visited:
                    return
                if type(value) is tuple:
                    visited.add(id(value))
                    for item in value:
                        retain(item)
                    return
                if not is_owned(value):
                    return
                visited.add(id(value))
                original = syntax_origin(value)
                entry = self._owned.versions.get(id(value))
                if entry is None or entry[0] is not original or entry[1] is not value:
                    return
                retained_versions[id(value)] = entry
                latest = self._owned.memo.get(id(original))
                if id(original) not in retained or (latest is not None and latest[1] is value):
                    retained[id(original)] = entry
                if syntax_kind(value) in _SUPPORTED:
                    for field in fields(value):
                        if field.name != 'token' and not (syntax_kind(value) is ast.Literal and field.name == 'value'):
                            retain(getattr(value, field.name))
                elif type(value) is OwnedList:
                    for item in value:
                        retain(item)
            for mapping in (self.vm.routines, self.vm.server_routines):
                if type(mapping) is dict:
                    for original in mapping.values():
                        entry = self._owned.memo.get(id(original))
                        if entry is not None and entry[0] is original:
                            retain(entry[1])
        owned_ids = set(retained_versions)
        self._nodes = {key: plan for key, plan in self._nodes.items() if key in owned_ids}
        self._blocks = {key: plan for key, plan in self._blocks.items() if key in owned_ids}
        self._owned.clear()
        self._owned.memo.update(retained)
        self._owned.versions.update(retained_versions)
        self._origin_signatures.clear()
        self._origin_blocks.clear()
        self._inline_ir = {key: value for key, value in self._inline_ir.items() if key in owned_ids}
        self._plain_modules.clear()
        retained_units={}
        for block,unit in self._python_units.values():
            if id(block) in owned_ids and id(unit) not in retained_units:
                retained_units[id(unit)]=unit.retained(owned_ids)
        self._python_units={key:(block,unit) for unit in retained_units.values()
                            for key,(block,_) in unit.blocks.items()}
        self._plain_routines = {key: value for key, value in self._plain_routines.items() if key in owned_ids}
        self._fast_ready = None

    def has_node(self, node):
        if self.OWNED_SNAPSHOT:
            view = self._owned.existing(node)
            if view is not None: node = view
        plan = self._nodes.get(id(node))
        return plan is not None and plan.node is node

    def has_block(self, statements):
        if self.OWNED_SNAPSHOT:
            view = self._owned.existing(statements)
            if view is not None: statements = view
        plan = self._blocks.get(id(statements))
        return plan is not None and plan.statements is statements

    def has_executable_block(self, statements):
        """Distinguish admitted metadata from an explicitly compiled entry."""
        if not self.FORCE_PYTHON_TRANSLATION:
            return self.has_block(statements)
        view = self._owned.existing(statements)
        if view is None:
            return False
        plan = self._blocks.get(id(view))
        if plan is None or plan.statements is not view:
            return False
        key = tuple(id(node) for node in view)
        saved = self._python_units.get(key)
        if saved is None:
            return False
        block, unit = saved
        entry = unit.blocks.get(key)
        return (entry is not None and entry[0] is block and entry[1] is not None
                and len(block) == len(view)
                and all(a is b for a, b in zip(block, view)))

    def prepare_node(self, node):
        """Explicit late-unit preflight, e.g. a materialized default/expression."""
        wrapper = [node]
        self.prepare(wrapper, allow_reprepare=False)
        self._blocks.pop(id(self._owned.existing(wrapper) if self.OWNED_SNAPSHOT else wrapper), None)
        if self.OWNED_SNAPSHOT:
            self._owned.memo.pop(id(wrapper), None)
            self._origin_blocks.pop(id(wrapper), None)
        return self

    def ensure_node(self, node):
        if self.has_node(node):
            self.verify_node(node)
            return self
        return self.prepare_node(node)

    def prepare_block(self, statements):
        """Explicit late-unit preflight, never invoked as implicit fallback."""
        return self.prepare(statements, allow_reprepare=False)

    @staticmethod
    def _block_signature(statements):
        return tuple((id(type(node)), id(node)) for node in statements)

    def verify_node(self, node):
        """Validate admitted metadata also consumed without a node visit."""
        plan = None
        if self.OWNED_SNAPSHOT:
            if self.ORIGIN_MUTATION_MONITOR:
                original = syntax_origin(node)
                saved = self._origin_signatures.get(id(original))
                if saved is None or saved[0] is not original:
                    raise CompiledUnsupported(None, 'owned node has no origin fingerprint')
                _verify_node(original, saved[1])
            # An exact current plan already identifies the admitted view. Its
            # owned origin and this VM's version are still checked below.
            if not self.ORIGIN_MUTATION_MONITOR:
                plan = self._nodes.get(id(node))
            if plan is None or plan.node is not node:
                view = self._owned.existing(node)
                if view is not None: node = view
                plan = None
        if plan is None: plan = self._nodes.get(id(node))
        if plan is None or plan.node is not node:
            self.stats['unsupported_executions'] += 1
            raise CompiledUnsupported(node, 'node belongs to no prepared compilation unit')
        try:
            if self.OWNED_SNAPSHOT:
                self._verify_owned_identity(node)
            else:
                _verify_node(node, plan.signature)
        except CompiledUnsupported:
            self.stats['unsupported_executions'] += 1
            raise

    def _verify_owned_identity(self, value):
        # Normal writes to owned nodes/lists reject. Do not recursively hash
        # their immutable shape; opaque Literal contents intentionally stay live.
        # Unrestricted object/list protocol bypass is not a Python sandbox.
        provenance = owned_provenance(value)
        if provenance is None:
            raise CompiledUnsupported(None, 'unregistered owned execution view')
        original = provenance[0]
        entry = self._owned.versions.get(id(value))
        if entry is None or entry[0] is not original or entry[1] is not value:
            raise CompiledUnsupported(None, 'owned view belongs to no admitted unit')
        return original

    def _verify_active_plans(self):
        # OFF snapshots have already-admitted, sealed ancestors retained by
        # active frames. Rechecking them adds no live authority or epoch check.
        # FULL/default retain origin-mutation timing; current-node admission,
        # opaque boundaries and frame/release invariants remain independent.
        if self.OWNED_SNAPSHOT and not self.ORIGIN_MUTATION_MONITOR:
            return
        # Semantic adapters may inspect target/callee/parameter metadata without
        # visiting it. Validate ancestors before returning any child value to
        # such an adapter. Suspended frames are checked conservatively as well.
        for plan in self._active_plans:
            if plan.tier == 'semantic-helper' or syntax_kind(plan.node) is ast.ExpressionStatement:
                # FULL checks original ancestor metadata before child values
                # reach an adapter, even when fast mode is disabled by context.
                self.verify_node(plan.node)

    def fast_available(self, *, refresh=False):
        if not refresh and self._fast_ready is not None:
            return self._fast_ready
        from . import runtime as R
        vm = self.vm
        self._fast_ready = (self.FAST_INLINE and type(vm) is R.Interpreter
                and all(vars(R.Interpreter).get(name) is original
                        for name, original in zip(_TRUSTED_ABI_NAMES, _TRUSTED_ABI))
                and all(vars(R.Interpreter).get(name) is R._HYBRID_RUNTIME_HOOKS[name]
                        for name in ('locals', '_has_module_context'))
                and vm._configuration_runtime is None
                and type(vm.imports) is dict
                and all(type(key) is str for key in vm.imports)
                and type(vm.module_names) is set
                and all(type(key) is str for key in vm.module_names)
                and type(vm.variables) is dict
                and all(type(key) is str for key in vm.variables)
                and (vm.locals is None or (type(vm.locals) is dict and all(type(key) is str for key in vm.locals)))
                and not any(name in vars(vm) for name in (
                    'compiled_before', 'compiled_after', 'compiled_exception',
                    'semantic_name', 'semantic_assign', 'set_variable')))
        return self._fast_ready

    def fast_name(self, name):
        """Return a plain stored value, never dereference or resolve host modules."""
        vm = self.vm
        local = vm.locals
        if not self.fast_available() or (local is not None and type(local) is not dict): return False, None
        if local is not None and name in local:
            value = local[name]
            return (False, None) if isinstance(value, self._reference_type) else (True, value)
        if vm._has_module_context and name in vm.variables and (local is None or name in vm.module_names):
            return True, vm.variables[name]
        return False, None

    def fast_assignable(self, name):
        local = self.vm.locals
        return (self.fast_available() and
                (local is None or (type(local) is dict and
                 not isinstance(local.get(name), self._reference_type))))

    def invalidate_counter_slots(self):
        # Scope declarations are not host callbacks but can shadow a module slot.
        self._opaque_epoch += 1

    def counter_slot(self, name):
        """Read/write-identical plain storage, never an authorization cache."""
        vm = self.vm
        epoch = self._opaque_epoch
        if not self.fast_available(refresh=True): return None, epoch
        local = vm.locals
        if type(vm.imports) is not dict or any(type(key) is not str for key in vm.imports):
            return None, epoch
        if type(vm.module_names) is not set or any(type(key) is not str for key in vm.module_names):
            return None, epoch
        if local is None and name in vm.imports: return None, epoch
        if local is not None and name in local:
            scope = local
        elif vm._has_module_context and name in vm.variables and (local is None or name in vm.module_names):
            scope = vm.variables
        else:
            return None, epoch
        write_scope = (vm.variables if local is None or
                       (vm._has_module_context and name in vm.module_names and name not in local)
                       else local)
        if scope is not write_scope or isinstance(scope[name], self._reference_type):
            return None, epoch
        return scope, epoch

    def assign_value(self, name, value):
        opaque = not self.fast_assignable(name.casefold())
        if opaque: self.verify_all()
        self.vm.set_variable(name, value)
        if opaque: self.verify_all()

    def counter_value(self, node):
        opaque = not self.fast_assignable(node.name.casefold())
        if opaque: self.verify_all()
        result = self.vm.semantic_name(node)
        if opaque: self.verify_all()
        return result

    def verify_all(self):
        """Opaque callback/host/resumption boundary, not a security decision cache."""
        self._opaque_epoch += 1
        self.fast_available(refresh=True)
        if self.OWNED_SNAPSHOT:
            if self.ORIGIN_MUTATION_MONITOR:
                for original, expected in tuple(self._origin_signatures.values()):
                    self.stats['origin_monitor_checks'] += 1
                    _verify_node(original, expected)
                for original, expected in tuple(self._origin_blocks.values()):
                    self.stats['origin_monitor_checks'] += 1
                    _verify_block(original, expected)
            return
        for plan in tuple(self._nodes.values()):
            self.verify_node(plan.node)
        for plan in tuple(self._blocks.values()):
            _verify_block(plan.statements, plan.signature)

    def inline_enter(self, node):
        plan = self._nodes.get(id(node))
        if plan is None or plan.node is not node:
            self.verify_node(node)
        fast = self.fast_available()
        kind_type = syntax_kind(node)
        opaque = (kind_type in _HELPERS or kind_type in
                  (ast.Call, ast.ExpressionStatement, ast.Await, ast.ForEach))
        stored_name = (False, None)
        if kind_type is ast.Name:
            stored_name = self.fast_name(node.name.casefold())
            if stored_name[0]: opaque = False
        if kind_type is ast.Assign and syntax_kind(node.target) is ast.Name and self.fast_assignable(node.target.name.casefold()): opaque = False
        if not fast:
            self._verify_active_plans()
            self.verify_node(node)
        elif opaque:
            self.verify_all()
        if self.DETAILED_INLINE_STATS:
            key = 'helper_executions' if plan.tier == 'semantic-helper' else 'emitted_executions'
            self.stats[key] += 1
            kind = syntax_kind(node).__name__
            self.stats['node_kinds'][kind] = self.stats['node_kinds'].get(kind, 0) + 1
        if fast and not opaque:
            return (None, stored_name[1]) if kind_type is ast.Name else None
        self._active_frames += 1
        self._active_plans.append(plan)
        return plan, fast, opaque

    def inline_exit(self, ticket, *, unwinding=False):
        if ticket is None or ticket[0] is None: return
        plan, fast, opaque = ticket
        try:
            if not unwinding:
                if fast and opaque:
                    self.verify_all()
                elif not fast:
                    self.verify_node(plan.node)
                    self._verify_active_plans()
        finally:
            for index in range(len(self._active_plans) - 1, -1, -1):
                if self._active_plans[index] is plan:
                    del self._active_plans[index]
                    break
            self._active_frames -= 1

    def run_node(self, node):
        if self.FORCE_PYTHON_TRANSLATION:
            return (yield from self._run_python_node(node))
        if self.OWNED_SNAPSHOT: node = self.execution_view(node)
        if self.INLINE and self.FAST_INLINE and not self._active_frames:
            self.verify_all()
        try:
            self._verify_active_plans()
        except CompiledUnsupported:
            self.stats['unsupported_executions'] += 1
            raise
        plan = self._nodes.get(id(node))
        if plan is None or plan.node is not node:
            self.stats['unsupported_executions'] += 1
            raise CompiledUnsupported(node, 'node belongs to no prepared compilation unit')
        self.verify_node(node)
        if plan.function is None:
            self.stats['unsupported_executions'] += 1
            raise CompiledUnsupported(node, 'syntax-only node cannot execute directly')
        if self.INLINE:
            self.stats['inline_fragments'] += 1
            return (yield from plan.function(self.vm))
        key = 'helper_executions' if plan.tier == 'semantic-helper' else 'emitted_executions'
        self.stats[key] += 1
        kind = syntax_kind(node).__name__
        self.stats['node_kinds'][kind] = self.stats['node_kinds'].get(kind, 0) + 1
        self._active_frames += 1
        self._active_plans.append(plan)
        try:
            result = yield from plan.function(self.vm)
            self._verify_active_plans()
            return result
        except CompiledUnsupported:
            self.stats['unsupported_executions'] += 1
            raise
        finally:
            # Async tasks may resume in a different order from admission.
            for index in range(len(self._active_plans) - 1, -1, -1):
                if self._active_plans[index] is plan:
                    del self._active_plans[index]
                    break
            self._active_frames -= 1

    def run_block(self, statements, *, plain_routine=None):
        if self.FORCE_PYTHON_TRANSLATION:
            return (yield from self._run_python_block(statements))
        if self.OWNED_SNAPSHOT:
            view = self._owned.existing(statements)
            if view is None:
                self.prepare_block(statements)
                view = self._owned.existing(statements)
            statements = view
        if self.INLINE and self.FAST_INLINE:
            self.verify_all()
        plan = self._blocks.get(id(statements))
        if plan is None or plan.statements is not statements:
            self.stats['unsupported_executions'] += 1
            raise CompiledUnsupported(statements[0] if statements else None,
                                      'block belongs to no prepared compilation unit')
        self._check_block_plan(plan)
        if plan.function is None:
            raise CompiledUnsupported(statements[0] if statements else None, 'legacy block executable was not prepared')
        self.stats['block_executions'] += 1
        if plan.role == 'metadata': self.stats['metadata_block_executions'] += 1
        elif self.INLINE: self.stats['inline_blocks'] += 1
        self._active_frames += 1
        try:
            plain = self._plain_routine_plan(plan, plain_routine)
            if plain is not None:
                function, values, is_generator, prefix_only = plain
                result = function(self.vm, *values)
                if is_generator:
                    result = yield from result
                counter = 'plain_prefix_calls' if prefix_only else 'plain_routine_calls'
                self.stats[counter] = self.stats.get(counter, 0) + 1
                from .runtime import _Return
                raise _Return(result)
            self._force_translation_gap(statements[0] if statements else None, 'block-adapter')
            self.stats['plain_adapter_blocks'] = self.stats.get('plain_adapter_blocks', 0) + 1
            if plan.role == 'metadata':
                return (yield from plan.function(self.vm, self, plan))
            return (yield from plan.function(self.vm))
        except CompiledUnsupported:
            self.stats['unsupported_executions'] += 1
            raise
        finally:
            self._active_frames -= 1

    def _prepare_python_unit(self, program, nodes, blocks, module_entry):
        from .python_translation_blocks import prepare_blocks, UnsupportedTranslation
        from .python_translation_expressions import UnsupportedExpression
        if not self.OWNED_SNAPSHOT:
            raise CompiledUnsupported(None, 'force translator requires owned snapshot')
        selected_blocks=[plan.statements for plan in blocks.values() if plan.role=='structural']
        entry_keys={tuple(id(node) for node in program)}
        for plan in nodes.values():
            if syntax_kind(plan.node) in (ast.Routine,ast.ServerInitializer):
                entry_keys.add(tuple(id(node) for node in plan.node.body))
        if not any(block is program for block in selected_blocks):selected_blocks.append(program)
        if module_entry:
            selected=[node for node in program if syntax_kind(node) is not ast.Import
                      and syntax_kind(node) is not ast.ServerInitializer
                      and not (syntax_kind(node) is ast.Var and node.execution_context=='server')]
            entry_keys.add(tuple(id(node) for node in selected))
            cached=self._python_units.get(tuple(id(node) for node in selected))
            if cached is not None and len(cached[0])==len(selected) and all(a is b for a,b in zip(cached[0],selected)):
                self._verify_owned_identity(cached[0]);selected_blocks.append(cached[0])
            else:selected_blocks.append(self._owned.freeze(selected))
        for plan in nodes.values():
            if syntax_kind(plan.node) in (ast.Import,ast.Execute):
                if len(self._owned.versions)>=self.MAX_REGISTRY_ENTRIES:
                    raise CompiledUnsupported(plan.node,'force singleton registry budget')
                entry_keys.add((id(plan.node),))
                cached=self._python_units.get((id(plan.node),))
                if cached is not None and len(cached[0])==1 and cached[0][0] is plan.node:
                    self._verify_owned_identity(cached[0]);selected_blocks.append(cached[0])
                else:selected_blocks.append(self._owned.freeze([plan.node]))
        expression_kinds=(ast.Literal,ast.Name,ast.Group,ast.Unary,ast.Binary,ast.Conditional,
                          ast.Attribute,ast.Index,ast.Call,ast.New,ast.DynamicNew,ast.Await)
        roots=[plan.node for plan in nodes.values() if any(syntax_kind(plan.node) is kind for kind in expression_kinds)]
        retained={id(unit):unit for _,unit in self._python_units.values()}
        available=min(self.MAX_INLINE_UNIT_BYTES-self._inline_unit_bytes,
                      self.MAX_PLAIN_SOURCE_BYTES-self._plain_source_bytes()-sum(unit.source_bytes for unit in retained.values()))
        try:unit=prepare_blocks(selected_blocks,roots,max_source_bytes=available,max_function_bytes=self.MAX_INLINE_FUNCTION_BYTES,entry_keys=entry_keys,owned_leaves=True,compact_control=len(nodes)>10_000,max_bindings=self.MAX_REGISTRY_ENTRIES-sum(u.binding_count for u in retained.values()))
        except (UnsupportedTranslation,UnsupportedExpression) as error:
            gaps=self.stats.setdefault('force_translation_gaps',{})
            reason='admission:'+str(error);gaps[reason]=gaps.get(reason,0)+1
            raise CompiledUnsupported(program[0] if program else None,str(error)) from None
        if (len(self._python_units)+len(unit.blocks)+len(unit.statements or {})
                +sum(len(u.statements or {}) for u in retained.values())>self.MAX_REGISTRY_ENTRIES):
            raise CompiledUnsupported(None,'force translator registry budget')
        self._inline_unit_bytes+=unit.source_bytes
        for key,(block,_) in unit.blocks.items():self._python_units[key]=(block,unit)

    def _python_leaf_operation(self, node):
        identity=node if type(node) is int else id(node)
        plan=self._nodes.get(identity)
        if plan is None or plan.tier!='shared-leaf':return None
        if type(node) is not int and plan.node is not node:return None
        return plan.node,plan.function

    def _python_expression_execution(self, node):
        # Resolve only source-bound code already admitted in this caller VM.
        view=self._owned.existing(node)
        if view is None:return None
        for _,unit in self._python_units.values():
            item=unit.expressions.functions.get(id(view))
            if item is not None and item[0] is view:
                return unit.bind(self).expressions,view
        return None

    def _run_python_node(self,node):
        view=self.execution_view(node)
        leaf=self._python_leaf_operation(view)
        if leaf is not None:
            self._verify_active_plans();self.verify_node(view)
            kinds=self.stats.setdefault('python_translated_node_kinds',{})
            kind=syntax_kind(view).__name__;kinds[kind]=kinds.get(kind,0)+1
            self._active_frames += 1
            try:
                return leaf[1](self.vm,view)
            finally:
                self._active_frames -= 1
        resolved=self._python_expression_execution(view)
        if resolved is not None:
            execution,view=resolved
            execution.guard(view)
            self._active_frames += 1
            try:
                return (yield from execution.plan.functions[id(view)][1](execution))
            finally:
                self._active_frames -= 1
        saved=self._python_units.get((id(view),))
        if saved is not None:
            block,unit=saved
            self.verify_all();self._verify_owned_identity(block)
            execution=unit.bind(self);execution.outer_node=view
            self._active_frames+=1
            try:return (yield from execution.block((id(view),)))
            finally:self._active_frames-=1
        self._force_translation_gap(view,'node-adapter')

    def _run_python_block(self, statements):
        owned=tuple(self._owned.existing(node) for node in statements)
        key=tuple(id(node) for node in owned)
        saved=self._python_units.get(key)
        if saved is None:
            self._force_translation_gap(statements[0] if statements else None,'unprepared-block')
        block,unit=saved
        if len(block)!=len(owned) or any(a is not b for a,b in zip(block,owned)):
            raise CompiledUnsupported(None,'force translated block provenance mismatch')
        self.verify_all();self._verify_owned_identity(block)
        self._active_frames+=1
        try:return (yield from unit.bind(self).block(key))
        except Exception as error:
            from .python_translation_expressions import UnsupportedExpression
            if isinstance(error,UnsupportedExpression):
                gaps=self.stats.setdefault('force_translation_gaps',{})
                reason='expression:'+str(error)
                gaps[reason]=gaps.get(reason,0)+1
                raise CompiledUnsupported(block[0] if block else None,reason) from None
            raise
        finally:self._active_frames-=1

    def _plain_source_bytes(self):
        return (sum(len(entry[1].source.encode()) for entry in self._plain_routines.values() if entry[1] is not None)
                + sum(plan.source_bytes for plan in self._plain_modules.values()))

    def _prepare_plain_module(self, program):
        if not self.vm.compiled_plain_routines or not self.OWNED_SNAPSHOT or self.ORIGIN_MUTATION_MONITOR:return
        if len(self._plain_modules)>=self.MAX_REGISTRY_ENTRIES or len(self._owned.versions)>=self.MAX_REGISTRY_ENTRIES:return
        from .plain_modules import lower_module
        from .plain_routines import Ineligible
        selected=[node for node in program if syntax_kind(node) is not ast.Import
                  and syntax_kind(node) is not ast.ServerInitializer
                  and not (syntax_kind(node) is ast.Var and node.execution_context=='server')]
        used=self._plain_source_bytes()
        available=min(self.MAX_INLINE_FUNCTION_BYTES,self.MAX_INLINE_UNIT_BYTES-self._inline_unit_bytes,
                      self.MAX_PLAIN_SOURCE_BYTES-used)
        if available<=0:return
        bases=(self._owned.memo,self._owned.versions)
        journals=tuple(AdmissionMap(base) for base in bases)
        self._owned.memo,self._owned.versions=journals
        try:
            block=self._owned.freeze(selected)
            try:plan=lower_module(block,max_source_bytes=available)
            except Ineligible:return
            for journal in journals:journal.commit()
        finally:self._owned.memo,self._owned.versions=bases
        self._inline_unit_bytes+=plan.source_bytes
        self._plain_modules[tuple(id(node) for node in block)]=plan

    def run_module(self, statements):
        """Only runtime's post-preflight module entry calls this optional path."""
        if self.FORCE_PYTHON_TRANSLATION:
            return (yield from self._run_python_block(statements))
        import sys
        vm=self.vm
        snapshot=self._plain_scope_snapshot()
        if (self._active_frames or not self.INLINE or not self.FAST_INLINE or self.DETAILED_INLINE_STATS
                or snapshot is None or snapshot[0] is not None
                or sys.gettrace() is not None or sys.getprofile() is not None
                or not vm.compiled_plain_routines or not self.fast_available(refresh=True)):
            return (yield from vm.block(statements))
        owned=tuple(self._owned.existing(node) for node in statements)
        plan=self._plain_modules.get(tuple(id(node) for node in owned))
        if plan is None or len(plan.block)!=len(owned) or any(a is not b for a,b in zip(plan.block,owned)):
            return (yield from vm.block(statements))
        if not plan.storage_eligible(vm.variables,vm.imports):return (yield from vm.block(statements))
        self.verify_all();self._verify_owned_identity(plan.block)
        if any(not self.has_node(node) for node in plan.block):return (yield from vm.block(statements))
        self._active_frames+=1
        self.stats['plain_module_entries']=self.stats.get('plain_module_entries',0)+1
        try:
            result=plan.function(vm,vm.variables)
            self.stats['plain_module_completions']=self.stats.get('plain_module_completions',0)+1
            return result
        except BaseException:
            self.stats['plain_module_errors']=self.stats.get('plain_module_errors',0)+1
            raise
        finally:self._active_frames-=1

    def _prepare_plain_routines(self, nodes):
        """Optional lowering is part of transactional admission, not execution.

        Source generation is charged to the same unit-byte counter. Exhausting
        optional room retains the already admitted compiled adapter instead.
        """
        if not self.vm.compiled_plain_routines or not self.OWNED_SNAPSHOT or self.ORIGIN_MUTATION_MONITOR: return
        from .plain_routines import lower, Ineligible
        used = self._plain_source_bytes()
        for plan in nodes.values():
            routine = plan.node
            if syntax_kind(routine) is not ast.Routine: continue
            cached = self._plain_routines.get(id(routine))
            if cached is not None and cached[0] is routine:
                if cached[1] is not None:
                    size = len(cached[1].source.encode())
                    if (size > self.MAX_INLINE_FUNCTION_BYTES
                            or size > self.MAX_INLINE_UNIT_BYTES - self._inline_unit_bytes
                            or used > self.MAX_PLAIN_SOURCE_BYTES):
                        self._plain_routines[id(routine)] = (routine, None)
                        used -= size
                    else:
                        self._inline_unit_bytes += size
                continue
            available = min(self.MAX_INLINE_FUNCTION_BYTES, self.MAX_PLAIN_SOURCE_BYTES - used,
                            self.MAX_INLINE_UNIT_BYTES - self._inline_unit_bytes)
            try: lowered = lower(routine, max_source_bytes=max(0, available))
            except Ineligible: lowered = None
            if lowered is not None:
                size = len(lowered.source.encode())
                used += size
                self._inline_unit_bytes += size
            self._plain_routines[id(routine)] = (routine, lowered)

    def _plain_routine_plan(self, block, routine):
        # Host tracing/profiling may observe or mutate the live VM scope on
        # Python calls/lines. Do not capture detached local slots in that mode.
        import sys
        if sys.gettrace() is not None or sys.getprofile() is not None:
            return None
        if (not self.vm.compiled_plain_routines or not self.OWNED_SNAPSHOT or self.ORIGIN_MUTATION_MONITOR
                or not self._fast_ready or self.DETAILED_INLINE_STATS
                or routine is None or not is_owned(routine)
                or syntax_kind(routine) is not ast.Routine
                or routine.body is not block.statements or block.role == 'metadata'):
            return None
        # Cross-context activation may carry the parent engine's declaration
        # while this child has separately admitted the body. That is not an
        # eligible local plain plan; retain the existing compiled body adapter.
        provenance = self._owned.versions.get(id(routine))
        if provenance is None or provenance[1] is not routine:
            return None
        if self._plain_scope_snapshot() is None:return None
        self._verify_owned_identity(routine)
        cached = self._plain_routines.get(id(routine))
        if cached is None or cached[0] is not routine: return None
        lowered = cached[1]
        if lowered is None: return None
        # Structural code is reusable; live storage and policy eligibility are not.
        local = self.vm.locals
        if type(local) is not dict: return None
        if any(name in self.vm.module_names or name in self.vm.imports for name in lowered.names): return None
        values = tuple(local.get(name) for name in lowered.parameters)
        if any(not any(type(value) is scalar for scalar in (Decimal, bool, str, type(None)))
               for value in values): return None
        return lowered.function, values, lowered.generator, lowered.prefix_only

    def _plain_scope_snapshot(self):
        """Side-effect-free guard before touching replaceable scope accessors."""
        from . import runtime as R
        from .async_runtime import Scheduler, ExecutionContext
        vm=self.vm
        if type(vm) is not R.Interpreter:return None
        for cls,_,_ in R._PLAIN_STORAGE_ABI:
            if any(type(key) is not str for key in vars(cls)):return None
        class_fields=vars(R.Interpreter)
        if (class_fields.get('__hash__',object.__hash__) is not object.__hash__
                or class_fields.get('__eq__',object.__eq__) is not object.__eq__):return None
        def storage(value,cls):
            if type(value) is not cls:return None
            namespace=vars(cls)
            if (namespace.get('__getattribute__',object.__getattribute__) is not object.__getattribute__
                    or '__getattr__' in namespace):return None
            for registered,descriptor,mro in R._PLAIN_STORAGE_ABI:
                if cls is registered:
                    current=type.__getattribute__(cls,'__mro__')
                    if (len(current)!=len(mro) or any(a is not b for a,b in zip(current,mro))
                            or namespace.get('__dict__') is not descriptor):return None
                    fields=object.__getattribute__(value,'__dict__')
                    if type(fields) is not dict or any(type(key) is not str for key in fields):return None
                    return fields
            return None
        vm_fields=storage(vm,R.Interpreter)
        if vm_fields is None:return None
        for name,original in zip(('locals','_context_stack','_module_context_stack'),R._PLAIN_SCOPE_ABI):
            if vars(R.Interpreter).get(name) is not original:return None
        scheduler=vm_fields.get('_scheduler')
        if type(scheduler) is not Scheduler or 'active_context' in vars(Scheduler):return None
        if any(name in vars(ExecutionContext) for name in ('locals','context_stack','module_context_stack')):
            return None
        scheduler_fields=storage(scheduler,Scheduler)
        if scheduler_fields is None:return None
        context=scheduler_fields.get('active_context')
        if type(context) is not ExecutionContext:return None
        fields=storage(context,ExecutionContext)
        if fields is None:return None
        scopes=fields.get('locals');sides=fields.get('context_stack');modules=fields.get('module_context_stack')
        if type(scopes) is not dict or type(sides) is not list or type(modules) is not list:return None
        # Exact dict lookup can still hash the VM or compare colliding hostile
        # keys. Scan identities, and reject keys unsafe for subsequent trusted
        # runtime accessors which use normal dictionary lookup.
        scope=None
        for key,value in scopes.items():
            if type(key) is not R.Interpreter:return None
            if key is vm:scope=value
        return scope,context,tuple(sides),tuple(modules)

    def _resume_plain_segment(self, routine, segment, saved_frame):
        """Fresh live eligibility after an opaque statement, never replay it."""
        import sys
        def denied(reason):
            key='plain_resume_denied_'+reason
            self.stats[key]=self.stats.get(key,0)+1
            return None
        vm=self.vm
        if sys.gettrace() is not None or sys.getprofile() is not None:return denied('instrumentation')
        current=self._plain_scope_snapshot()
        if current is None or saved_frame is None:return denied('context')
        scope,context,sides,modules=current
        old_scope,old_context,old_sides,old_modules=saved_frame
        if (scope is not old_scope or context is not old_context
                or len(sides)!=len(old_sides) or len(modules)!=len(old_modules)
                or any(a is not b for a,b in zip(sides,old_sides))
                or any(a is not b for a,b in zip(modules,old_modules))):return denied('context')
        if vars(vm).get('_compiled_plain_routines') is not True or not self.fast_available(refresh=True):
            return denied('policy')
        root=self._plain_routines.get(id(routine))
        if root is None or root[0] is not routine or root[1] is None:return denied('provenance')
        if not any(segment is item for item in root[1].segments):return denied('provenance')
        self.verify_all();self._verify_owned_identity(routine)
        if type(scope) is not dict or any(type(key) is not str for key in scope):return denied('scope')
        if any(name in vm.module_names or name in vm.imports for name in segment.names):return denied('collision')
        if any(name not in scope for name in segment.parameters):return denied('missing')
        values=tuple(scope[name] for name in segment.parameters)
        if any(not any(type(value) is scalar for scalar in (Decimal,bool,str,type(None))) for value in values):
            return denied('type')
        self.stats['plain_segment_entries']=self.stats.get('plain_segment_entries',0)+1
        return segment.function,values,segment.generator

    def _check_block_plan(self, plan):
        if self.OWNED_SNAPSHOT:
            original = self._verify_owned_identity(plan.statements)
            if self.ORIGIN_MUTATION_MONITOR:
                saved = self._origin_blocks.get(id(original))
                if saved is None:
                    raise CompiledUnsupported(None, 'owned block has no origin fingerprint')
                _verify_block(original, saved[1])
        else:
            _verify_block(plan.statements, plan.signature)

    @staticmethod
    def _compile(lines, bindings):
        from . import runtime as R
        from .safe_mode import require_transfer
        from .database_transactions import forbid_transfer
        source = 'def generated(vm):\n    if False:\n        yield None\n'
        if 'n' in bindings:
            parent = bindings['n']
            expected = _signature(parent)
            def evaluate(vm, child):
                _verify_node(parent, expected)
                result = yield from vm._visit(child)
                _verify_node(parent, expected)
                return result
            def block(vm, body):
                _verify_node(parent, expected)
                result = yield from vm.block(body)
                _verify_node(parent, expected)
                return result
            bindings = {**bindings, 'evaluate': evaluate, 'block': block,
                        'check_node': _verify_node, 'expected': expected}
            lines = [line.replace('vm._visit(', 'evaluate(vm, ').replace('vm.block(', 'block(vm, ')
                     for line in lines]
        source += '\n'.join('    ' + line for line in lines) + '\n'
        namespace = {'R': R, 'Decimal': Decimal, 'require_transfer': require_transfer,
                     'forbid_transfer': forbid_transfer, **bindings}
        module = python_ast.parse(source, filename='<bsl-compiled>')
        exec(compile(module, '<bsl-compiled>', 'exec'), namespace)
        return namespace['generated']

    def _node_tier(self, node):
        """Validate shared semantic dependencies without generating unused code."""
        kind = syntax_kind(node)
        if kind in _SYNTAX_ONLY:
            return 'syntax-only'
        if kind in _HELPERS and not callable(getattr(self.vm, _HELPERS[kind], None)):
            raise CompiledUnsupported(node, f'missing semantic adapter {_HELPERS[kind]}')
        tier = 'semantic-helper' if kind in _HELPERS or kind is ast.Call else 'emitted'
        if kind is ast.ExpressionStatement:
            expression = node.expression
            while syntax_kind(expression) is ast.Group:
                expression = expression.expression
            if syntax_kind(expression) is ast.Call: tier = 'semantic-helper'
        return tier

    def _lower_node(self, node):
        kind = syntax_kind(node)
        if kind in _SYNTAX_ONLY:
            return None, 'syntax-only'
        if self.INLINE:
            if kind in _HELPERS and not callable(getattr(self.vm, _HELPERS[kind], None)):
                raise CompiledUnsupported(node, f'missing semantic adapter {_HELPERS[kind]}')
            from .compiled_inline import Emitter
            tier = 'semantic-helper' if kind in _HELPERS or kind is ast.Call else 'emitted'
            if kind is ast.ExpressionStatement:
                expression = node.expression
                while syntax_kind(expression) is ast.Group:
                    expression = expression.expression
                if syntax_kind(expression) is ast.Call: tier = 'semantic-helper'
            return Emitter(self).compile(node), tier
        bindings = {'n': node}
        tier = 'emitted'
        if kind in _HELPERS:
            method = _HELPERS[kind]
            if not callable(getattr(self.vm, method, None)):
                raise CompiledUnsupported(node, f'missing semantic adapter {method}')
            tier = 'semantic-helper'
            lines = [f'return vm.{method}(n)' if kind in (ast.Name, ast.Import) else
                     f'return (yield from vm.{method}(n))']
        elif kind is ast.Literal:
            bindings['value'] = node.value
            lines = ['return value']
        elif kind is ast.Group:
            bindings['child'] = node.expression
            lines = ['return (yield from vm._visit(child))']
        elif kind is ast.Unary:
            bindings.update(operand=node.operand, operator=node.operator)
            lines = ['value = yield from vm._visit(operand)',
                     'return R.unary_value(operator, value)']
        elif kind is ast.Binary:
            bindings.update(left=node.left, right=node.right, operator=node.operator)
            lines = ['a = yield from vm._visit(left)']
            if node.operator == 'AND':
                lines += ['if not R.boolean(a):', '    return False',
                          'return R.boolean((yield from vm._visit(right)))']
            elif node.operator == 'OR':
                lines += ['if R.boolean(a):', '    return True',
                          'return R.boolean((yield from vm._visit(right)))']
            else:
                lines += ['b = yield from vm._visit(right)',
                          'return R.binary_values(operator, a, b)']
        elif kind is ast.Conditional:
            bindings.update(condition=node.condition, yes=node.when_true, no=node.when_false)
            lines = ['if R.boolean((yield from vm._visit(condition))):',
                     '    return (yield from vm._visit(yes))',
                     'return (yield from vm._visit(no))']
        elif kind is ast.Call:
            tier = 'semantic-helper'
            lines = ['return (yield from vm.call(n, require_value=True))']
        elif kind is ast.ExpressionStatement:
            expression = node.expression
            while syntax_kind(expression) is ast.Group:
                expression = expression.expression
            if syntax_kind(expression) is ast.Call:
                bindings['call'] = expression
                tier = 'semantic-helper'
                lines = ['return (yield from vm.call(call, require_value=False))']
            else:
                bindings['expression'] = node.expression
                lines = ['return (yield from vm._visit(expression))']
        elif kind is ast.If:
            lines = []
            for index, (condition, body) in enumerate(node.branches):
                bindings[f'condition{index}'] = condition
                bindings[f'body{index}'] = body
                lines += [f'if R.boolean((yield from vm._visit(condition{index}))):',
                          f'    yield from vm.block(body{index})', '    return None']
            bindings['otherwise'] = node.otherwise
            lines += ['yield from vm.block(otherwise)', 'return None']
        elif kind in (ast.For, ast.ForEach, ast.While):
            bindings['body'] = node.body
            if kind is ast.For:
                bindings.update(start=node.start, end=node.end, name=node.name.casefold(),
                                counter=ast.Name(node.token, node.name.casefold()))
                lines = ['first = R.require_number((yield from vm._visit(start)))',
                         'last = R.require_number((yield from vm._visit(end)))',
                         'vm.set_variable(name, first)',
                         'while R.require_number(vm.semantic_name(counter)) <= last:']
            elif kind is ast.ForEach:
                bindings.update(collection=node.collection, name=node.name)
                lines = ['value = yield from vm._visit(collection)',
                         'for item in vm.compiled_iterable(value):',
                         '    vm.set_variable(name, item)']
            else:
                bindings['condition'] = node.condition
                lines = ['while R.boolean((yield from vm._visit(condition))):']
            lines += ['    try:', '        yield from vm.block(body)',
                      '    except R._Continue:', '        pass',
                      '    except R._Break:', '        break']
            if kind is ast.For:
                lines += ['    vm.set_variable(name, R.require_number(vm.semantic_name(counter)) + Decimal(1))']
            lines += ['return None']
        elif kind is ast.Break:
            lines = ['raise R._Break']
        elif kind is ast.Continue:
            lines = ['raise R._Continue']
        elif kind is ast.Return:
            if node.value is None:
                lines = ['raise R._Return(None)']
            else:
                bindings['value'] = node.value
                lines = ['raise R._Return((yield from vm._visit(value)))']
        elif kind is ast.Try:
            bindings.update(body=node.body, handler=node.handler)
            lines = ['try:', '    yield from vm.block(body)',
                     'except R.BSLRuntimeError as error:',
                     '    for index in range(len(vm._handled_errors)):',
                     '        vm._handled_errors[index] = None',
                     '    vm._handled_errors.append(error)',
                     '    try:', '        yield from vm.block(handler)',
                     '    finally:', '        vm._handled_errors.pop()', 'return None']
        elif kind is ast.Goto:
            lines = ['raise R._Goto(n)']
        elif kind in (ast.Label, ast.Routine):
            lines = ['return None']
        elif kind is ast.Var:
            bindings['names'] = tuple(node.names)
            lines = ['if vm.locals is None and any(name.casefold() in vm.imports for name in names):',
                     '    raise ValueError("Имя импорта конфликтует с объявлением")',
                     'for name in names:',
                     '    (vm.variables if vm.locals is None else vm.locals).setdefault(name.casefold(), None)',
                     'return None']
        elif kind is ast.Await:
            bindings['operand'] = node.operand
            lines = ["require_transfer('Await')", 'forbid_transfer(vm._transaction_backend())',
                     'value = yield from vm._visit(operand)', 'result = yield R.AwaitRequest(value)',
                     'check_node(n, expected)', 'return result']
        else:
            raise CompiledUnsupported(node, f'no lowering for {kind.__name__}')
        return self._compile(lines, bindings), tier

    def _lower_block(self, statements):
        if self.INLINE:
            from .compiled_inline import Emitter
            return Emitter(self).compile(statements, block=True)
        bindings = {f'node{i}': node for i, node in enumerate(statements)}
        labels = {node.name.casefold(): i for i, node in enumerate(statements)
                  if syntax_kind(node) is ast.Label}
        bindings.update(statements=statements, expected=self._block_signature(statements),
                        check_block=_verify_block)
        lines = ['result = None']
        if not labels:
            for i in range(len(statements)):
                lines += ['check_block(statements, expected)',
                          f'result = yield from vm._visit(node{i})']
        else:
            bindings['labels'] = labels
            lines += ['pc = 0', 'while True:', '    check_block(statements, expected)',
                      f'    if pc >= {len(statements)}:', '        break', '    try:']
            for i in range(len(statements)):
                lines += [f'        {"if" if i == 0 else "elif"} pc == {i}:',
                          f'            result = yield from vm._visit(node{i})']
            lines += ['    except R._Goto as jump:',
                      '        if jump.name not in labels:', '            raise',
                      '        pc = labels[jump.name]', '    else:', '        pc += 1']
        lines += ['check_block(statements, expected)', 'return result']
        return self._compile(lines, bindings)

# Definition-time originals survive class instrumentation before lazy import.
# This checks ABI compatibility; it is not protection against malicious Python.
from .runtime import (_COMPILED_BASE_ABI_NAMES as _TRUSTED_ABI_NAMES,
                      _COMPILED_BASE_ABI as _TRUSTED_ABI)
