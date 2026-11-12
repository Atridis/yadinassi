import test from 'node:test';
import assert from 'node:assert/strict';
import {mountForm} from '../src/app.mjs';
import {environment,all} from './fake-dom.mjs';
import {state,reply,field,button} from './fixtures.mjs';
const initial=()=>state(0,{items:[field('Name'),field('Notes',{type:'String',value:''}),button('Choose')]});
async function setup(){const env=environment(),calls=[];const mount=mountForm(env,env.document.root,{transport:async r=>{calls.push(r);return reply(r,initial());}});await mount.ready;return {mount,env,calls};}
test('external host snapshot preserves raw input and never issues a form request',async()=>{
  const {mount,env,calls}=await setup(),input=all(env.document.root).find(n=>n.tagName==='INPUT');input.value='pending';input.emit('input');
  const next=initial();next.revision=1;next.items[0].value.value='confirmed';mount.adoptExternal(reply({id:1},next));
  assert.equal(input.value,'confirmed');assert.ok(env.document.root.textContent.includes('Name: pending'));assert.equal(mount.view.hasDrafts(),true);assert.equal(input.disabled,true);assert.equal(mount.client.snapshot.items[0].value.value,'confirmed');assert.equal(calls.length,1);
});
test('external event failure still adopts its authoritative state without clearing draft',async()=>{
  const {mount,env}=await setup(),input=all(env.document.root).find(n=>n.tagName==='INPUT');input.value='pending';input.emit('input');
  const next=initial();next.revision=1;mount.adoptExternal(reply({id:1},next,'event_failed'));
  assert.equal(mount.client.snapshot.revision,1);assert.equal(input.value,'pending');assert.equal(mount.client.transportFailed,false);
});
test('external snapshot cannot bypass a busy or terminally locked form',async()=>{
  const {mount,env}=await setup();mount.client.busy=true;assert.throws(()=>mount.adoptExternal(reply({id:1},initial())));
  mount.client.busy=false;mount.lock();assert.throws(()=>mount.adoptExternal(reply({id:1},initial())));assert.ok(env.document.root.textContent.includes('Connection lost'));assert.ok(env.document.root.textContent.includes('refresh is unavailable'));
});
test('malformed external snapshot is terminal and does not replace prior state',async()=>{
  const {mount}=await setup(),before=mount.client.snapshot;
  assert.throws(()=>mount.adoptExternal(reply({id:9},state(1))));assert.equal(mount.client.snapshot,before);assert.equal(mount.client.transportFailed,true);
});
test('owned opening during first change stops remaining flush and command without losing drafts',async()=>{
  const env=environment(),calls=[];let blocked=false;
  const mount=mountForm(env,env.document.root,{businessBlocked:()=>blocked,transport:async r=>{
    calls.push(r);const next=initial();if(r.params.event==='change'){blocked=true;next.revision=1;next.items[0].value={type:'String',value:r.params.value.value};}return reply(r,next);
  }});await mount.ready;
  const fields=all(env.document.root).filter(n=>n.tagName==='INPUT');fields[0].value='first';fields[0].emit('input');fields[1].value='second';fields[1].emit('input');
  await mount.run('command','Choose');assert.equal(calls.length,2);assert.equal(calls[1].params.event,'change');assert.equal(fields[1].value,'second');assert.equal(fields[1].disabled,true);assert.equal(mount.client.transportFailed,false);
});
