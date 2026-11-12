import test from 'node:test';import assert from 'node:assert/strict';
import {MainDemoFilterCapture} from './main_demo_filter_capture.mjs';
const origin='http://127.0.0.1:12345',url=origin+'/rpc';
const packet={id:7,method:'demo.dispatch',params:{request:{id:9,method:'application.catalogFilter',params:{}}}};
const raw=Buffer.from('{"id":7,"result":{"payload":{"id":9}}}');
const limits={fetchTimeout:100,bodyTimeout:100,bounded:(promise)=>promise};
function fixture({requestURL=url,responseURL=url,status=200,bytes=raw,disposeError=false}={}){
 const seen={fetch:[],fulfill:[],dispose:0,abort:0};
 const response={url:()=>responseURL,status:()=>status,body:async()=>bytes,dispose:async()=>{seen.dispose++;if(disposeError)throw Error('private detail');}};
 const route={request:()=>({url:()=>requestURL,postDataJSON:()=>packet}),fetch:async args=>{seen.fetch.push(args);return response;},
   fulfill:async args=>{seen.fulfill.push(args);},abort:async()=>{seen.abort++;}};
 return {route,seen,response};
}
async function rejection(options,code){
 const c=new MainDemoFilterCapture(),t=c.begin('application.catalogFilter'),f=fixture(options);
 const failed=assert.rejects(t.ready,new RegExp(code));await c.route(f.route,origin,limits);await failed;
 assert.equal(f.seen.abort,1);assert.throws(()=>c.consume(t,7),new RegExp(code));c.clear(t);return f;
}
test('captures exactly one actual fetch and delivers identical bytes; single consumption',async()=>{
 const c=new MainDemoFilterCapture(),t=c.begin('application.catalogFilter'),f=fixture();
 await c.route(f.route,origin,limits);await t.ready;
 assert.deepEqual(f.seen.fetch,[{timeout:100,maxRedirects:0,maxRetries:0}]);
 const captured=c.consume(t,7);assert.equal(captured.bytes,raw);assert.equal(f.seen.fulfill[0].body,captured.bytes);
 assert.equal(f.seen.fulfill[0].response,f.response);assert.equal(f.seen.dispose,1);
 assert.throws(()=>c.consume(t,7),/filter_capture_consumed/);c.clear(t);
});
test('one expected method pending, unknown methods refused, clear settles pending waiter',async()=>{
 const c=new MainDemoFilterCapture();assert.throws(()=>c.begin('application.form'),/filter_capture_method/);
 const t=c.begin('application.catalogFilter');assert.throws(()=>c.begin('application.report'),/filter_capture_pending/);
 const rejected=assert.rejects(t.ready,/filter_capture_retired/);c.clear(t);await rejected;
});
test('foreign request and response endpoints are refused without redirect or retry',async()=>{
 const a=await rejection({requestURL:'https://example.com/rpc'},'filter_capture_request_origin');assert.equal(a.seen.fetch.length,0);
 const b=await rejection({responseURL:origin+'/elsewhere'},'filter_capture_response_origin');assert.equal(b.seen.fetch.length,1);assert.equal(b.seen.dispose,1);
});
test('non200 and over-budget body fail closed with disposal',async()=>{
 await rejection({status:503},'filter_capture_http');const f=await rejection({bytes:Buffer.alloc(131073)},'filter_reply_body_budget');assert.equal(f.seen.fulfill.length,0);assert.equal(f.seen.dispose,1);
});
test('outer and inner response ids must match the actual browser request',async()=>{
 await rejection({bytes:Buffer.from('{"id":8,"result":{"payload":{"id":9}}}')},'filter_capture_outer_id');
 await rejection({bytes:Buffer.from('{"id":7,"result":{"payload":{"id":8}}}')},'filter_capture_inner_id');
});
test('invalid JSON and cleanup failure are closed failures, never fallback reads',async()=>{
 await rejection({bytes:Buffer.from('<html>private</html>')},'filter_capture_json');await rejection({disposeError:true},'filter_capture_cleanup');
});
test('duplicate matching browser request is not fetched again and poisons capture',async()=>{
 const c=new MainDemoFilterCapture(),t=c.begin('application.catalogFilter'),f=fixture();await c.route(f.route,origin,limits);await t.ready;
 await c.route(f.route,origin,limits);assert.equal(f.seen.fetch.length,1);assert.throws(()=>c.consume(t,7),/filter_capture_duplicate/);c.clear(t);
});
test('consumer id binding and unrelated method do not silently consume or fetch',async()=>{
 const c=new MainDemoFilterCapture(),t=c.begin('application.report'),f=fixture();assert.equal(await c.route(f.route,origin,limits),false);assert.equal(f.seen.fetch.length,0);
 const rejected=assert.rejects(t.ready,/filter_capture_retired/);c.clear(t);await rejected;
 const next=c.begin('application.catalogFilter');await c.route(f.route,origin,limits);await next.ready;
 assert.throws(()=>c.consume(next,8),/filter_capture_consumer_id/);c.clear(next);
});
