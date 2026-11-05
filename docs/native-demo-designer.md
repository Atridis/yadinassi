# Demo archive → isolated native DESIGNER

This is a separate profile, not fixture injection into a closed catalog suite.
It does not import or execute the archive's `validate_dump.py`, start ENTERPRISE,
create users/roles, change unsafe-operation protection, run external processors,
or modify existing smoke/profile inventories or workflows.

## Source and execution status

Implementation and unit tests are not evidence of native acceptance. The first
native run has not been performed. Exact CheckConfig options are documented in
the official [1C 8.3.27 Administrator Guide, section 7.4.5](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/):
`-ConfigLogIntegrity -IncorrectReferences -ThinClient -Server
-ThickClientManagedApplication -HandlersExistence -ExtendedModulesCheck`.
These select configuration/reference integrity, managed client/server syntax,
handler existence and extended module checks. They do not execute business
scenarios. The image and executable path select 8.3.27.1508; no runtime
`SystemInfo.AppVersion` measurement is claimed because that requires BSL execution.

## Owner-operated CI route

After source review, use **Native demo DESIGNER acceptance** manual workflow
on the reviewed same-repository branch. Supply its exact 40-character commit SHA
as `reviewed_sha`. The workflow must be available in GitHub's default-branch
workflow catalog before its manual action is available. A moving branch is not
an approval token: dispatch SHA, workflow SHA and input SHA must all match.
Only the verified repository owner/account IDs and matching event sender qualify.
Admission runs inline without checkout or permissions; the native job then binds
a clean checkout to the same immutable SHA. Its only grants are `contents: read`
and `packages: read`, matching the existing isolated workflow. This eligibility
is not a defense against an authorized editor changing workflow/policy source.
No automatic pull-request/push trigger and no undocumented dispatch workaround
is provided. Publication, source review and actual dispatch are separate steps.

The host receives registry credentials only for login/pull into an owned private
Docker configuration, removes them before container execution, and passes a clean
environment. The unchanged digest-pinned image uses `network=none`, UID 1000,
read-only root and source bind mount, no capabilities, no-new-privileges, resource
limits, private IPC, no Docker logging and bounded tmpfs. Display authentication
uses a fresh cookie with X11/RFB TCP disabled, as in the existing profile.
A private `dbus-run-session` owns the session bus for the whole sequence without
changing the pinned image's session policy. Container removal remains the final
process-tree cleanup boundary.

## Native stages and evidence

1. Pass only the fixed archive, manifest, safe extractor and new profile sources.
2. Recheck archive identity, CRC/entry hashes, paths and normalized UTF-8 names;
   materialize exactly 15 XML and 4 BSL files in a fresh owned directory.
3. CREATEINFOBASE creates a fresh file database without template/data.
4. DESIGNER LoadConfigFromFiles loads the untouched source.
5. DESIGNER CheckConfig runs the selected documented checks.
6. DESIGNER UpdateDBCfg applies configuration to the disposable database.
7. DESIGNER DumpConfigToFiles emits a hierarchical redump.
8. Compare exact file inventory (only native ConfigDumpInfo.xml is additional),
   BSL source (BOM/CRLF only normalization), expanded XML element/attribute names,
   text and child order (structural indentation only ignored). Namespace prefix bindings
   are retained conservatively, including QName-valued text and attributes. Refuse semantic mutations,
   additional modules, missing fields or native-added defaults until separately
   reviewed. Strict roundtrip may reveal format incompatibility; that is a failed
   witness, not authority to weaken checks.

Each batch must exit zero and produce a fresh zero DumpResult. Surviving native
processes prevent advancing. Each command has a 120-second timeout plus 5-second
kill grace; the host's 900-second lifecycle includes container ownership checks,
execution and cleanup. The reused lifecycle never removes by guessed name and
rejects uncertain create/removal. The finite report is released only after the
owned container ID and private host workspace have been removed. On uncertainty,
no native evidence is accepted and cleanup state is reported separately.

Only fixed enums, hashes, source paths from the reviewed inventory, nonces,
selected image/version and booleans leave the
container. Raw logs, XML, BSL, database files and process paths are not artifacts.
The workflow uploads only `demo-native-report/report.json`. A successful report
proves selected Designer acceptance and strict source roundtrip, not functional
MVP acceptance, GUI behavior, storage parity or all twelve demo scenarios.

## Local source verification

`python3 -B -m unittest tests.test_demo_cf_fixture tests.test_native_1c_demo_designer -v`

Repeat with `-O` to ensure gates do not depend on assertions. These tests never
start Docker or 1C. `bash -n scripts/native_1c_demo_designer.sh` checks shell syntax.
The native entrypoint deliberately requires `--execute-approved-image`; do not
run it as a unit test or substitute it for CI's exact-source admission.
