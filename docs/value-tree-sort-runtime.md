# Bounded numeric ValueTree Rows.Sort

## Authenticated evidence and scope

Linux 1C 8.3.27.1508 run **40966832988**, attempt 1, PR151 head
`c460c127e76571e6b7930e60d074c19e7373a295`, tree
`02225abeed780d76cfdb16e148d69f144fb8c02d` supplied the unchanged 21-case
[observer](value-tree-sort-measurement.md). Independent audit verified source,
server/client module identity, positive EN/RU controls, identical 6,443-byte
captures and cleanup. Native capture SHA256:
`63264e3a24c6b3381e300f22766c11eecbffb20e17a03fadc95745aec6594871`.
The acquisition failed runtime parity because Sort was then absent; this must
not be rewritten as historical runtime acceptance. The literal capture and
minimal provenance are retained in `tests/fixtures/value_tree_sort/`.

The implementation is enabled only for the **interpreter semantic target**
`linux-8.3.27.1508`, independent of the Python host OS. The default Windows 1C
target remains explicitly unsupported for Tree Sort. This is a local bounded
implementation awaiting fresh complete CI/native acceptance, not full 1C parity.

## Observed behavior reproduced

`Rows.Sort / Строки.Сортировать` is a procedure with one through three arguments.
The measured calls use a column selector string, optional Boolean recursion
(default False) and optional comparator. Omission and explicit Undefined of the
comparator reproduce the successful numeric case; real CompareValues instances
are unavailable and remain deferred. Expression use rejects before mutation.

Default/False reorders only the receiver's immediate rows. True also sorts its
descendant collections. A child receiver never sorts ancestors or siblings.
Root/row/column/schema identities, per-row cells, Parent, Owner and Level remain
unchanged in all 21 native cases. Existing rows are reordered in their existing
`items` lists; `_all_rows` remains a liveness registry, not traversal order.

Numeric primary/secondary keys, EN ASC/DESC and RU Возр/Убыв reproduce the
observed multikey results. Both 18-row duplicate-key native cases are unstable:
ASC `rcoflibqnkhejmgpda`, DESC `adpgmjbqnkheilfocr`. The existing deterministic
introsort primitive reproduces the **complete native row records** in both
cases. This justifies an empirical model for this target, not identification
of the native algorithm or proof for arbitrary sizes/ties. In particular, this
Tree evidence does not exercise its depth-limit/heapsort fallback. Larger local
property and primitive fallback tests establish local ordering/resource safety,
not additional native equivalence.

Observed invalid selectors (including a missing first/second field and empty
selector), numeric selector, Array recursion, numeric comparator, wrong arity
and expression use leave the tree unchanged. The observer's coarse `A/O`
categories are reproduced; these are not exact localized exception text claims.

## Local safety policy and deferred behavior

Only exact finite Decimal key values are accepted. Strings (even in otherwise
simple cases), mixed types, Boolean/Undefined/Null keys, dates, objects and
CompareValues are deferred. Unsupported target/flag/key types are rejected
without host conversion, equality or ordering hooks. Numeric subclasses are
not implicitly admitted. Direction tokens outside the four named forms,
repeated selector names, empty comma chunks and optional comma holes are also
conservatively unsupported rather than assigned guessed native semantics.

Limits are local Yadinassi policy, not native limits: 100,000 registered rows,
4,096 columns/tokens, 1,000,000 examined cells/text characters, depth 256,
8,000,000 charged work units, numeric coefficient 4,096 digits and adjusted
exponent magnitude 4,096. Coefficient admission occurs before digit-tuple
allocation and does not depend on the caller's Decimal context.

Iterative validation checks receiver ancestry, exact object/key types, liveness,
ownership, cell-key identity and resource budgets before comparisons. Every
permutation is computed privately before any list is committed. Thus local
validation/work failures do not partially mutate this numeric subset; this is
an implementation policy, not a claim of universal native transactional Sort.
No identity is normalized, cloned, or inferred from cell equality. The observer
still accepts newly observed valid row identities independently of runtime
identity preservation.
