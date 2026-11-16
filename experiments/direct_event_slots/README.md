# Bounded editor/list event plan slots

The existing catalog manager now retains two code-only slots: editor and list.
Alternating list checks and editing no longer evict the other's generated code.
Both retain the complete previous source/schema/profile/constructor/name key;
no receiver, VM, grant, or activation is cached. Current admissions and fresh
execution contexts are unchanged. A changed key replaces only its purpose slot.

Reproduce: `PYTHONPATH=tests:. python experiments/direct_event_slots/paired.py BASE CANDIDATE`.
Baseline is local 7e2d5123 (same production code as public bbeba4e4).
Five alternating fresh-process pairs, nine real SQLite list/check/reopen/change/
cancel cycles per process, first discarded. Description visible output is checked.
Measured warm medians: 36.114 -> 2.641 ms. This is specifically the former cache
thrash case, not ordinary warm events or a general business speedup. Raw samples
are in results.json. No performance pass threshold.
