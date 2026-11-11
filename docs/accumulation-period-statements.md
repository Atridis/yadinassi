# Stock period statements: implementation checkpoint

This separate block targets `BalanceAndTurnovers` / `ОстаткиИОбороты` and a
closed Day/Month periodicity over existing Balance registers. It does not add
turnover-register storage, another UI report API, forms or posting authority.
Physical formats 14/15 and their exact source grants are unchanged.

The initial checkpoint contains overflow-safe, constant-space calendar indexing
and preserves the existing named Date binding before any read lease. It does
**not yet admit the new query sources** or assert their native semantics.
Opening/closing boundaries, carry-only and zero groups, partial periods and gaps
must be grounded in a new independent native capture before runtime admission.
The existing native12/native16 evidence remains immutable and does not prove
this new surface.

The final statement must reduce all fields on one actual borrowed read view.
It will retain complete source validation, typed reference identity, exact
scaled integer arithmetic and existing input/output budgets. No totals table,
implicit DDL, migration, independent Balance/Turnovers snapshots or cold
index-only guarantee is introduced. A wide interval must never allocate an
unbounded list of periods, and the last representable date must not require an
overflowing `End + 1` calculation.

A CLI example and exact native replay will accompany the functional checkpoint.
The current UI report grant remains separately closed; this core extension does
not automatically authorize another report name in it.
