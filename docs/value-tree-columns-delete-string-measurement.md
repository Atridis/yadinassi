# Columns.Delete named-selector compatibility measurement (DS6)

This immutable six-case measurement resolves an existing runtime compatibility
question, not a new implementation. The shared interpreter checks procedure
return policy before evaluating arguments; changing it to dispatch on selector
type would change evaluation/error timing. The unpublished DL14 runtime candidate
is therefore held until these independent native facts exist.

All cases start with Key (Title P, Width 9), Secondary, two root rows and one
child. Cases 1/2 are English index and Russian owned-column positive controls.
Cases 3/4 invoke English/Russian Delete("Key") statements; cases 5/6 invoke the
same methods as expressions. The documented primary Delete689 API lists Number
and ValueTreeColumn, not String: the four String results remain observations.
Exceptions are captured before helpers; before/after schema, rows, identity,
metadata and both cell sequences are independent. Partial mutation is retained,
not normalized or assumed transactional. Expression values use the existing
finite scalar grammar; values outside it reject the observer, not prove absence.

Availability requires both EN/RU controls to remove the selected column from a
nonempty two-column graph, with valid P9 setup. String success/error and retained
reference outcomes never control availability. Exact server/client agreement and
interpreter comparison remain required. Matched missing methods cannot pass.

The strict CC snapshot grammar is reused with a closed DS6 header map, not Clear
lifetime conclusions. Capture maximum is 2207 / 8192 bytes; completed marker compact 2356 bytes,
conservative JSON spacing/escaped-slash/BOM bound 2386 / 16384 bytes. Full integrated
majorants: stage 4353 / 8192, native report 9479 / 32768, transport 20707 / 65536,
host report 15189 / 32768, provenance 14977 / 32768. The fixed 23-file cold closure
includes only DS6 and its unchanged CC decoder dependency. No caps, permissions,
credentials, full_suite.py or runtime files change.

This measurement head temporarily replaces the DL14 automatic matrix row with
DS6 (same job/container count). DL14 source and its authenticated run 41135287284,
head ef3de20d75ad33260e542f96be78481b3beb1d03, 2492-byte capture SHA256
ca1d13d6b1ae5c038221392b65cc9e112378c7d9b350d640828cc878c68dcd2f remain immutable.
That acquisition succeeded while its runtime comparison failed; it is not
relabeled. Final runtime acceptance must restore the DL14 required lane and
retain DS6 offline replay with its own original acquisition attribution. No DS6
native capture exists at preparation time.
