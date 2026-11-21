# Bounded source manager-name shadowing

Ordinary exact source-host routines may assign a local value to a manager
namespace name (the existing bilingual manager aliases, including Catalogs,
Documents, Reports, DataProcessors and register-manager families). This changes a local binding, not the application
namespace or manager authority. Before the first executed assignment, reads
continue through the existing checked namespace lookup. An assignment in a
branch that was not taken does not hide that namespace. Subsequent reads use the
local value; sibling routines and subsequent activations retain their own scopes.

The private compiler profile is trusted-source-only. Parameters and explicit
local declarations retain their existing semantics. Module slots and exported
application variables are excluded, so their live addresses and shared writes
are unchanged. Attribute/index writes are not name shadowing and do not gain
permission to modify namespace objects. An unset implicit local is not an output
reference to the namespace.

This bounded profile does not apply to specialized object/form boundaries or
ordinary standalone execution. Routines combining implicit manager shadowing
with Execute/Eval are explicitly rejected during preparation, before effects;
their fragment visibility contract is not silently approximated. Other source
virtual namespaces and module-top-level implicit shadows are not added here.
