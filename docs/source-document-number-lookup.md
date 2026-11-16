# Source document number lookup

`Documents.<Name>.FindByNumber(number)` / `Документы.<Имя>.НайтиПоНомеру(номер)`
returns the canonical source reference, or that document type's empty reference
when absent. The current admitted document profile requires explicit String
numbers, unique within the document type, and `NumberPeriodicity=Nonperiodical`.
Exactly one argument is admitted. Period/date arguments, coercion and inferred
numbering are not implemented. Comparison is exact and case-sensitive.

The lookup uses the existing bounded, integrity-checked source document reader
under the caller's scratch capability. It sees the caller's uncommitted writes
and rollback, includes deletion-marked documents, and does not execute object
modules, create objects or post documents. Ambiguous results are rejected rather
than returning an arbitrary match. Existing lifecycle, synchronous server,
application ownership and safe-mode checks apply.

This implementation scans the admitted bounded record set; it does not claim
an indexed search or native 1C parity. No storage schema, migration or default
capability changes are introduced.
