# Original disposable metadata: schema boundary

The XML is an original, single-catalog fixture, not a third-party configuration.
These pinned primary-source specimens were inspected only for platform XML shape:

- [Catalog property/type serialization, XML 2.20](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/Catalogs/Currencies.xml).
- [Non-privileged server-call common module, XML 2.20](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/CommonModules/AttachableCommandsServerCall.xml).
- [Role XML shape](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/Roles/FullAccess.xml). Its broad rights are not copied.
- [Read/Insert/Update spelling in a role](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/Roles/AddEditCurrencyRates/Ext/Rights.xml). Its UI rights and attribute defaults are not copied.
- [Primary platform distinction between basic and interactive rights](https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/1C_Enterprise_Platform_Training_Course_-_Senior_Application_Developer_Level/Module_3._Access_rights/Episode_1._Playing_roles/?language=en).

Setup has exactly Administration, DataAdministration, ThickClient and
MainWindowModeNormal on this disposable configuration. CRUD has only the latter
two session rights and Read/Insert/Update/Delete on NativeOracleItems. Every role
default is false. No UI field or external-processor right is granted. Neither
source inspection nor unit tests establish that these rights are sufficient on
the pinned native platform. A permission/serialization failure stops the run;
it is not permission to broaden rights or change authentication/protection.

The common module is server-only, ServerCall=true and Privileged=false. The
privileged SessionModule is restricted to fresh zero-user bootstrap. It never
reads or mutates catalog data. Ordinary launches skip it. Audit is a distinct
setup-user call, while every measured catalog operation uses the CRUD identity.
Native API spelling, configuration serialization roundtrip and successful
execution remain unproven until an accepted isolated native run is obtained.
