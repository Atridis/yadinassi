# Independent streaming aggregate byte bounds

Full catalog/document record validators now count raw UTF-8 payload bytes while
streaming, and enforce the existing 16 MiB per-record-table aggregate bound even
when called without verify_extra. Full section validation likewise accumulates
bytes across all document families under its existing 16 MiB storage bound.
Preflight guards, per-record/per-document limits, canonical decoding, UUID and
revision checks are retained. No extra SQL query or persistent cache is added.

Tests cover exact aggregate limits and a one-byte overflow, cumulative section
families, UTF-8 versus character length and statement closure with retained
error tracebacks. Limit constants are patched downward for focused tests; this
does not weaken production constants. Canonical persisted JSON remains ASCII
escaped; noncanonical Unicode input is still rejected by the codec.

This is validation hardening, not a new storage profile or native parity claim.
