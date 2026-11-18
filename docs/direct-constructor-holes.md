# Direct native collection constructor omissions

Native direct Array/Map/Structure lowering previously converted a syntactic
comma-hole into Python None, then evaluated other arguments. That both ran side
effects before a rejection and accidentally accepted `New Structure("X",)`.
The existing canonical subset rejects such omissions before argument effects.

Only the reached fallback native lowering for these three built-ins (and their
Russian aliases), with service boundaries enabled, now emits the existing
catchable omission diagnostic before supplied argument evaluation. Dead branches
stay inert. Explicit `Undefined` is still a real supplied value and preserves
ordinary evaluation/error order; it is not a hole.

Explicit constructor services and their optional-slot protocol run first and are
unchanged. Overridden direct collection constructors remain unsupported before
host effects. Dynamic New with a parameter array, unknown constructors, source
constructor protocols and experiments without service boundaries are unchanged.
No constructor or host authority is added and no VM/legacy fallback is used.

Evidence is the existing defaults/maps omission tests and compiled-strict
side-effect controls, not a native 1C observation. The diagnostic describes the
current supported subset; this is not a claim that the native platform universally
rejects these argument forms. Future native-backed optional-slot support must be
explicit rather than silently treating all omitted positions as Undefined.
