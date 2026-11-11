import test from 'node:test';
import assert from 'node:assert/strict';
import {checkUnownedApplicationCapability} from '../../../tests/browser_ui/unowned_application_capability.mjs';

const result = () => ({protocol:'yadinassi-configuration-app/3', state:{sessions:[
  {id:'form-1',entry:1,title:'Owner',owner:null,blocked:false}
]}, error:null, session:null, form:null, updates:[]});

test('legacy acquisition admits only the empty owned-result extension', () => {
  checkUnownedApplicationCapability(result());
  checkUnownedApplicationCapability({...result(),dialogCapability:'yadinassi-owned-dialog/1',dialogs:[]});
  const legacy=result();delete legacy.updates;
  checkUnownedApplicationCapability(legacy);
});
test('legacy acquisition rejects unsolicited owner updates and ownership', () => {
  for(const mutate of [v=>v.updates.push({session:'form-1',form:{}}),
    v=>v.state.sessions[0].owner='form-2',v=>v.state.sessions[0].blocked=true]) {
    const value=result();mutate(value);assert.throws(()=>checkUnownedApplicationCapability(value));
  }
});
test('legacy acquisition keeps closed envelope and session inventories', () => {
  for(const mutate of [v=>v.dialogs=[],v=>Object.assign(v,{dialogCapability:'unknown',dialogs:[]}),
    v=>Object.assign(v,{dialogCapability:'yadinassi-owned-dialog/1',dialogs:[{}]}),v=>v.callback='private',v=>v.state.sessions[0].result='private',
    v=>delete v.state.sessions[0].blocked,v=>v.updates=null]) {
    const value=result();mutate(value);assert.throws(()=>checkUnownedApplicationCapability(value));
  }
});
