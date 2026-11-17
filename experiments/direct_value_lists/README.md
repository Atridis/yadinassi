# Direct ValueList calls and field references

Base: `8b480263207d8ec498171fe7917464b7f1091321` (Catalog and nonposting
Document object handlers included). No VM dispatch or native fixture changes.

The original all-types serialization setup stopped at `New ValueList` after
table indexes were connected. Merely admitting its constructor and public
receivers was insufficient: original runtime/reference tests exposed eight
failures, including procedure-as-function mutation, effects preceding rejection
of required omitted arguments, and lost writes through item-field references.

This slice admits the exact canonical ValueList constructor and list/item public
protocol. The compiler supplies call-site value/omission facts to a boundary seam;
other receiver protocols retain their existing dispatch. ValueList procedures
are refused as values before argument evaluation. Only Add's three and Insert's
last three optional slots accept omissions, with canonical defaults. Explicit
Undefined is not rewritten. Factory/index receiver omissions fail before receiver
and argument effects. Named attribute chains remain available, including existing
`T.Columns.Add("A",, "Header")`; independent review caught and corrected an
initial overly broad rejection of this case.

Item-field references use the existing `_ForwardReference` adapter and canonical
reference getters/setters. Binding reads eagerly, each access rechecks canonical
ownership and runtime state, and the weak owner is not retained. Canonical item
conversion, detached-item behavior, list resource/atomicity checks, mutation during
iteration, and private/member restrictions remain in their existing classes.
Host-held field references are checked when the runtime closes; they are not
claimed to have Execute FragmentScope activation-only lifetimes.

## Verification

From repository root, with project dependencies installed:

```
python experiments/direct_value_lists/check.py
python -O experiments/direct_value_lists/check.py
python experiments/direct_strings_parity/replay.py /path/to/native-artifact.zip
```

Python 3.12: 134 selected tests passed, normal and optimized. Python 3.10 optimized:
133 passed; the runner explicitly does not select one existing codec transport
test that patches unavailable `subprocess._text_encoding`. Eight new regressions
cover source/AST/prepared routes with VM entry points forbidden, persistent calls,
refusal order, bilingual defaults, retained references, ownership mutation, and
existing table-column omissions. Separate Catalog/Document/source-scope integration
checks contain 95 tests.

The unchanged original ValueList runtime/reference suite now has no assertion
failures; five errors remain: DynamicNew, the native helper's FixedStructure
constructor, and three tests expecting catchable BSLError for direct fail-closed
BoundaryViolation cases. The focused runner lists these exclusions explicitly;
the original tests and fixtures are unchanged.

Original strings replay is byte-exact in Python 3.12 normal and Python 3.10 -O:
385 observations, 386 physical lines, 13,707 bytes,
SHA-256 `309d8a1b6ffd21ca578da5e2c2c161a7b28ce8b0692860effb6e92c0ad03a763`.
The replay verifies source/provenance hashes from native run 44107865305. This is
strings evidence, not a claim of full native parity or all-CI success.

## Remaining compatibility limits

The unchanged all-types serialization test now finishes ValueList setup and
reaches its individual subtests; it still reports one failure and eight errors
for other direct representations, FixedArray/FixedStructure/FixedMap constructors,
and XMLStringProcessing. First-class Find name resolution is not changed.
DynamicNew, direct-array LoadValues adaptation and contextual choice UI are not
introduced. Source configuration-specific ValueList integration is not claimed.
