# Direct UserMessage

The direct constructor and dynamic constructor now use the current canonical
`Interpreter._new_user_message` binding. The resulting object retains the existing
family-owned `UserMessageContext`; no independent delivery channel is created.

The finite bilingual surface is Text, Field, DataPath, DataKey, TargetID,
Message() and SetData(value). Existing canonical setters retain atomic type/size
checks. Paths remain inert strings. Message/SetData remain procedures, including
captured method calls. Replaced constructor registrations, foreign message owners,
changed captured handlers, close/revoke and policy denials do not authorize effects.

Only the actual owner and relevant invoked handlers are checked. There is no
per-access class inventory scan, generated-loop wrapper or general reflective
assignment grant. Delivery still uses the host's current sink/output, once;
post-delivery failure is not retried. Catalog inputs use the existing database
owner check; form scopes without that catalog capability cannot gain it through
SetData/DataKey. Managed forms reuse this adapter under their existing event guard.
No serializer, arbitrary member, by-reference property or cross-family message
transport is added.

Baseline: all 27 tests in `test_user_messages` failed at the unsupported constructor.
After this change those unchanged 27 tests pass, including ordinary forms, imports,
server/no-context delivery and six catalog cases. Together with nine new security
tests and neighboring dynamic-constructor, prepared-admission and source-form
security suites: **67 PASS normal and -O**. This is bounded validation, not a full
Light or native-1C parity claim.
