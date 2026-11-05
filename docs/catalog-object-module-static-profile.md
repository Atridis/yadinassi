# Catalog ObjectModule static profile v1

Status: **static analysis only; native parity = false**. This is not an
ObjectModule runtime, a BSL sandbox, or permission to activate a configuration.
The existing `module execution unsupported` activation issue is unchanged.
No existing parser, interpreter, catalog object, backend, or importer behavior
is modified. No source is executed, imported from disk, or sent to a host API.

## Entry and identity boundary

`analyze_object_module(source: bytes, binding: ObjectModuleBinding)` is a local
Python infrastructure API, not a BSL global, user-selectable event dispatcher,
CLI, or database operation. It returns frozen, tuple-based structural IR.

The binding commits to nonzero database/configuration/catalog UUIDs, a positive
bounded configuration generation, a bounded catalog schema, and the lowercase
SHA-256 of **exact original source bytes**. BOM and line endings are retained
and affect the hash. The canonical module path is derived as
`Catalogs/<catalog.name>/Ext/ObjectModule.bsl`, never accepted as an arbitrary
path. Metadata UUID/name collisions and field profile mismatches reject.

The caller must obtain this binding from verified metadata and an exact module
inventory. The analyzer validates its shape and matches the source hash; it
does **not** authenticate the UUIDs, inspect a database, verify an archived XML
dump, or establish that these bytes belong to this catalog. Supplying the same
source with another valid identity creates another explicit commitment, not a
provenance proof. Fabricated/reconstructed IR is not an execution capability.

In particular, do not derive the expected hash from untrusted replacement bytes
and call that an integrity check. The expected commitment must come from the
trusted calling workflow. This substage intentionally has no loader or consumer
that could mistake analysis success for activation approval.

## Deliberately narrow admitted syntax

- Exactly one `BeforeWrite(Cancel)` or `ПередЗаписью(Отказ)` procedure. English
  and Russian event/parameter aliases may be combined; names are case-insensitive.
  The single event parameter is non-Val, without a default.
- Private helper **procedures**, with names starting `_om_`, up to eight
  parameters each. Arbitrary helper names and all other lifecycle names reject.
  Helpers must be reachable in the syntactic call graph from BeforeWrite.
  Recursive/cyclic graphs reject. This namespace restriction is local policy,
  not a native 1C requirement.
- Explicit local `Var` declarations at the beginning of each procedure; no
  module state, implicit locals, shadowing of fields/profile symbols, or late
  declarations. Locals must be initialized before reads on every analyzed path.
  This is conservative and does not infer that a helper initializes a local.
- Assignments, `If/ElsIf/Else`, bare `Return`, direct helper calls, scalar
  literals, grouping, arithmetic/comparisons/Boolean operators, and `?(...)`.
  Every branch, both sides of Boolean operators, every conditional operand,
  unused procedure body, and code after Return are analyzed. There is no
  constant folding or dead-code exemption.
- Code/Description and their Russian aliases, plus zero to 64 uniquely named
  Number(12,2,Any), Boolean, or DateTime fields supplied in the committed schema.
  Reads/writes can use an implicit field name or direct `ThisObject.Field`.
  IR contains a named field slot, not a general host-member operation.
- Local/reference parameters may be passed by reference only as direct,
  initialized local names. Fields, grouped names and computed values are not
  accepted as reference arguments. Val arguments may be admitted expressions.

Functions, exports, async, defaults, all module initialization/state, other
events, subscriptions, imports, constructors, Execute/Eval, any builtin/host
call, arbitrary members/indexing, first-class routines, loops, Try/Raise/Goto,
Ref, IsNew, DeletionMark, DataExchange, and AdditionalProperties are excluded.
Date and Null literals are excluded; DateTime fields may be copied structurally.

### Why the ordinary parse entry is not used

The general `parse()` function selects conditional-compilation branches and
several execution-side passes. Its output cannot by itself prove that every
byte of an object module was checked. V1 rejects raw `#` and `&` **anywhere**, even
inside comments or string literals, before lexical analysis. This intentionally
also rejects benign text such as `"A&B"`; it is a conservative closed contract,
not a new language rule. It then uses one `Lexer(allow_directives=False)` and one
`Parser` pass with no side selector. No hidden preprocessor/annotation branch is
admitted. A closed token vocabulary and exact AST class/field layouts must match
before lowering; unknown syntax or future AST shape changes fail closed.

The parser's default `client` label is checked only as evidence that no execution
annotation was consumed. It is not an object-module execution context claim.

## Bounds and what is not proved

- Source: 16,384 UTF-8 bytes before decoding or lexing.
- Tokens: 2,048 including EOF; lexical structural/unary nesting: 16.
- AST: 2,048 nodes and depth 48; exact closed node shapes.
- Procedures including the event: 16; parameters: 8; locals per procedure: 32.
- String literals: 1,024 characters; decimal literals: 38 significant digits,
  at most 18 fractional digits. These are local analysis limits.
- Conservative acyclic call-graph expansion: 8,192 syntax nodes, counting
  repeated calls and both sides of branches. Unreachable helper declarations
  reject rather than acquiring an implicit dispatch meaning.

These bounds constrain **analysis and IR structure**, not resource use by a
future interpreter. For example, the analyzer can represent division by zero,
ill-typed arithmetic, a non-Boolean cancellation assignment, or intermediate
values exceeding storage qualifiers. It does not evaluate expressions, prove
types, validate runtime inputs, prove successful termination of a future engine,
or establish native coercion/rounding semantics. A future executor would require
closed scalar-value validation, operation/allocation budgets, cancellation
validation and a separate security review. Never pass admitted source/AST to the
general Interpreter as an execution shortcut.

All returned source/IR data is immutable under the normal Python API. This does
not defend against hostile Python code already running in the same process or
make public dataclass instances cryptographically authentic. Diagnostics are
bounded categories and do not reproduce source snippets or underlying exception
messages.

## Independent gates before execution

1. Independent audit of this exact static-analysis patch and its negative cases.
2. Separately approved local tests; this document itself records no test run.
3. Closed module path/ownership inventory, keeping every unrelated activation
   issue. Inventory support does not authorize execution.
4. New owned native seed measuring actual `Object.Write()` dispatch, Cancel and
   exception effects on detached buffers, duplicate/stale ordering, helper
   references and every admitted scalar conversion. Historical catalog fixtures
   explicitly exclude ObjectModule; form evidence does not transfer.
5. Separately reviewed object receiver/transaction integration, reentrancy guard,
   and exact post-handler intent recovery. Uncertain-commit resolution must not
   replay the handler. This patch changes none of those mechanisms.

The original analysis was prepared on main `d2927b67eb986d5f2db9d531cd2bfe80710b6b82` and was later integrated with the current catalog work.
The analyzer rejects catalog schemas containing tabular sections rather than
discarding section metadata. Native evidence acquisitions remain independent work. Analysis success cannot remove
any XML, metadata, module, database identity, activation, or native-evidence gate.

## Local test scope

`tests/test_object_module_analysis.py` contains only local static-analysis tests:
positive IR/source binding, immutability, whole-source rejection, hidden branches,
AST drift, illegal capabilities, reference/call graph restrictions, identity and
resource bounds, and preservation of the importer's existing activation issue.
It executes no BSL and acquires no native observations. Run only after approval
for the exact enumerated unittest count and command.
