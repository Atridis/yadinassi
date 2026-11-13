import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const shell=readFileSync(new URL('../src/app.mjs',import.meta.url),'utf8');
const configuration=readFileSync(new URL('../../configuration/src/app.mjs',import.meta.url),'utf8');
test('shell owns one attachment and injects epoch bound transport into both surfaces',()=>{
 assert.equal((shell.match(/createBrowserHost\(environment,root\)/g)||[]).length,1);
 assert.match(shell,/mountEditor\(environment,content,dispatch\(mountedEpoch\)\)/);
 assert.match(shell,/mountApplication\(environment,content,dispatch\(mountedEpoch\)\)/);
});
test('recovery snapshots and resumes retained renderer without selecting or replaying',()=>{
 const recovery=shell.split('async function recover(){')[1].split('async function select')[0];
 assert.match(recovery,/await client.snapshot\(\);await install\(\)/);assert.doesNotMatch(recovery,/client.select|client.dispatch/);
 assert.match(shell,/mountedEpoch===client.state.epoch\)\{await mount.resume\(\);return;/);
});
test('configuration cleanup is named and preserves business lifecycle',()=>{
 assert.match(configuration,/removeEventListener\('beforeunload',warnBeforeUnload\)/);
 const destroy=configuration.split('const destroy = () => {')[1].split('return {ready')[0];
 assert.match(destroy,/if \(!canLeave\(\)\) throw/);assert.doesNotMatch(destroy,/application.close|client.request|perform\(/);
 assert.match(configuration,/browserHost,canLeave,destroy,resume/);
});

test('modal editor recovery delegates to shell inspection, while resume avoids recursion',()=>{
 const catalog=readFileSync(new URL('../../catalog/src/app.jsx',import.meta.url),'utf8');
 assert.match(catalog,/const requestResync=\(\)=>exchange\?\.recover\?exchange.recover\(\):resync\(\)/);
 assert.match(catalog,/onClick=\{requestResync\}>Resynchronize choice/);
 assert.match(shell,/exchange.recover=recover/);
 assert.match(catalog,/recover=\(\)=>resync\(\)/);
});
test('verified transport recovery does not require discarding dirty local drafts',()=>{
 assert.match(shell,/ready:!client.uncertain&&!client.pending&&mount\?\.recoveryReady\(\)/);
 const catalog=readFileSync(new URL('../../catalog/src/app.jsx',import.meta.url),'utf8');
 const fence=catalog.split('recoveryReady=()=>')[2].split(';')[0];
 assert.doesNotMatch(fence,/hasDraftChanges|dirty|recoveryRef/);
 assert.match(fence,/editingLocked/);
});
