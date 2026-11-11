# Fresh accumulation register block

The implementation target is a separate fresh-only explicit source profile for
Balance-kind scalar accumulation registers with recorder-owned movements and
usable Balance/Turnovers query sources. This checkpoint does not activate it.

Period, Active and exact movement direction are distinct standard fields.
Dimensions, numeric resources and attributes retain distinct schema groups.
Movement storage, mutation identities and immutable receipt domains are separate
from recorder information registers. Their global dimension uniqueness must not
be reused. Storage primitives use only a borrowed caller-owned transaction.

Document, Posted state and movements will share the existing root journal and
operation savepoint. Historical immutable outcomes must remain recoverable after
later replacements. No new commit authority or implicit profile upgrade is added.

The query target is a raw scalar movement source plus Balance(&At) and
Turnovers(&From,&To), composed through the existing bounded typed query pipeline.
All underlying movements must be validated and charged before reduction,
including inactive, unprojected and out-of-range rows. Ordinary WHERE follows
virtual-table derivation. Native signs, endpoint inclusion, zero suppression,
group identity and output qualifiers await the sixteen-case acquisition in
scripts/accumulation_register_behavior/PLAN.md. Stored resource qualifiers do not
automatically describe signed or widened aggregate results.

The first block may refuse raw RecordType projection and enum query parameters
while using the exact enum for BSL movement assignment. Scalar raw Period,
Active, Recorder, dimensions/resources and aggregate queries remain the goal.
Turnover-kind registers, BalanceAndTurnovers, source filters/periodicity,
Boundary/PointInTime, manager APIs, persisted totals caches, migrations and
polymorphic Recorder projection are deferred.
