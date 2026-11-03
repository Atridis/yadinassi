import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SCENARIOS,ARTIFACTS,launchURL,launchOutputReader,allowedRequest,redact,childEnvironment,
  ownBrowserPid,commandLineArgs,sandboxCommand,sandboxStatus,completedResult,sha256} from './support.mjs';
const token='a'.repeat(43), origin='http://127.0.0.1:12345';
test('exact local launch URL',()=>assert.equal(launchURL(origin+'/#session='+token).origin,origin));
test('launch URL rejects credentials, external/invalid host, query and ports',()=>{
  for(const value of ['http://example.org/#session='+token,'http://localhost:12345/#session='+token,
    'http://u:p@127.0.0.1:12345/#session='+token,'http://127.0.0.1:99999/#session='+token,
    origin+'/?x=1#session='+token,origin+'/#session=short']) assert.throws(()=>launchURL(value));
});
test('request admission is exact origin and finite path',()=>{
  assert.equal(allowedRequest(origin+'/rpc',origin),true);
  for(const value of [origin+'/app.js?x=1',origin+'/database.sqlite','https://example.org/',
    'http://127.0.0.1:12346/', 'file:///etc/passwd']) assert.equal(allowedRequest(value,origin),false);
});
test('redaction removes known and fragment capabilities',()=>{
  const value=redact('goto '+origin+'/#session='+token+' header '+token,[token]);
  assert.equal(value.includes(token),false);assert.ok(value.includes('[redacted]'));
  assert.equal(redact('x'.repeat(8180)+token,[token]),'x'.repeat(8180)+'[redacted]');
});
test('redaction bounds output',()=>assert.ok(redact('x'.repeat(20000)).length<=8192));
test('child env excludes tokens, proxies and inherited debug hooks',()=>{
  assert.deepEqual(childEnvironment({PATH:'/bin',GITHUB_TOKEN:'secret',NODE_OPTIONS:'bad',
    PYTHONPATH:'bad',HTTPS_PROXY:'bad',DEBUG:'pw:*'},'/owned'),{
      HOME:'/owned',TMPDIR:'/owned',LANG:'C.UTF-8',PYTHONDONTWRITEBYTECODE:'1',
      PYTHONIOENCODING:'utf-8',PATH:'/bin'});
});
test('sandbox command requires pipe and rejects disabling flags',()=>{
  assert.equal(sandboxCommand(['chrome','--headless','--remote-debugging-pipe']),true);
  for(const flag of ['--no-sandbox','--disable-setuid-sandbox','--disable-namespace-sandbox',
    '--disable-seccomp-filter-sandbox','--disable-gpu-sandbox','--single-process',
    '--no-zygote','--disable-web-security']) assert.throws(()=>sandboxCommand(['--remote-debugging-pipe',flag]));
  assert.throws(()=>sandboxCommand([]));
});
test('sandbox status accepts positive namespace and seccomp evidence',()=>
  assert.deepEqual(sandboxStatus('Layer 1 Sandbox\tNamespace\nSeccomp-BPF sandbox\tYes'),{layer1:true,seccompBpf:true}));
test('sandbox status fails closed for absent or negative evidence',()=>{
  for(const text of ['', 'Layer 1 Sandbox Namespace\nSeccomp-BPF sandbox No',
    'Namespace sandbox No\nSeccomp-BPF sandbox Yes']) assert.throws(()=>sandboxStatus(text));
});
test('all eight ordered actual scenarios required',()=>{
  const records=SCENARIOS.map(name=>({name,status:'PASS'}));assert.equal(completedResult(records),true);
  assert.equal(completedResult(records.slice(0,7)),false);
  assert.equal(completedResult([...records].reverse()),false);
  assert.equal(completedResult(records.map(row=>({...row,status:'SKIP'}))),false);
});
test('fixed artifact list excludes browser state and database',()=>
  assert.deepEqual(ARTIFACTS,['result.json','manifest.json','list.png','editor.png','narrow.png']));
test('hash manifest uses exact bytes',()=>assert.equal(sha256('abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'));

test('host URL reader handles split capability and stops retaining after completion',()=>{
  const reader=launchOutputReader(),line=origin+'/#session='+token+'\n';
  assert.equal(reader(Buffer.from(line.slice(0,-20))),null);
  assert.equal(reader(Buffer.from(line.slice(-20))).origin,origin);
  assert.equal(reader(Buffer.alloc(10000)),null);
});
test('host URL reader rejects before overflow and remains settled',()=>{
  const reader=launchOutputReader();assert.equal(reader(Buffer.alloc(4096,120)),null);
  assert.throws(()=>reader(Buffer.from('x')),/host_output_budget/);
  assert.equal(reader(Buffer.alloc(10000)),null);
});

test('browser PID comes only from the unique browser process in its own CDP session',()=>{
  assert.equal(ownBrowserPid([{type:'renderer',id:25},{type:'browser',id:24}]),24);
});
test('browser PID rejects absent, duplicate, unsafe, negative and string identities',()=>{
  for(const value of [null,[],[{type:'renderer',id:1}],[{type:'browser',id:1},{type:'browser',id:2}],
    [{type:'browser',id:0}],[{type:'browser',id:-1}],[{type:'browser',id:'2'}],
    [{type:'browser',id:1.5}],[{type:'browser',id:Number.MAX_SAFE_INTEGER+1}],Array(129).fill({type:'browser',id:2})])
    assert.throws(()=>ownBrowserPid(value),/browser_pid_invalid/);
});

test('bounded own command line decodes NUL-separated actual arguments',()=>{
  const raw=Buffer.from('chrome'+String.fromCharCode(0)+'--remote-debugging-pipe'+String.fromCharCode(0));
  assert.deepEqual(commandLineArgs(raw),['chrome','--remote-debugging-pipe']);
  assert.equal(sandboxCommand(commandLineArgs(raw)),true);
});
test('own command line rejects missing terminator, nonbytes, overflow and invalid UTF8',()=>{
  for(const raw of ['',Buffer.alloc(0),Buffer.from('chrome'),Buffer.alloc(16385),Buffer.from([255,0])])
    assert.throws(()=>commandLineArgs(raw));
});
