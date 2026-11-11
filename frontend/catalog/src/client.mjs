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
    catch(error){if(error?.preDispatch===true)throw error;this.uncertain=true;throw Error('Connection interrupted. Do not repeat Save; resynchronize first.');}
    if(!reply||typeof reply!=='object'||reply.jsonrpc!=='2.0'||reply.id!==id||
       Number.isInteger(reply.id)===false||Boolean(reply.result)===Boolean(reply.error)){
      this.uncertain=true;throw Error('Invalid editor response; resynchronize before editing.');
    }
    const snapshot=reply.result??reply.error?.data?.snapshot;
    if(snapshot){
      try{validateSnapshot(snapshot);}catch(error){if(error?.preDispatch===true)throw error;this.uncertain=true;throw error;}
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
  if(field.kind==='catalog_ref'){
    if(typeof value!=='string'||!field.choices?.some(choice=>choice.value===value))throw Error('Select an available reference');
    return {type:'CatalogRef',catalog:field.value.catalog,record:value};
  }
  if(field.kind==='boolean'){
    if(typeof value!=='boolean')throw Error('Boolean input required');
    return {type:'Boolean',value};
  }
  // Decimal/date parsing is host-owned. Never JS Number(), parseFloat() or Date.
  if(typeof value!=='string')throw Error('Text input required');
  if(field.kind==='datetime'&&/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$/.test(value))value+=':00';
  return {type:'String',value};
}

// Display row numbers may change after deletion. Only the host-issued row UUID
// and section name identify a draft or a row event; never use array indexes.
export const rowDraftKey=(section,row)=>JSON.stringify([section,row]);
export function editorDraft(editor){
  return {
    fields:Object.fromEntries((editor?.fields||[]).map(field=>[field.control,field.inputText])),
    rows:Object.fromEntries((editor?.sections||[]).flatMap(section=>
      section.rows.map(row=>[rowDraftKey(section.name,row.id),row.field.inputText])))
  };
}
// Callers keep drafts only within the same editor identity. A successful single
// field event adopts its normalized value without discarding unrelated input.
export function reconcileDraft(editor,draft,acceptedControl){
  const fresh=editorDraft(editor);
  for(const kind of ['fields','rows']){
    for(const key of Object.keys(fresh[kind])){
      if(!(kind==='fields'&&key===acceptedControl)&&Object.hasOwn(draft[kind]||{},key))
        fresh[kind][key]=draft[kind][key];
    }
  }
  return fresh;
}
/** Detached ownership reads may replace an editor or retire a row. Never
 * silently retarget or erase its raw input; callers expose these values for copying. */
export function orphanedDraft(previous, next, draft) {
  const before=editorDraft(previous), after=editorDraft(next), result={fields:{},rows:{}};
  for(const kind of ['fields','rows']) {
    for(const [key,value] of Object.entries(draft?.[kind]||{})) {
      if(value!==before[kind][key] && (previous?.editorId!==next?.editorId || !Object.hasOwn(after[kind],key)))
        Object.defineProperty(result[kind],key,{value,enumerable:true,configurable:true,writable:true});
    }
  }
  return Object.keys(result.fields).length||Object.keys(result.rows).length?result:null;
}
function draftChanges(editor,draft){
  const changes=[];
  for(const field of editor?.fields||[]){
    if(Object.hasOwn(draft.fields||{},field.control)&&draft.fields[field.control]!==field.inputText)
      changes.push({event:'change',field,value:draft.fields[field.control],values:{control:field.control}});
  }
  for(const section of editor?.sections||[]){
    for(const row of section.rows){
      const key=rowDraftKey(section.name,row.id);
      if(Object.hasOwn(draft.rows||{},key)&&draft.rows[key]!==row.field.inputText)
        changes.push({event:'changeRow',field:row.field,readOnly:section.readOnly,value:draft.rows[key],
          values:{section:section.name,row:row.id}});
    }
  }
  return changes;
}
export const hasDraftChanges=(editor,draft)=>draftChanges(editor,draft).length>0;
export function draftEvents(editor,draft){
  const changes=draftChanges(editor,draft);
  if(changes.length&&(editor.editingLocked||editor.sourceStale))throw Error('Editing is locked; current inputs are preserved.');
  return changes.map(change=>{
    if(change.readOnly||change.field.readOnly||change.field.enabled===false)
      throw Error('A changed field is read-only; current inputs are preserved.');
    return {event:change.event,values:{...change.values,value:typedInput(change.field,change.value)}};
  });
}
export async function flushDraft(client,editor,draft){
  // Validate the entire batch before sending anything. Each accepted event
  // advances the client's authoritative revision; a failure stops the batch.
  for(const change of draftEvents(editor,draft)){
    const current=client.snapshot?.state?.editor;
    if(current?.editorId!==editor.editorId||current?.editingLocked||current?.sourceStale)
      throw Error('Editor changed while applying inputs; current inputs are preserved.');
    await client.event(change.event,change.values);
  }
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
