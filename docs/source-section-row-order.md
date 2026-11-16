# Source section row ordering

The explicit source-document-section profile now admits `Insert/Вставить(index)`,
`Move/Сдвинуть(row_or_index, offset)` and `IndexOf/Индекс(row)`.
This closes the basic memory-buffer ordering gap used by document editors and
initialization code; it does not add posting, migration or native parity.

Indices are exact integral BSL Numbers, zero-based. Insert accepts the end
position and returns an initially unassigned owned row. Move accepts a live row
of this exact section or its current index, plus an integral signed offset;
the resulting position must remain in bounds. There is no clamping or wrapping.
IndexOf accepts only a live row of the same section. Foreign, deleted and stale
handles are rejected rather than returning a membership sentinel.

Moves preserve row handles and values, and LineNumber/НомерСтроки reflects the
new one-based position. A nonzero move or successful insertion invalidates an
active iterator; a zero move does not. Failed type, range, ownership or aggregate
buffer-budget validation leaves the buffer order and version unchanged.

These are memory-only operations. No handlers run and nothing is persisted
until an explicitly permitted document Write. Existing application ownership,
closed-owner, safe-mode, read-handler and transaction-poison guards remain in
force. The implementation uses the existing bounded section storage contract,
not a general native-1C compatibility claim.
