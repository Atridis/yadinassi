/** Presentation preferences only. Never persist capabilities, records or drafts. */
export const THEME_KEY='yadinassi.catalog.theme';
export const themePreference=value=>['dark','light','system'].includes(value)?value:'dark';
export const resolvedTheme=(preference,systemDark)=>
  preference==='system'?(systemDark?'dark':'light'):themePreference(preference);

export function readTheme(environment){
  try{return themePreference(environment.localStorage.getItem(THEME_KEY));}
  catch{return 'dark';}
}
export function rememberTheme(environment,preference){
  try{environment.localStorage.setItem(THEME_KEY,themePreference(preference));}
  catch{/* A blocked preference store must not interrupt editing. */}
}

/** The host supplies a fresh retained list after Save; never patch it from a draft. */
export function workspacePreview(previous,snapshot){
  const state=snapshot?.state;
  if(!state||state.kind==='closed')return {catalogs:[],list:null};
  if(!state.editor)return {catalogs:state.catalogs,list:state.list};
  const {catalog,catalogName}=state.editor;
  return {
    catalogs:previous?.catalogs?.some(item=>item.id===catalog)?previous.catalogs:[{id:catalog,name:catalogName}],
    list:state.list?.catalog===catalog?state.list:null,
  };
}

/** Check results belong to the current list snapshot, never the editor preview. */
export function listCheckPresentation(snapshot){
  const state=snapshot?.state;
  if(state?.kind!=='list'||state.editor||!state.listCheck?.available)
    return {available:false,messages:[]};
  return {available:true,messages:state.listCheck.messages||[]};
}

/** Only the host's typed Boolean marks a persisted list record. */
export const isDeletionMarked=row=>row?.deletionMark?.type==='Boolean'&&row.deletionMark.value===true;

/** Selection is scoped to the visible authoritative page, never row positions. */
const recordKey = (reference,catalog) => reference?.type==='CatalogRef'&&reference.catalog===catalog&&
  typeof reference.record==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(reference.record)&&
  reference.record!=='00000000-0000-0000-0000-000000000000'?reference.record.toLowerCase():null;
export function reconcileSelection(previous,snapshot){
  const list=snapshot?.state?.list,editor=snapshot?.state?.editor;
  if(!list||snapshot.state.kind==='closed')return {catalog:null,records:[]};
  const visible=new Set(list.rows.map(row=>recordKey(row.reference,list.catalog)).filter(Boolean));
  const saved=editor&&['saved','unchanged'].includes(editor.saveState)&&!editor.editingLocked?
    recordKey(editor.reference,list.catalog):null;
  const records=saved&&visible.has(saved)?[saved]:previous?.catalog===list.catalog?
    [...new Set(previous.records)].filter(key=>visible.has(key)):[];
  return {catalog:list.catalog,records};
}
export function selectRecord(previous,list,reference,multiple=false){
  const current=reconcileSelection(previous,{state:{kind:'list',list}});
  const key=recordKey(reference,list?.catalog);
  if(!key||!list.rows.some(row=>recordKey(row.reference,list.catalog)===key))return current;
  if(!multiple)return {catalog:list.catalog,records:[key]};
  return {catalog:list.catalog,records:current.records.includes(key)?current.records.filter(value=>value!==key):[...current.records,key]};
}
export function selectedReference(selection,list){
  const current=reconcileSelection(selection,{state:{kind:'list',list}});
  if(current.records.length!==1)return null;
  return list.rows.find(row=>recordKey(row.reference,list.catalog)===current.records[0])?.reference||null;
}

/** Immediate command authority, independent of a framework's deferred repaint. */
export function createSelectionModel(){
  let current={catalog:null,records:[]};
  return {
    get current(){return current;},
    reconcile(snapshot){current=reconcileSelection(current,snapshot);return current;},
    select(list,reference,multiple=false){current=selectRecord(current,list,reference,multiple);return current;},
    target(list){return selectedReference(current,list);},
    empty(list){return reconcileSelection(current,{state:{kind:'list',list}}).records.length===0;},
  };
}
