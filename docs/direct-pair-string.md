# Direct iterator pair String presentation

The exact direct iterator-pair representation now returns `КлючИЗначение` through
the existing canonical String adapter. Previously its dataclass repr exposed key
and value representations and could invoke payload repr hooks. This is a single
exact-type label branch, with no field, equality, str/repr or descriptor access.
Class-method overrides cannot affect that label because no method is dispatched.
The definition-time pair identity remains pinned; subclasses and other host
values keep the previous canonical String path, not a new exemption.

Named and captured canonical String calls share the existing implementation and
policy/lifetime checks. User-registered String replacements are untouched. This
change does not alter pair equality, map keys, iteration, readonly properties,
implicit presentation, or constructor authority, and adds no VM/legacy fallback.

Archived `integrational_tests/fill_exclude_native/collections.out` records
`present.key-and-value.structure` and `present.key-and-value.map` as
`[КлючИЗначение]`. Their source in `integrational_tests/tests/collections.bsl`
explicitly calls `Строка(Пара)`. Fixed-structure/map labels are also present but
already use canonical pairs, not the new direct representation. These are
existing observations, not a fresh native run or a claim about all presentation.
