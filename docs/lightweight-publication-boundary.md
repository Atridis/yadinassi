# Local computation and publication

The lightweight standalone module path computes in Python locals. Pure scalar,
native Array and numeric Map code has no repeated module-dict reads or per-element
authority wrappers. Map values here are numeric or missing None, not arbitrary
host objects. General code keeps explicit publication/reload at dynamic edges.
Owned/source/database profiles retain their existing authority protocols.

Local output publication is an authority boundary: the ORIGINAL context `_check`
runs before a batch and after each actual namespace write. Closing/revoking during
private computation prevents new slots being published; a finalizer triggered by
one authorized overwrite stops subsequent writes. The completed first write is
not rolled back. No claim of transactionally atomic public dictionary updates.
Checks are per published variable, not per element/iteration. They intentionally
retain actual owner/generation/policy checks, not a weaker `vm.closed` test.

Known behavioral change: module locals retain/release prior host values at
different points; this may change finalizer timing. Pure computed state is not
continuously visible through vm.variables. Dynamic edges synchronize explicitly.
Functional compatibility tests remain available; unsupported compatibility is
not described as passing. Critical close/revoke tests are not waived.
