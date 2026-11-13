import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../src/app.jsx',import.meta.url),'utf8');
test('reusable mount injects transport without another browser attachment',()=>{
  assert.match(source,/export function mountEditor\(environment,root,exchange=null\)/);
  assert.match(source,/const browserHost=exchange\?\{enabled:false/);
  assert.match(source,/const underlyingTransport=exchange\|\|/);
  assert.match(source,/if\(exchange\)\{connect\(\)\.then\(connected,failed\);return;\}/);
});
test('surface leave fence includes open editor picker drafts recovery and pending state',()=>{
  const fence=source.split('  leave=()=>')[1].split(';')[0];
  for(const token of ['!disposed','readiness','!gate.current','!client.uncertain','!client.snapshot?.state?.editor','!client.snapshot?.state?.referenceChoice','!recoveryRef.current','!hasDraftChanges','!lifecycle.current.pending'])assert.ok(fence.includes(token),token);
});
test('destroy only retires renderer and transport, never replays or business closes',()=>{
  const destroy=source.split('destroy(){')[1].split('}};')[0];
  assert.match(destroy,/disposed=true/);assert.match(destroy,/render\(null,browserHost.content\)/);
  assert.doesNotMatch(destroy,/client\.(event|hello|resync)|transport\(/);
  assert.match(source,/if\(disposed\)throw new Error\('Editor mount destroyed'\)/);
  assert.match(source,/getElementById\('app'\)\)mountEditor/);
});
