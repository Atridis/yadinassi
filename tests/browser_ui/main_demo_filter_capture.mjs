/** Single-use observer of one real browser RPC; never sends a second request. */
import assert from 'node:assert/strict';
const METHODS=new Set(['application.catalog','application.catalogFilter','application.report']);
const endpoint=(value,origin)=>{const url=new URL(value);return url.origin===origin&&url.pathname==='/rpc'&&!url.search&&!url.hash&&!url.username&&!url.password;};
export class MainDemoFilterCapture {
  #active=null;
  begin(method){
    assert.ok(!this.#active,'filter_capture_pending');
    assert.ok(METHODS.has(method),'filter_capture_method');
    const ticket={method,claimed:false,consumed:false,value:null,error:null};
    ticket.ready=new Promise((resolve,reject)=>{ticket.resolve=resolve;ticket.reject=reject;});
    this.#active=ticket;return ticket;
  }
  async route(route,origin,{fetchTimeout,bodyTimeout,bounded}){
    const ticket=this.#active,packet=route.request().postDataJSON();
    if(!ticket||packet?.method!=='demo.dispatch'||packet.params?.request?.method!==ticket.method)return false;
    let response;
    try{
      assert.ok(!ticket.claimed,'filter_capture_duplicate');ticket.claimed=true;
      assert.ok(endpoint(route.request().url(),origin),'filter_capture_request_origin');
      const inner=packet.params.request;
      assert.ok((typeof packet.id==='number'||typeof packet.id==='string')&&(typeof inner.id==='number'||typeof inner.id==='string'),'filter_capture_request_id');
      response=await route.fetch({timeout:fetchTimeout,maxRedirects:0,maxRetries:0});
      assert.ok(endpoint(response.url(),origin),'filter_capture_response_origin');
      assert.equal(response.status(),200,'filter_capture_http');
      const bytes=await bounded(response.body(),bodyTimeout,'filter_reply_body_timeout');
      assert.ok(Buffer.isBuffer(bytes)&&bytes.length<=131072,'filter_reply_body_budget');
      let body;try{body=JSON.parse(bytes.toString('utf8'));}catch{throw Error('filter_capture_json');}
      assert.equal(body.id,packet.id,'filter_capture_outer_id');
      assert.equal(body.result?.payload?.id,inner.id,'filter_capture_inner_id');
      assert.equal(this.#active,ticket,'filter_capture_retired');
      assert.equal(ticket.error,null,'filter_capture_failed');
      // The browser receives this exact buffer, not a reserialized JSON value.
      await route.fulfill({response,body:bytes});
      ticket.value={packet,bytes};
    }catch(error){
      const codes=['filter_capture_duplicate','filter_capture_request_origin','filter_capture_response_origin',
        'filter_capture_request_id','filter_capture_http','filter_reply_body_timeout','filter_reply_body_budget',
        'filter_capture_json','filter_capture_outer_id','filter_capture_inner_id','filter_capture_retired','filter_capture_failed'];
      const code=codes.find(code=>error?.message===code||error?.message?.startsWith(code+'\n'))||'filter_capture_transport';
      ticket.error=Error(code);
    }finally{
      try{if(response)await response.dispose();}catch{ticket.error=Error('filter_capture_cleanup');}
      if(ticket.error){ticket.reject(ticket.error);try{await route.abort('failed');}catch{/* ready carries the closed failure */}}
      else ticket.resolve();
    }
    return true;
  }
  consume(ticket,outerId){
    assert.equal(this.#active,ticket,'filter_capture_retired');
    if(ticket.error)throw ticket.error;
    assert.ok(ticket.value&&!ticket.consumed,'filter_capture_consumed');
    assert.equal(ticket.value.packet.id,outerId,'filter_capture_consumer_id');
    ticket.consumed=true;return ticket.value;
  }
  clear(ticket){
    assert.equal(this.#active,ticket,'filter_capture_retired');
    this.#active=null;ticket.value=null;ticket.reject(Error('filter_capture_retired'));
  }
}
