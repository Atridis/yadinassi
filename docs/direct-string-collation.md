# Bounded direct string relational ordering

The original standalone experiment deliberately measured raw Python ordering
against UCA. Its selection remained provisional (see the chronological
experimental-semantic-ledger); the later sorted(key=...) measurements did not
settle relational-operator semantics. Raw Python reverses the existing native
`"a" < "A"` observation and disagrees with the existing Min/Max string kernel.

The direct profile now explicitly selects `uca_string_order` together with
`native_order`. Exact str/str relational comparisons use the existing pure
collation.string_key algorithm: pinned pyuca 1.2, UCA10 DUCET file SHA validation,
4096 input and 16384 normalized-character limits. The helper holds its
definition-time kernel identity, not a replacement looked up through a mutable
public alias during comparison. No user-selected import/path, OS locale setting,
new host receiver, VM dispatch or fallback is introduced. Initial reached use
can read the existing pinned package table; no new filesystem capability is
exposed. The existing shared table cache has one entry and no input-string cache.

This is semantic restoration, not an acceleration. UCA key construction costs
more than Python codepoint comparison. Existing experimental profiles without
the new flag retain their ordinal ordering. Non-string scalar admission remains
unchanged; string subclasses and foreign comparison hooks are not admitted.
Equality, Map keys, Find, table/query sorting and grouping remain separate and
unchanged. Canonically equivalent keys do not make distinct strings equal.

UCA string literals are deliberately not folded during compilation. Otherwise
resource/table errors could escape Try or read the table from an unreachable
branch. They are checked at the reached runtime operation, including prepared
plan reuse, with left-to-right operand effects preserved.

Evidence is limited: the existing Windows 1C numbers fixture captures
`helper.strings.operator.less: [true]` for a<A and exact equality false, alongside
Min case-order examples. The full original native numeric prefix comparison
passes. UCA-equivalent spellings and resource/error behavior additionally follow
the existing kernel tests, not a new native capture. This is not proof of full
1C locale/Unicode ordering, not a claim that 1C internally uses UCA10, and not a
change to separately measured UCA6 table ordering. Broad math tests still contain
an unrelated missing-service authority error; that guard is not weakened here.
