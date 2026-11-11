/** Closed compatibility admission for legacy scenarios that never open owned forms. */
import assert from 'node:assert/strict';

export function checkUnownedApplicationCapability(result) {
  const input = Object.hasOwn(result,'inputCapability');
  const dialog = Object.hasOwn(result,'dialogCapability');
  const owned = Object.hasOwn(result, 'updates');
  assert.deepEqual(Object.keys(result).sort(),
    ('protocol state error session form' + (owned ? ' updates' : '') + (dialog ? ' dialogCapability dialogs' : '') + (input ? ' inputCapability inputs' : '')).split(' ').sort(), 'wire_keys');
  if (dialog) {
    assert.equal(result.dialogCapability,'yadinassi-owned-dialog/1','dialog_capability');
    assert.deepEqual(result.dialogs,[],'unexpected_dialog');
  }
  if (input) {
    assert.equal(result.inputCapability,'yadinassi-owned-input/1','input_capability');
    assert.deepEqual(result.inputs,[],'unexpected_input');
  }
  if (!owned) return;
  // These scenarios have no Close(result) or completion. Do not quietly accept
  // unsolicited snapshots or weaken their original closed-envelope witness.
  assert.deepEqual(result.updates, [], 'unexpected_owner_update');
  assert.ok(Array.isArray(result.state.sessions) && result.state.sessions.length <= 8, 'session_budget');
  for (const session of result.state.sessions) {
    assert.deepEqual(Object.keys(session).sort(), ['id', 'entry', 'title', 'owner', 'blocked'].sort(), 'session_keys');
    assert.equal(session.owner, null, 'unexpected_owned_session');
    assert.equal(session.blocked, false, 'unexpected_blocked_owner');
  }
}
