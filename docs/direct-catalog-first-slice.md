# Direct catalog protocol: initial slice

A host-selected exact SQLiteDBContext now permits the Catalogs/Справочники
namespace. Generated Python calls the existing public catalog field/method
protocol, not Python getattr or interpreter dispatch. Receivers must belong to
the current catalog metadata root. Foreign roots and private backend attributes
are rejected. Field normalization, immutable reference fields, row attachment,
pending-write protection and original backend writer remain unchanged.

Verified on a temporary main-demo database: BSL creates and writes a warehouse,
reads it through Ref.GetObject, creates a product and adds its tabular row.
The no-argument host Add call exposed an emitter bug: Array's implicit None was
also inserted into the host call. It is now inserted only in the native list path.

Registered Query construction, Execute, Select, Next and result field reads now
use the existing public query protocol. Query receivers must belong to the same
catalog root. Detached result/selection values are pure data; they cannot query
or write. Reference-valued cells still require current-root ownership on use.
This is not universal database execution: document/register protocols, query
Unload ValueTable operations and database iteration are not connected. Explicit transaction services are refused
before effects in this first direct database slice; the prior activation flag is
restored. Catalog writes still use their existing atomic writer. The original
product BeforeWrite module remains mandatory and now has a separate direct
implementation (see python-direct-catalog-preparation.md); its failure is not bypassed. Partial prior independent writes
are not a transaction and are not automatically undone if a later statement fails.

No arbitrary Python object protocol or silently selected legacy path is added.
