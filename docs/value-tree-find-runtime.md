# ValueTree Rows.Find: bounded runtime candidate

This local candidate adds `Tree.Rows.Find(Value [, Columns [, Recursive]])`
and `Строки.Найти` on root or child row collections. It is based on the audited
44 observations of native run 40469971658, which failed host comparison while
Find was absent. That run is evidence, **not acceptance of this implementation**.

The implementation selects the first matching live original row, or Undefined
when no row matches. Rows are visited in receiver order; explicit Boolean true
uses iterative depth-first preorder through children. Native-tested Number 1 and
String `"True"` also enable recursion. Other numeric/string flag forms remain
rejected as unmeasured; this does not broaden the separate FindRows converter.
Omitted/false recursion
is local only. Descendants of nonmatching parents are still visited. This does
not scan the insertion-order registry, perform breadth-first traversal, copy rows,
or include the receiver's parent in a child-collection search.

An omitted, empty or Undefined column argument selects all schema columns.
Named comma-separated columns use case-insensitive schema lookup; any selected
cell can match, but row order takes precedence over column order. All names are
resolved before an empty-receiver or matching-row shortcut. Duplicate names
are de-duplicated, and empty tokens between valid names are ignored.

The finite witnesses establish ordinary spaces around names. The model's
`str.strip()` also trims Unicode whitespace; this is an explicit local
generalization, not an exhaustive native whitespace observation. Arbitrary
duplicate/empty-token combinations follow the model policy. Nonempty selectors
containing no names at all remain rejected as unmeasured. Number/Boolean/object
column selectors are not coerced.

Search values and selected cells are limited to exact String, finite Decimal,
Boolean, Undefined and Null. Number and Boolean are distinct; strings compare
with exact case and trailing spaces. Date, UUID, Type, TypeDescription, collections,
objects and extension subclasses are not silently assigned native equality.
All selected cells of a visited row are validated before equality short-circuits.
Later rows after the first match are not traversed. No mutation occurs during
search. The returned row is shared and live; detached-row lifetime is deferred.

## Local resource and safety policy

Existing tree limits apply: 100000 visited rows, 4096 selector/schema columns,
1000000 scanned cells, depth 256, 1000000 characters per string and an 8000000-unit
logical work budget. These are Yadinassi limits, not claims about native limits.
Text is bounded before splitting/casefolding and charged before equality. Decimal
coefficients are bounded without expansion of extreme exponents or changing
ambient decimal flags. Iterative frames avoid Python recursion limits.

Exact type gates reject hostile query/cell/name/flag subclasses before conversion
or equality hooks. Corrupt row/schema/container identities fail closed; schema
and child item lists and cell dictionaries must be the implementation's ordinary
built-in containers. Generic tests cover values/order independent of native
witness IDs, first-result identity, resource failures and malformed host objects.

## Native evidence and final gates

The initial42 capture accepted Number 1 and String `"True"` flags but a root match
hid their recursive effect. Fresh run40469971658 authenticated both supplementary
descendant-only probes: each returns original row6, parent4, level2. All old902
and initial42 native records remain byte-identical; all44 outputs are retained
as literal tests, without filtering accepted flags. Both captures failed the
then-unimplemented host comparison: neither is runtime acceptance.

Fresh full host/native and four-platform gates on this final ca76-based runtime
remain required. Do not reuse measurement provenance or claim native-prefix
equality alone proves host parity. No Copy/Sort, index, codec, transport, database
or workflow changes belong to this feature.
