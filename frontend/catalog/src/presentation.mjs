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
