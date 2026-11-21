# Direct catalog UI events

The reviewed autoform uses the current form's public model protocol, not Python
reflection. Exact item/command/control/table/row types must belong to the current
form and remain registered/attached. Public setters retain their original side,
readonly, data and action-signature checks. The GetAttributes result is bridged
from its newly returned canonical Array to its native list storage; attribute
metadata and immutable type descriptors remain constrained to this form.

Original catalog source event execution keeps the existing source bytes/hash,
XML/schema binding, scalar draft, row identity, message and candidate admission.
Only the invocation step changes to generated functions. The two pinned object
method calls are lowered to explicit services with a real Boolean reference,
then invoke the corresponding generated object export. Preparation is not
substituted with BeforeWrite; list checking uses its existing read snapshot.
No writer, transaction owner, source selection or persistent commit is replaced.
Failures still discard the disposable candidate and messages at the host seam.

Verified original main-demo workflows: refused empty product save and switch;
kind OnChange normalization/messages/save/navigation; product reference and row
editing/save/list check/reopen. New tests patch Interpreter.execute_program,
call_routine, block and _visit to fail during kind/product workflows. These plus
foreign/retired/private-control checks pass normal Python and -O.

Existing source event suites: 44/45 pass. The remaining old test injects a zero
per-AST `_remaining` observer and expects it to run; the direct profile deliberately
does not recreate that interpreter observer. It is not a storage or source
ownership check. The broader baseline host suite also has two document-card
admission failures addressed by a separate integration, not this catalog slice.
