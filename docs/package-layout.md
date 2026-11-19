# Package layout

The package root contains the public embedding API (`Interpreter`, `BSLError`,
`BSLRuntimeError`), the CLI entry points, and the runtime that connects the
subsystems.

| Package | Responsibility |
| --- | --- |
| `syntax`, `numeric` | BSL syntax and numeric implementation |
| `execution/direct` | Direct Python execution, including adapters for configured modules under `source` |
| `execution/codegen` | AST generation and code generation helpers |
| `execution` | Execution policy, invocation and module handling |
| `types`, `collections` | BSL values, types and collections |
| `text`, `temporal` | String, number-presentation and date operations |
| `configuration`, `application` | Configuration loading and application/session services |
| `db` | Catalogs, documents, registers, query execution, and SQLite storage |
| `forms`, `ui` | BSL form state and browser-facing UI |
| `formats`, `streams`, `http` | Serializers, stream I/O and HTTP transport |
| `data` | Bundled data tables |

Python imports of implementation modules use their owning package, for example
`yadinassi.db.sqlite.sqlite_catalog`. The top-level embedding API and the
`yadinassi` command have not moved.
