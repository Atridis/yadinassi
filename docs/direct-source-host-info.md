# Direct source host information

Source-owned SystemInfo/СистемнаяИнформация and the explicit foreground
scratch-host session now use finite direct adapters. This does not detect an
installed native 1C platform or invent a native login.

SystemInfo returns only the original compatibility-target properties and actual
Yadinassi version. AppVersion still requires an explicitly configured source
compatibility target; unknown operating-system/platform properties fail.
Properties remain readonly. A canonical source-owned factory marker replaces
the previous constructor lambda without enabling the constructor globally.

GetCurrentInfoBaseSession, GetBackgroundJob and InfoBaseConnectionString use
the actual caller and original host-session implementation. The session must
belong to the running source application, execute synchronously on the server,
and have an explicitly created source scratch database. Foreground startup has
no background job. Connection text remains SQLite identity, not native File/Srvr
syntax and not a grant of database authority.

Saved methods, constructor registrations and delayed invocations recheck exact
owners and implementation identities. Foreign, closed, retargeted and forged
markers are rejected before callbacks. Legacy execution is not a fallback.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_host_info_no_vm \
  test_python_direct_source_host_info_security
```

Final local evidence: 960 focused/compiler tests pass on Python 3.12; Python
3.10 `-O` passes with the existing SQLite limit-API skip. This includes an explicit
compiled-strict control proving that the canonical factory marker preserves the
legacy constructor path, while direct-path suites poison legacy execution.
The source-wide 1,228-test suite remains red at 103 errors and 5 failures,
10 fewer failing outcomes than the extension checkpoint, with no new failing
identities. Constructor class-symbol, __init__ and __new__ identities are checked
before creating an object; patched-init and rebound-symbol tests verify that no
substituted callback executes.
