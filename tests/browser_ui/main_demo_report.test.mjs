import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {encodeMainDemoReport,verifyMainDemoSourceBinding} from './main_demo_report.mjs';
const hash=raw=>createHash('sha256').update(raw).digest('hex');
const fixture=()=>({status:'FAIL',failure:{phase:'example',reason:'step_failed'},scenarios:[{name:'one',status:'PASS'}],binding:{commit:'a'.repeat(40),tree:'b'.repeat(40),source:{'yadinassi/example.py':'c'.repeat(64)}}});
test('roundtrip preserves every execution field and full source inventory without mutating report',()=>{
  const report=fixture(),before=JSON.stringify(report),{raw,sourceRaw,sourceArtifact}=encodeMainDemoReport(report);
  assert.equal(JSON.stringify(report),before);
  const parsed=JSON.parse(raw);assert.equal(parsed.status,'FAIL');assert.deepEqual(parsed.failure,report.failure);assert.deepEqual(parsed.scenarios,report.scenarios);
  assert.deepEqual(verifyMainDemoSourceBinding(parsed,sourceRaw),report.binding.source);
  assert.deepEqual(parsed.binding.sourceArtifact,sourceArtifact);assert.equal(parsed.binding.source,undefined);
});
test('large source inventory no longer spends the report budget and none is dropped',()=>{
  const report=fixture();report.binding.source={};
  for(let i=0;i<1600;i++)report.binding.source['yadinassi/module'+i+'.py']='d'.repeat(64);
  assert.ok(Buffer.byteLength(JSON.stringify(report))>65536);
  const {raw,sourceRaw}=encodeMainDemoReport(report);
  assert.ok(Buffer.byteLength(raw)<65536);assert.equal(Object.keys(verifyMainDemoSourceBinding(JSON.parse(raw),sourceRaw)).length,1600);
});
test('real tracked inventory remains bounded independently of 128 action records',()=>{
  const root=fileURLToPath(new URL('../../',import.meta.url));
  const names=execFileSync('git',['ls-files','-z','yadinassi','pyproject.toml','tests/browser_ui','frontend/catalog','frontend/configuration','frontend/main-demo','frontend/form','examples/demo','.github/workflows/main-demo-browser-qa.yml'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean);
  const report=fixture();report.binding.source=Object.fromEntries(names.map(name=>[name,hash(readFileSync(root+name))]));
  report.actions=Array.from({length:128},(_,i)=>'realistically-bounded-action-label-'+i);
  const {raw,sourceRaw}=encodeMainDemoReport(report);
  assert.equal(Object.keys(verifyMainDemoSourceBinding(JSON.parse(raw),sourceRaw)).length,names.length);
});
test('source mutation replacement wrong commit tree count and digest rejected',()=>{
  const {raw,sourceRaw}=encodeMainDemoReport(fixture());const report=JSON.parse(raw);
  assert.throws(()=>verifyMainDemoSourceBinding(report,sourceRaw.replace('c','d')),/source_binding_digest/);
  for(const [key,value] of [['commit','d'.repeat(40)],['tree','d'.repeat(40)]]){
    const changed=structuredClone(report);changed.binding[key]=value;
    assert.throws(()=>verifyMainDemoSourceBinding(changed,sourceRaw),new RegExp('source_binding_'+key));
  }
  for(const [key,value] of [['files',99],['bytes',1],['sha256','0'.repeat(64)],['file','other.json']]){
    const changed=structuredClone(report);changed.binding.sourceArtifact[key]=value;
    assert.throws(()=>verifyMainDemoSourceBinding(changed,sourceRaw));
  }
});
test('execution report and source inventory retain independent hard caps',()=>{
  const report=fixture();report.diagnostic='x'.repeat(65536);
  assert.throws(()=>encodeMainDemoReport(report),/report_budget/);
  delete report.diagnostic;report.binding.source={};
  for(let i=0;i<14000;i++)report.binding.source['long/path/file'+i+'.py']='c'.repeat(64);
  assert.throws(()=>encodeMainDemoReport(report),/source_binding_budget/);
});
test('capabilities rejected from both artifacts, including source paths',()=>{
  const report=fixture();report.failure.reason='SECRET';
  assert.throws(()=>encodeMainDemoReport(report,['SECRET']),/capability_leak/);
  report.failure.reason='step_failed';report.binding.source['SECRET/file.py']='c'.repeat(64);
  assert.throws(()=>encodeMainDemoReport(report,['SECRET']),/capability_leak/);
});
test('early failure without source binding stays failure without fabricated artifact',()=>{
  const report=fixture();delete report.binding;
  const encoded=encodeMainDemoReport(report);
  assert.equal(encoded.sourceRaw,null);assert.equal(encoded.sourceArtifact,null);assert.equal(JSON.parse(encoded.raw).status,'FAIL');
});
test('source paths and hash shape fail closed',()=>{
  for(const path of ['/etc/passwd','../x','a/../b','a\\b']){
    const report=fixture();report.binding.source={[path]:'c'.repeat(64)};
    assert.throws(()=>encodeMainDemoReport(report),/source_binding_path/);
  }
  const report=fixture();report.binding.source={'ok.py':'bad'};
  assert.throws(()=>encodeMainDemoReport(report),/source_binding_hash/);
});
