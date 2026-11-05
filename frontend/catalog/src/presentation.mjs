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

/** The host omits navigation while editing. Keep only a labelled, inert preview. */
export function workspacePreview(previous,snapshot){
  const state=snapshot?.state;
  if(!state||state.kind==='closed')return {catalogs:[],list:null};
  if(!state.editor)return {catalogs:state.catalogs,list:state.list};
  const {catalog,catalogName}=state.editor;
  return {
    catalogs:previous?.catalogs?.some(item=>item.id===catalog)?previous.catalogs:[{id:catalog,name:catalogName}],
    list:previous?.list?.catalog===catalog?previous.list:null,
  };
}
