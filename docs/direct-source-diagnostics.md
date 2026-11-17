# Direct source diagnostics

Source routine/fragment service lookup keeps the spelling from the authored
call in diagnostics, while matching registrations and routines by casefolded
keys as before. Required-service inventories remain normalized. This is not a
new callable or receiver capability, and unknown calls still fail before actual
argument evaluation. Standalone compiler lookup spelling is unchanged.

Source GetRef still requires exactly one explicit UUID. Early argument-count
rejection now uses the same explanation as the existing source reference marker;
EmptyRef/Metadata still take no arguments. Admission order, UUID type checks,
ownership, backend availability and reference semantics are unchanged.
