import test from 'node:test';import assert from 'node:assert/strict';
import {verifyFormCheckReport} from './source_form_check_support.mjs';
const state={form_preview:{name:'CommonForm.Main',source_path:'Form.xml',source_sha256:'a'.repeat(64),status:'projected',counts:{controls:1},diagnostics:[],omitted_diagnostics:0},module_preflight:{name:'CommonForm.Main',module_path:'Module.bsl',module_sha256:'b'.repeat(64),xml_sha256:'a'.repeat(64),compilation_profile:'standalone',status:'compiled',error:null,handler_names:{missing:[]}}};
function report(){const x=state.form_preview,m=state.module_preflight;return{schema:'yadinassi-source-form-check/1',name:x.name,scope:'Static XML projection and BSL preflight only; not runtime or native parity',xml:{source_path:x.source_path,source_sha256:x.source_sha256,status:x.status,counts:x.counts,diagnostics:x.diagnostics,omitted_diagnostics:x.omitted_diagnostics},module:{source_path:m.module_path,source_sha256:m.module_sha256,xml_sha256:m.xml_sha256,compilation_profile:m.compilation_profile,status:m.status,error:m.error,handler_names:m.handler_names},runtime_checked:false,storage_granted:false,native_parity:false};}
test('download must exactly match both source-bound probes',()=>{assert.deepEqual(verifyFormCheckReport(JSON.stringify(report()),state,'private-session'),report());});
test('altered hashes, success claims and extra data cannot be published',()=>{
 for(const change of [r=>r.xml.source_sha256='c'.repeat(64),r=>r.runtime_checked=true,r=>r.session='private-session',r=>r.values={Greeting:'secret'},r=>r.module.status='unavailable']){
  const r=report();change(r);assert.throws(()=>verifyFormCheckReport(JSON.stringify(r),state,'private-session'));
 }
});
test('missing token and mixed check identity reject evidence',()=>{
 for(const token of [null,undefined,''])assert.throws(()=>verifyFormCheckReport(JSON.stringify(report()),state,token));
 assert.throws(()=>verifyFormCheckReport(JSON.stringify(report()),{...state,module_preflight:{...state.module_preflight,name:'Other'}},'private-session'));
});
