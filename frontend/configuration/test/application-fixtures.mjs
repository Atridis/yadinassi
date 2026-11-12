/** Legacy mock hosts now acknowledge the production renderer's empty dialog extension.
 * Actual dialog/negotiation tests use the unwrapped production mount directly. */
import {mountApplication as mount} from '../src/app.mjs';
import {DIALOG_CAPABILITY} from '../src/client.mjs';
import assert from 'node:assert/strict';
export function mountApplication(environment, root, exchange) {
  return mount(environment,root,async request => {
    if (request.method === 'application.hello') assert.equal(request.params.dialogCapability,DIALOG_CAPABILITY);
    const reply = await exchange(request);
    return {...reply,result:{...reply.result,dialogCapability:DIALOG_CAPABILITY,dialogs:[],inputCapability:'yadinassi-owned-input/1',inputs:[]}};
  });
}
