export const PROTOCOL='yadinassi-main-demo/1';
const keys=(v,n)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===n.length&&n.every(k=>Object.hasOwn(v,k));
const surfaces=['catalogs','documents'];
export class MainDemoClient{
  constructor(exchange){this.exchange=exchange;this.state=null;this.pending=false;this.uncertain=false;this.counter=0;}
  async call(method,params,{read=false}={}){
    if(this.pending||this.uncertain&&!read)throw Error('Read current demo state before continuing');
    if(this.counter>=2147483647)throw Error('Request limit');
    this.pending=true;const id=++this.counter;
    try{
      const response=await this.exchange({jsonrpc:'2.0',id,method,params});
      if(!keys(response,['jsonrpc','id','result'])||response.jsonrpc!=='2.0'||response.id!==id)throw Error('Invalid demo reply');
      const r=response.result,s=r?.state;
      if(!keys(r,['protocol','state','error','payload'])||r.protocol!==PROTOCOL||!keys(s,['kind','surface','epoch','canSwitch','uncertain'])||
        !['main-demo','closed'].includes(s.kind)||!surfaces.includes(s.surface)||typeof s.canSwitch!=='boolean'||typeof s.uncertain!=='boolean'||
        !(s.epoch===null&&(s.kind==='closed'||s.uncertain&&!s.canSwitch)||typeof s.epoch==='string'&&/^[0-9a-f]{32}$/.test(s.epoch))||
        ![null,'closed','stale_surface','finish_current_surface'].includes(r.error))throw Error('Invalid demo state');
      if(method==='demo.dispatch'&&!r.error&&(!r.payload||r.payload.jsonrpc!=='2.0'||r.payload.id!==params.request.id||!keys(r.payload,['jsonrpc','id','result'])&&!keys(r.payload,['jsonrpc','id','error'])))throw Error('Invalid nested reply');
      if(method!=='demo.dispatch'&&r.payload!==null)throw Error('Unexpected demo payload');
      this.state=s;this.uncertain=s.uncertain;
      if(r.error)throw Object.assign(Error(r.error),{known:true});
      return r.payload;
    }catch(error){if(!error.known)this.uncertain=true;throw error;}finally{this.pending=false;}
  }
  hello(){return this.call('demo.hello',{protocol:PROTOCOL},{read:true});}
  snapshot(){return this.call('demo.snapshot',{protocol:PROTOCOL},{read:true});}
  select(surface){if(!surfaces.includes(surface)||!this.state?.canSwitch)throw Error('Finish current surface');return this.call('demo.select',{epoch:this.state.epoch,surface});}
  dispatch(request,epoch=this.state?.epoch){if(!this.state||epoch!==this.state.epoch)throw Error('Retired surface');return this.call('demo.dispatch',{epoch,request});}
  close(){if(!this.state?.canSwitch)throw Error('Finish current surface');return this.call('demo.close',{epoch:this.state.epoch});}
}
