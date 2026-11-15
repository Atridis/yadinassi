/** Verify local-download evidence before it may enter public QA artifacts. */
import assert from 'node:assert/strict';
export function verifyFormCheckReport(raw,state,token){
 assert.equal(typeof token,'string');assert.ok(token.length>0);assert.ok(!raw.includes(token));
 const xml=state.form_preview,module=state.module_preflight;
 const expected={schema:'yadinassi-source-form-check/1',name:xml.name,
  scope:'Static XML projection and BSL preflight only; not runtime or native parity',
  xml:{source_path:xml.source_path,source_sha256:xml.source_sha256,status:xml.status,counts:xml.counts,diagnostics:xml.diagnostics,omitted_diagnostics:xml.omitted_diagnostics},
  module:{source_path:module.module_path,source_sha256:module.module_sha256,xml_sha256:module.xml_sha256,compilation_profile:module.compilation_profile,status:module.status,error:module.error,handler_names:module.handler_names},
  runtime_checked:false,storage_granted:false,native_parity:false};
 assert.equal(xml.name,module.name);assert.equal(xml.source_sha256,module.xml_sha256);
 const report=JSON.parse(raw);assert.deepEqual(report,expected);return report;
}
