/** Keep execution evidence bounded independently of the growing source inventory. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const sha256=raw=>createHash('sha256').update(raw).digest('hex');
export function encodeMainDemoReport(report,tokens=[]){
  let sourceRaw=null,sourceArtifact=null;
  const result={...report,evidenceSchema:2};
  if(report.binding?.source!==undefined){
    const source=report.binding.source;
    assert.ok(source&&typeof source==='object'&&!Array.isArray(source),'source_binding_shape');
    const names=Object.keys(source);
    for(const name of names){
      assert.ok(name.length>0&&!name.startsWith('/')&&!name.includes('\\')&&!name.split('/').includes('..'),'source_binding_path');
      assert.match(source[name],/^[a-f0-9]{64}$/,'source_binding_hash');
    }
    sourceRaw=JSON.stringify({schema:1,commit:report.binding.commit,tree:report.binding.tree,source})+'\n';
    // Separate bounded inventory, not an enlarged execution-report allowance.
    assert.ok(Buffer.byteLength(sourceRaw)<=1024*1024,'source_binding_budget');
    sourceArtifact={file:'source-binding.json',files:names.length,bytes:Buffer.byteLength(sourceRaw),sha256:sha256(sourceRaw)};
    const {source:unused,...binding}=report.binding;
    result.binding={...binding,sourceArtifact};
  }
  const raw=JSON.stringify(result)+'\n';
  assert.ok(Buffer.byteLength(raw)<=65536,'report_budget');
  assert.ok(!tokens.some(token=>raw.includes(token)||(sourceRaw!==null&&sourceRaw.includes(token))),'capability_leak');
  return {raw,sourceRaw,sourceArtifact};
}

/** Verify a downloaded source inventory against the digest in a result report. */
export function verifyMainDemoSourceBinding(report,sourceRaw){
  const descriptor=report.binding?.sourceArtifact;
  assert.equal(report.evidenceSchema,2,'report_schema');
  assert.equal(descriptor?.file,'source-binding.json','source_binding_file');
  assert.equal(typeof sourceRaw,'string','source_binding_bytes');
  assert.ok(Buffer.byteLength(sourceRaw)<=1024*1024,'source_binding_budget');
  assert.equal(Buffer.byteLength(sourceRaw),descriptor.bytes,'source_binding_size');
  assert.equal(sha256(sourceRaw),descriptor.sha256,'source_binding_digest');
  const inventory=JSON.parse(sourceRaw);
  assert.equal(inventory.schema,1,'source_binding_schema');
  assert.equal(inventory.commit,report.binding.commit,'source_binding_commit');
  assert.equal(inventory.tree,report.binding.tree,'source_binding_tree');
  assert.equal(Object.keys(inventory.source).length,descriptor.files,'source_binding_count');
  return inventory.source;
}
