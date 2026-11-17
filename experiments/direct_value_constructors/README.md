# Finite direct descriptor and table constructors

Base: f8e69ce1f5e9105f475dd0906a68d5e2097c48e5. Two original native-codec tests stopped at `New TypeDescription`; after admitting that family, their next stop was `New ValueTable`. Both now pass unchanged:

- test_serialization_native.NativeEvidenceTests.test_all_native_type_guids
- test_serialization_native.NativeEvidenceTests.test_all_runtime_value_types_preserve_native_readback_behavior

The direct service table now admits exact registered canonical TypeDescription, NumberQualifiers, StringQualifiers, DateQualifiers, BinaryDataQualifiers and ValueTable factories, in both languages. Existing classes keep all their value/resource validation. Constructor binding rejects overrides, checks owner lifecycle and policy, and rechecks factory identity after argument effects. Only TypeDescription gains positional omission support, mapping holes to Undefined as its existing overload contract requires. Qualifier/table constructor holes remain rejected. No VM dispatch or dynamic reflection is added. Source forms and TextDocument code are untouched.

Validation: 114 targeted tests pass in normal Python 3.12 and optimized Python 3.10, covering both original native-codec tests, canonical descriptor/codec behavior, new route/alias/override/mutation/revocation/server regressions, regex, HTTP, CatalogQuery and full-client regressions. The unchanged strings replay still exactly matches native artifact 14339791263 in both modes: 385 observations, 13707 bytes, SHA256 309d8a1b6ffd21ca578da5e2c2c161a7b28ce8b0692860effb6e92c0ad03a763. Reproduce using experiments/direct_strings_parity/replay.py with that outputs archive.

Two of the original four compatibility tests remain failing: test_serialization.InternalSerializationTests.test_every_implemented_type_has_native_readback_behavior now reaches the unsupported table-index collection receiver; test_str_find_extended.ExtendedStrFindRuntimeTests.test_override_and_shadow_cannot_inherit_special_omission_policy still stops at the first-class `Find` variable. Broader qualifier tests also expose existing differences in exception classes for unsupported indexing/iteration/method requests; gates have not been weakened to make those tests green.

Scope limits: this slice admits static constructors through the existing canonical classes. Dynamic `New(type, arguments)`, direct-list type-array adaptation and application-specific enum-name resolution are not added. Canonical descriptor strings, canonical BSLArray inputs supplied by existing services, copy overloads and qualifier holes retain the original class behavior. It does not claim complete constructor or all-type codec parity.
