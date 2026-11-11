# Accumulation observation and runtime fixture

`observations.out` and `provenance.json` are the unchanged accepted output of
[native run 42981217995](https://github.com/Atridis/yadinassi/actions/runs/42981217995).
The 16 ordered cases used source tree `15bb86ab74d5287b5927c9a870a4d2f42956712a`
and synthetic merge `38a11ab9fab5822154fa4ea973a35b7dbcb417e9`.
The native report accepts measurement, not runtime parity. Its immutable input
hashes and output bytes remain historical evidence, never rewritten for new code.

The native Designer input was the complete source-derived schema **2.4** XML in
`scripts/accumulation_register_behavior`. It was actually installed and its
material metadata projection verified before the observations ran.

`RuntimeAccumulationRegister.xml` is the separately authored canonical **2.20**
host input from local commit `001d4392944b6276db9c1255eb1ac21014d78eed` (the parent of integration `fe6b529`).
SHA-256: `dbc670763140778ea4549a78035b28aaac8fd2215c3aa4d595df5cba1509833a`.
It has the same owned identities, dimensions, resources, attributes, qualifiers,
totals settings and recorder contract. The tests compare that material projection
and execute the unchanged observer/handler against this explicitly granted host
input. This is not a claim that the authored wrapper can be installed natively,
nor permission for the runtime importer to accept arbitrary native dumps.

Active=false is explicitly unsupported in the first host profile. The native
mixed-active case failed; all-inactive behavior was not measured. RecordType
query projection/parameters, virtual periodicity/conditions, boundary objects,
reversed intervals, and all-zero Turnovers groups remain deferred. A zero-net
group with nonzero Receipt/Expense remains supported. Virtual grouping uses the
existing bounded caseless UCA contract; ordinary query WHERE/ORDER/GROUP retain
their separately documented host comparison policy.
