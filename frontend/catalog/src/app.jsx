import {h,render,Fragment} from 'preact';
import {useEffect,useRef,useState} from 'preact/hooks';
import {EditorClient,typedInput,readBoundedJSON,takeSessionCapability,
  rowDraftKey,editorDraft,reconcileDraft,hasDraftChanges,flushDraft} from './client.mjs';
import {readTheme,rememberTheme,resolvedTheme,workspacePreview,listCheckPresentation,isDeletionMarked} from './presentation.mjs';

let token=takeSessionCapability(location,history);
// The capability is memory-only: never store it with the presentation preference.
// Reopen the launch URL after a page reload to reattach without replaying writes.
const transport=async request=>readBoundedJSON(await fetch('/rpc',{method:'POST',cache:'no-store',
  credentials:'omit',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},
  body:JSON.stringify(request)+'\n'}));
const client=new EditorClient(transport);
const text=value=>value?.type==='String'?value.value:value?.type==='Boolean'?(value.value?'Yes':'No'):value?.value??'';
const sectionReason=reason=>({
  'section-profile-unsupported':'Only sections with one catalog reference column are editable.',
  'reference-options-unavailable':'Reference choices are unavailable or exceed the supported limit.',
  'section-row-limit':'This record exceeds the 32-row editing limit.'
}[reason]||reason||'Unsupported section.');

function App(){
  const [snapshot,setSnapshot]=useState(null),[draft,setDraft]=useState(()=>editorDraft()),[busy,setBusy]=useState(false),
    [error,setError]=useState(''),[filter,setFilter]=useState(''),
    [theme,setTheme]=useState(()=>readTheme(window)),[preview,setPreview]=useState({catalogs:[],list:null});
  const gate=useRef(false),actionPointer=useRef(false);
  const apply=(preserveDraft=false,acceptedControl)=>{if(client.snapshot){setSnapshot(client.snapshot);setPreview(previous=>workspacePreview(previous,client.snapshot));
    setDraft(previous=>preserveDraft?reconcileDraft(client.snapshot.state.editor,previous,acceptedControl):editorDraft(client.snapshot.state.editor));}};
  const changeField=(control,value)=>setDraft(previous=>({...previous,fields:{...previous.fields,[control]:value}}));
  const changeRow=(section,row,value)=>setDraft(previous=>({...previous,rows:{...previous.rows,[rowDraftKey(section,row)]:value}}));
  useEffect(()=>{
    const system=matchMedia('(prefers-color-scheme: dark)');
    const paint=()=>{document.documentElement.dataset.theme=resolvedTheme(theme,system.matches);
      document.documentElement.dataset.themePreference=theme;};
    paint();system.addEventListener('change',paint);
    return()=>system.removeEventListener('change',paint);
  },[theme]);
  const changeTheme=value=>{setTheme(value);rememberTheme(window,value);};
  const editor=snapshot?.state?.editor;
  const localDirty=hasDraftChanges(editor,draft);
  useEffect(()=>{
    const connect=()=>{
      if(gate.current)return;
      gate.current=true;setBusy(true);setError('');
      const previousEditor=client.snapshot?.state?.editor?.editorId;
      const sync=()=>apply(Boolean(previousEditor)&&previousEditor===client.snapshot?.state?.editor?.editorId);
      client.hello().then(sync).catch(e=>{sync();setError(e.message);}).finally(()=>{gate.current=false;setBusy(false);});
    };
    const reattach=()=>{
      const incoming=takeSessionCapability(location,history);
      if(incoming){token=incoming;connect();}
    };
    addEventListener('hashchange',reattach);
    if(token)connect();
    else setError('Session capability missing. Reopen the URL printed by the launcher to reconnect.');
    return()=>removeEventListener('hashchange',reattach);
  },[]);
  useEffect(()=>{
    const warn=event=>{if(localDirty||editor?.dirty||editor?.editingLocked||busy){event.preventDefault();event.returnValue='';}};
    addEventListener('beforeunload',warn);return()=>removeEventListener('beforeunload',warn);
  },[localDirty,editor?.dirty,editor?.editingLocked,busy]);
  async function run(event,values={},flush=false){
    if(gate.current||client.uncertain)return;
    if(event==='checkCard'&&!listCheckPresentation(client.snapshot).available)return;
    if(['addRow','deleteRow','changeRow'].includes(event)&&(!editor||editor.editingLocked||editor.sourceStale))return;
    gate.current=true;setBusy(true);setError('');
    const singleImportedChange=event==='change'&&!flush&&Boolean(editor?.originalForm);
    let flushComplete=!flush,eventComplete=false;
    try{
      if(flush&&editor&&!editor.editingLocked)await flushDraft(client,editor,draft);
      flushComplete=true;
      await client.event(event,values);
      eventComplete=true;
      const current=client.snapshot?.state?.editor;
      if((event==='closeCard'||event==='close')&&current?.state==='open'&&current.dirty&&
          confirm('Discard unsaved changes?')){
        await client.event('command',{control:'CancelButton'});
        if(event==='close'&&client.snapshot?.state?.kind!=='closed')await client.event('close');
      }
    }catch(e){setError(e.message);}
    finally{
      const sameEditor=Boolean(editor?.editorId)&&client.snapshot?.state?.editor?.editorId===editor.editorId;
      apply(sameEditor&&(!flushComplete||!eventComplete||singleImportedChange),
        singleImportedChange&&eventComplete?values.control:undefined);
      gate.current=false;setBusy(false);
    }
  }
  function commitImportedField(field,value,relatedTarget){
    const current=client.snapshot?.state?.editor;
    // A pointer/keyboard transition to a command belongs to that command's
    // existing flush/discard path, never a racing blur request.
    if(actionPointer.current||relatedTarget?.closest?.('[data-editor-action]'))return;
    if(!current?.originalForm||current.editorId!==editor?.editorId||field.readOnly||
       gate.current||client.uncertain||current.editingLocked||current.sourceStale)return;
    const active=current.fields.find(item=>item.control===field.control);
    if(active&&!active.readOnly&&active.inputText!==value)
      run('change',{control:field.control,value:typedInput(field,value)});
  }
  async function resync(){
    if(gate.current)return;gate.current=true;setBusy(true);
    try{await client.resync();setError('');}catch(e){setError(e.message);}finally{apply(client.snapshot?.state?.editor?.editorId===editor?.editorId);gate.current=false;setBusy(false);}
  }
  const state=snapshot?.state;
  const listCheck=listCheckPresentation(snapshot);
  const navigationLocked=busy||client.uncertain||Boolean(editor);
  const catalogs=editor?preview.catalogs:state?.catalogs||[];
  const list=editor?preview.list:state?.list;
  const visibleCatalogs=catalogs.filter(c=>c.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return <main onPointerDownCapture={e=>{actionPointer.current=Boolean(e.target.closest?.('[data-editor-action]'));}}
    onPointerUpCapture={()=>{actionPointer.current=false;}} onPointerCancelCapture={()=>{actionPointer.current=false;}}>
    <header><div><span class="brand">YADINASSI</span><h1>Catalog workspace</h1></div>
      <div class="header-actions"><span class="badge connection">Local SQLite</span>
      <label class="theme-control"><span>Theme</span><select aria-label="Color theme" value={theme}
        onChange={e=>changeTheme(e.currentTarget.value)}><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label>
      {snapshot&&state.kind!=='closed'&&<button data-editor-action="close" class="quiet" disabled={busy||client.uncertain||editor?.editingLocked} onClick={()=>run('close',{},true)}>Close database</button>}</div>
    </header>
    <p class="scope">{editor?.originalForm?'Imported name-validation handlers · local host form adapter · no native parity claim':'Auto-generated editor · bounded references and tabular rows · no imported 1C forms'}</p>
    {error&&<section role="alert" class="notice error"><strong>Action not completed</strong><span>{error}</span>
      {client.uncertain&&token&&<button disabled={busy} onClick={resync}>Resynchronize — do not repeat Save</button>}</section>}
    {!snapshot&&<section class="panel empty">{busy?'Opening database…':'Use the host launcher to select a supported SQLite file.'}</section>}
    {state?.kind==='closed'&&<section class="panel empty"><h2>Database closed</h2><p>No further changes can be made in this session.</p></section>}
    {snapshot&&state.kind!=='closed'&&<div class={'workspace'+(editor?' has-editor':'')}>
      <aside class="panel navigation" aria-label="Catalog navigation"><h2>Catalogs</h2><input aria-label="Filter catalogs" placeholder="Find catalog…" value={filter} onInput={e=>setFilter(e.currentTarget.value)}/>
        <nav aria-label="Catalogs">{visibleCatalogs.map(c=><button key={c.id}
          disabled={navigationLocked} aria-current={(editor?.catalog||list?.catalog)===c.id?'page':undefined} class={(editor?.catalog||list?.catalog)===c.id?'catalog selected':'catalog'} onClick={()=>run('selectCatalog',{catalog:c.id})}><span class="catalog-name">{c.name}</span><span>›</span></button>)}</nav>
        {!visibleCatalogs.length&&<p class="navigation-hint">No matching catalogs.</p>}
        {editor&&<p class="navigation-hint">Close the editor to switch records or catalogs.</p>}
      </aside>
      <section class="panel records" aria-label="Records">{list?<><div class="section-head"><div><h2>{list.catalogName}</h2><span class="muted">{list.total} records</span></div>
        <button class="primary" disabled={navigationLocked||!snapshot.capabilities.canCreate} onClick={()=>run('create')}>+ New record</button></div>
        {editor&&<p class="preview-note">List preview · refreshed when you return</p>}
        {listCheck.messages.length>0&&<div role="status" class="notice" aria-label="Результат проверки карточки">
          {listCheck.messages.map((message,index)=><div key={index}>{message.field&&<strong>{message.field}: </strong>}<span>{message.text}</span></div>)}
        </div>}
        <div class="table-scroll"><table class={listCheck.available?'list-check-table':undefined}><thead><tr><th>Code</th><th>Description</th><th></th></tr></thead><tbody>
          {list.rows.map(row=><tr key={row.reference.record} class={editor?.reference?.record===row.reference.record?'current-record':undefined}><td class="code">{text(row.code)}</td><td>{text(row.description)||<span class="muted">Untitled</span>}{isDeletionMarked(row)&&<span class="badge deletion-mark">Помечен на удаление</span>}</td>
            <td>{listCheck.available&&<button disabled={navigationLocked} onClick={()=>run('checkCard',{reference:row.reference})}>Проверить карточку</button>} <button disabled={navigationLocked} onClick={()=>run('openCard',{reference:row.reference})}>Open →</button></td></tr>)}</tbody></table></div>
        {!list.rows.length&&<div class="empty">No records on this page.
          {listCheck.available&&<button disabled={navigationLocked} onClick={()=>run('checkCard',{reference:null})}>Проверить карточку</button>}</div>}
        <footer class="pagination"><button disabled={navigationLocked||list.offset===0} onClick={()=>run('page',{offset:Math.max(0,list.offset-list.limit),limit:list.limit})}>← Previous</button>
          <span>{Math.min(list.offset+1,list.total)}–{Math.min(list.offset+list.limit,list.total)} of {list.total}</span>
          <button disabled={navigationLocked||list.offset+list.limit>=list.total} onClick={()=>run('page',{offset:list.offset+list.limit,limit:list.limit})}>Next →</button></footer>
      </>:<div class="empty"><h2>{editor?editor.catalogName:'Choose a catalog'}</h2><p>{editor?'Return to records to refresh the list.':'Open a record or create a new one. Changes are only persisted after Save.'}</p></div>}</section>
    {editor&&<section class="panel editor" aria-label="Record editor"><div class="section-head"><div><button data-editor-action="back" class="quiet back" disabled={busy||client.uncertain||editor.editingLocked} onClick={()=>run('closeCard',{},true)}>← Back to records</button>
      <h2>{editor.isNew?'New record':'Edit record'} <span class="muted">/ {editor.catalogName}</span></h2></div>
      <span class={'badge '+((localDirty||editor.dirty)?'dirty':'saved')}>{editor.editingLocked?'Outcome pending':localDirty||editor.dirty?'Unsaved changes':editor.saveState==='saved'?'Saved':'No unsaved changes'}</span></div>
      {editor.status&&(!localDirty||editor.error)&&<div role="status" class={'notice '+(editor.error?'error':'success')}>{editor.status}</div>}
      {editor.sourceStale&&<div role="alert" class="notice error">Configuration source changed. Edits are preserved; discard closes this database. Reopen the database to use the current source.</div>}
      {(editor.fieldMessages||[]).length>0&&<div role="alert" class="notice error">{editor.fieldMessages.map((message,index)=><div key={index}><strong>{message.field}</strong><span>{message.text}</span></div>)}</div>}
      <form onSubmit={e=>{e.preventDefault();run('command',{control:'SaveButton'},true);}}>
        <div class="fields">{editor.fields.filter(field=>field.visible).map(field=><label key={field.control} class={field.kind==='boolean'?'check-field':'field'}>
          <span>{field.title||field.name}</span>
          {field.kind==='catalog_ref'?<select aria-label={field.name} value={draft.fields[field.control]}
            disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onChange={e=>changeField(field.control,e.currentTarget.value)}>
            {field.choices.map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}
          </select>:field.kind==='boolean'?<input aria-label={field.title||field.name} aria-describedby={field.name==='DeletionMark'?'deletion-mark-note':undefined} type="checkbox" checked={draft.fields[field.control]===true} disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onChange={e=>changeField(field.control,e.currentTarget.checked)}/>:
          <input aria-label={field.name} type={field.kind==='datetime'?'datetime-local':'text'} step={field.kind==='datetime'?'1':undefined}
            inputMode={field.kind==='number'?'decimal':undefined} value={draft.fields[field.control]??''}
            disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onInput={e=>changeField(field.control,e.currentTarget.value)}
            onBlur={e=>commitImportedField(field,e.currentTarget.value,e.relatedTarget)}/>}
          {field.kind==='number'&&<small>Exact decimal · decimal point “.”</small>}
        </label>)}</div>
        {editor.fields.some(field=>field.visible&&field.name==='DeletionMark')&&<p id="deletion-mark-note" class="section-note">Пометка удаления изменяется только после «Save changes». Запись и строки не удаляются физически.</p>}
        {editor.references.length>0&&<section class="references"><h3>References <span class="badge">Read-only</span></h3>
          {editor.references.map(ref=><div key={ref.name}><strong>{ref.name}</strong><span>{ref.presentation||'Empty reference'}</span></div>)}
          <p>These references are preserved: choices are unavailable, exceed 64 records, or the current value is not selectable. Native FormData is not supported.</p></section>}
        {(editor.sections||[]).length>0&&<section class="tabular-sections" aria-label="Tabular sections"><h3>Tabular sections</h3>
          {editor.sections.map(section=><section key={section.name} class="tabular-section" aria-label={section.title||section.name}>
            <div class="tabular-head"><div><h4>{section.title||section.name}</h4><span class="muted">{section.rowCount??section.rows.length} rows</span></div>
              {section.readOnly?<span class="badge">Read-only</span>:<button data-editor-action="add-row" type="button"
                aria-label={'Add row to '+(section.title||section.name)} disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale||!section.canAdd}
                onClick={()=>run('addRow',{section:section.name},true)}>+ Add row</button>}</div>
            {section.readOnly?<p class="section-readonly">Rows are preserved and cannot be edited here. {sectionReason(section.reason)}</p>:
              section.rows.length?<div class="table-scroll"><table class="section-rows"><thead><tr><th scope="col">#</th><th scope="col">{section.rows[0].field.name}</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead><tbody>
                {section.rows.map(row=><tr key={row.id}><td class="code">{row.number}</td><td>
                  <select aria-label={(section.title||section.name)+' row '+row.number+': '+row.field.name}
                    value={draft.rows[rowDraftKey(section.name,row.id)]??row.field.inputText}
                    disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale||row.field.readOnly}
                    onChange={e=>changeRow(section.name,row.id,e.currentTarget.value)}>
                    {!row.field.choices.some(choice=>choice.value===row.field.inputText)&&
                      <option value={row.field.inputText}>Unavailable reference · {row.field.inputText}</option>}
                    {row.field.choices.map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}
                  </select></td><td><button data-editor-action="delete-row" type="button"
                    aria-label={'Delete row '+row.number+' from '+(section.title||section.name)}
                    disabled={busy||client.uncertain||editor.editingLocked||editor.sourceStale}
                    onClick={()=>run('deleteRow',{section:section.name,row:row.id},true)}>Delete</button></td></tr>)}
              </tbody></table></div>:<p class="section-empty">No rows. Add a row to select a reference.</p>}
          </section>)}
          <p class="section-note">Row editing is limited to records with at most 32 total rows. Changes are saved with the record.</p>
        </section>}
        <div class="editor-actions"><button data-editor-action="discard" type="button" disabled={busy||client.uncertain||editor.editingLocked} onClick={()=>run('command',{control:'CancelButton'})}>Discard &amp; return</button>
          <button data-editor-action="save" type="submit" class="primary" disabled={busy||client.uncertain||(editor.sourceStale&&!editor.editingLocked)}>{busy?'Working…':editor.editingLocked?'Resolve save outcome':'Save changes'}</button></div>
      </form>
    </section>}
    </div>}
    <footer class="app-footer">Runtime-owned form state · exact typed values · changes stay on this computer</footer>
  </main>;
}
render(<App/>,document.getElementById('app'));
