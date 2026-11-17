# Direct SearchDirection constructor rejection

Base: a9a2170ba5660db39b2b166b91892fa8a3834bd8. The unchanged strings scenario stopped after 372 observations because its intentional `New SearchDirection` negative test raised UnsupportedNakedSyntax during direct fragment compilation. SearchDirection is a namespace/value type, not a constructible type.

The finite service constructor table now marks its English and Russian names as non-constructible, using the same catchable runtime error path as regex result types. Unknown or unsupported constructors remain rejected during compilation; no blanket exception conversion or VM dispatch is added. Constructor resolution rejects this operation before evaluating arguments.

Run `python experiments/direct_string_join/replay.py` from this tree. The unchanged source completes with 385 observations, 13115 bytes, SHA256 a693bc2cf277b46de9be58d772afca30f1648c86d1b1ddbe3f76d550302673dd. Source SHA256 is cacbcc6dfef4352485f65badfaed8839e9363e9a4cfab814ee6c59e29abadeeb. The stored result is a direct replay result, not a native byte-comparison verdict.

Targeted tests cover both names through source, AST, prepared modules and Execute, rejection before argument effects, whole-fragment admission for an unsupported constructor, and server/NoContext/dual procedures. The original strings regression now requires completion with 385 records. Existing direct Execute, regex, full-client, HTTP and CatalogQuery tests run alongside these checks.

Integration on e62bbacaa1930532e507a18abca22099e922c796: 116 tests pass on Python 3.12 and 116 on Python 3.10 -O, including source Query/storage and security boundaries. Independent review found no blockers.

Native byte parity was checked against artifact 14339791263 from run 44107865305. Its strings source hash and output hash were verified against provenance. It does **not** match: native output is 13707 bytes, direct output 13115 bytes. Both have 385 observations (386 physical lines); 56 physical lines differ. These are existing search namespace/value/service operations returning `[error]` in direct execution. The constructor negative test now completes correctly, but completion count alone is not parity. `native_comparison.json` records exact hashes and differing lines without copying the native fixture. This publication only fixes the constructor blocker; it does not claim to fix the remaining SearchDirection namespace or StrFind omission behavior.
