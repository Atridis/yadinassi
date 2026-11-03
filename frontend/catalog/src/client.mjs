/** Independent renderer client. No runtime/SQL/BSL dependency or automatic write retry. */
export const PROTOCOL='yadinassi-editor/0';
const MAX=2147483647;
const counter=value=>Number.isInteger(value)&&value>=0&&value<=MAX;
export function validateSnapshot(snapshot) {
  if (!snapshot||typeof snapshot!=='object'||Array.isArray(snapshot)||snapshot.protocol!==PROTOCOL||
      snapshot.formId!=='catalog-editor'||!counter(snapshot.revision)||
      !snapshot.state||typeof snapshot.state!=='object'||!snapshot.capabilities||
      !['catalogs','list','editor','closed'].includes(snapshot.state.kind)) throw Error('Invalid editor snapshot');
  return snapshot;
}
export class EditorClient {
  constructor(exchange) {this.exchange=exchange;this.id=0;this.snapshot=null;this.uncertain=false;}
  async request(method,params) {
    const id=++this.id;
    if(id>MAX)throw Error('Request limit reached');
    let reply;
    try {reply=await this.exchange({jsonrpc:'2.0',id,method,params});}
    catch(error){this.uncertain=true;throw Error('Connection interrupted. Do not repeat Save; resynchronize first.');}
    if(!reply||typeof reply!=='object'||reply.jsonrpc!=='2.0'||reply.id!==id||
       Number.isInteger(reply.id)===false||Boolean(reply.result)===Boolean(reply.error)){
      this.uncertain=true;throw Error('Invalid editor response; resynchronize before editing.');
    }
    const snapshot=reply.result??reply.error?.data?.snapshot;
    if(snapshot){
      try{validateSnapshot(snapshot);}catch(error){this.uncertain=true;throw error;}
      if(this.snapshot&&snapshot.revision<this.snapshot.revision){this.uncertain=true;throw Error('Out-of-order editor response');}
      this.snapshot=snapshot;
      this.uncertain=false;
    } else {this.uncertain=true;}
    if(reply.error) {
      const error=Error(reply.error?.data?.reason||'Editor request rejected');
      error.snapshot=this.snapshot;
      throw error;
    }
    return this.snapshot;
  }
  hello(){return this.request('editor.hello',{protocol:PROTOCOL});}
  resync(){return this.request('editor.snapshot',{});}
  event(event,values={}){
    if(!this.snapshot||this.uncertain)throw Error('Resynchronize before editing');
    return this.request('editor.event',{event,baseRevision:this.snapshot.revision,...values});
  }
}
export function typedInput(field,value){
  if(field.kind==='boolean'){
    if(typeof value!=='boolean')throw Error('Boolean input required');
    return {type:'Boolean',value};
  }
  // Decimal/date parsing is host-owned. Never JS Number(), parseFloat() or Date.
  if(typeof value!=='string')throw Error('Text input required');
  if(field.kind==='datetime'&&/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$/.test(value))value+=':00';
  return {type:'String',value};
}
export async function readBoundedJSON(response){
  if(!response.ok)throw Error(`Local UI transport rejected request (${response.status})`);
  const reader=response.body.getReader();const chunks=[];let size=0;
  for(;;){const{done,value}=await reader.read();if(done)break;size+=value.byteLength;
    if(size>131072){await reader.cancel();throw Error('Oversized response');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}

/** Consume a launch capability, including same-document hash navigation. */
export function takeSessionCapability(location,history){
  const value=new URLSearchParams(location.hash.slice(1)).get('session');
  if(location.hash)history.replaceState(null,'',location.pathname);
  return typeof value==='string'&&/^[A-Za-z0-9_-]{32,128}$/.test(value)?value:null;
}
