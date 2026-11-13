import {h,render,Fragment} from 'preact';
import {useEffect,useRef,useState} from 'preact/hooks';
import {EditorClient,typedInput,readBoundedJSON,takeSessionCapability,
  rowDraftKey,editorDraft,reconcileDraft,hasDraftChanges,flushDraft,orphanedDraft} from './client.mjs';
import {createBrowserHost, AttachmentRefusal} from '../../form/src/attachment.mjs';
import {readTheme,rememberTheme,resolvedTheme,workspacePreview,listCheckPresentation,isDeletionMarked,selectedReference,createSelectionModel} from './presentation.mjs';

export function mountEditor(environment,root,exchange=null){
if(!environment?.document||!root||exchange!==null&&typeof exchange!=='function')throw new TypeError('Invalid editor mount');
const window=environment,document=environment.document;
const themeTarget=exchange?root:document.documentElement;
const {location,history}=environment;
const fetch=(...args)=>environment.fetch(...args),matchMedia=(...args)=>environment.matchMedia(...args);
const addEventListener=(...args)=>environment.addEventListener(...args),removeEventListener=(...args)=>environment.removeEventListener(...args);
const confirm=(...args)=>environment.confirm(...args);
const browserHost=exchange?{enabled:false,content:root,launcher:null,notify(){}}:createBrowserHost(environment,root);
let disposed=false,readiness=false,leave=()=>false,pending=()=>true,recover=null,recoveryReady=()=>false,resolveReady,rejectReady;
const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
// Mark the rejection observed without changing the caller's ready promise.
ready.catch(()=>{});
const connected=value=>{readiness=true;resolveReady(value);return value;};
const failed=error=>{rejectReady(error);};
let token=browserHost.launcher;
// The capability is memory-only: never store it with the presentation preference.
// Reopen the launch URL after a page reload to reattach without replaying writes.
const underlyingTransport=exchange||(browserHost.enabled?browserHost.transport:async request=>readBoundedJSON(await fetch('/rpc',{method:'POST',cache:'no-store',
  credentials:'omit',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},
  body:JSON.stringify(request)+'\n'})));
const transport=request=>{if(disposed)throw new Error('Editor mount destroyed');return underlyingTransport(request);};
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
  const [recoveredDraft,setRecoveredDraft]=useState(null);
  const [recordQuery,setRecordQuery]=useState(''),[recordOrder,setRecordOrder]=useState('code');
  useEffect(()=>{setRecordQuery(snapshot?.state?.listQuery?.query||'');setRecordOrder(snapshot?.state?.listQuery?.order||'code');},
    [snapshot?.state?.list?.catalog,snapshot?.state?.listQuery?.query,snapshot?.state?.listQuery?.order]);
  const draftRef=useRef(draft),recoveryRef=useRef(null);draftRef.current=draft;recoveryRef.current=recoveredDraft;
  const picker=snapshot?.state?.referenceChoice;
  const pickerRef=useRef(null),[pickerQuery,setPickerQuery]=useState('');
  useEffect(()=>{const dialog=pickerRef.current;if(picker){if(dialog&&!dialog.open)dialog.showModal();}else if(dialog?.open)dialog.close();},[picker?.ticket]);
  useEffect(()=>{setPickerQuery(picker?.navigation.query||'');},[picker?.ticket,picker?.navigation.query]);
  const inputBlocked=busy||Boolean(recoveredDraft)||Boolean(picker);
  const [selection,setSelection]=useState({catalog:null,records:[]});
  const selectionModel=useRef(null);
  if(!selectionModel.current)selectionModel.current=createSelectionModel();
  const gate=useRef(false),actionPointer=useRef(false),lifecycle=useRef({pending:false,unknown:false});
  const apply=(preserveDraft=false,acceptedControl)=>{if(client.snapshot){setSnapshot(client.snapshot);setSelection(selectionModel.current.reconcile(client.snapshot));setPreview(previous=>workspacePreview(previous,client.snapshot));
    setDraft(previous=>preserveDraft?reconcileDraft(client.snapshot.state.editor,previous,acceptedControl):editorDraft(client.snapshot.state.editor));}};
  const changeField=(control,value)=>setDraft(previous=>({...previous,fields:{...previous.fields,[control]:value}}));
  const changeRow=(section,row,value)=>setDraft(previous=>({...previous,rows:{...previous.rows,[rowDraftKey(section,row)]:value}}));
  useEffect(()=>{
    const system=matchMedia('(prefers-color-scheme: dark)');
    const paint=()=>{themeTarget.dataset.theme=resolvedTheme(theme,system.matches);
      themeTarget.dataset.themePreference=theme;};
    paint();system.addEventListener('change',paint);
    return()=>system.removeEventListener('change',paint);
  },[theme]);
  const changeTheme=value=>{setTheme(value);rememberTheme(window,value);};
  const editor=snapshot?.state?.editor;
  const localDirty=hasDraftChanges(editor,draft);
  pending=()=>gate.current||lifecycle.current.pending||Boolean(recoveryRef.current)||client.uncertain;
  leave=()=>!disposed&&readiness&&!gate.current&&!client.uncertain&&!client.snapshot?.state?.editor&&!client.snapshot?.state?.referenceChoice&&!recoveryRef.current&&!hasDraftChanges(client.snapshot?.state?.editor,draftRef.current)&&!lifecycle.current.pending;
  lifecycle.current={pending:Boolean(recoveredDraft)||localDirty||editor?.dirty||editor?.editingLocked||busy||client.uncertain,unknown:client.uncertain||Boolean(editor?.editingLocked)};
  useEffect(()=>{
    const connect=()=>{
      if(disposed)return Promise.reject(new Error('Editor mount destroyed'));
      if(gate.current)throw new AttachmentRefusal('busy');
      if(browserHost.enabled&&client.uncertain)throw Error('Unknown previous outcome');
      gate.current=true;setBusy(true);setError('');
      const originalEditor=client.snapshot?.state?.editor,previousEditor=originalEditor?.editorId,originalDraft=draftRef.current;
      const sync=()=>{
        if(browserHost.enabled){const orphaned=orphanedDraft(originalEditor,client.snapshot?.state?.editor,originalDraft);
          if(orphaned){recoveryRef.current=orphaned;setRecoveredDraft(orphaned);}}
        apply(Boolean(previousEditor)&&previousEditor===client.snapshot?.state?.editor?.editorId);
      };
      return client.hello().then(sync).catch(e=>{sync();setError(e.message);if(browserHost.enabled||exchange)throw e;}).finally(()=>{gate.current=false;setBusy(false);});
    };
    const reattach=()=>{
      const incoming=takeSessionCapability(location,history);
      if(incoming){token=incoming;connect();}
    };
    if(browserHost.enabled){
      browserHost.setPending(()=>lifecycle.current.pending,()=>lifecycle.current.unknown);
      browserHost.start(connect).then(connected,failed);return()=>browserHost.attachment.dispose();
    }
    if(exchange){connect().then(connected,failed);return;}
    addEventListener('hashchange',reattach);
    if(token)connect().then(connected,failed);
    else {const message='Session capability missing. Reopen the URL printed by the launcher to reconnect.';setError(message);failed(new Error(message));}
    return()=>removeEventListener('hashchange',reattach);
  },[]);
  useEffect(()=>{browserHost.notify();},[localDirty,busy,snapshot,error,recoveredDraft]);
  useEffect(()=>{
    const warn=event=>{if(recoveredDraft||localDirty||editor?.dirty||editor?.editingLocked||busy||client.uncertain){event.preventDefault();event.returnValue='';}};
    addEventListener('beforeunload',warn);return()=>removeEventListener('beforeunload',warn);
  },[localDirty,editor?.dirty,editor?.editingLocked,busy,recoveredDraft]);
  async function run(event,values={},flush=false){
    if(client.snapshot?.state?.referenceChoice&&event!=='referenceChoice')return;
    if(gate.current||recoveryRef.current||client.uncertain||browserHost.enabled&&!browserHost.attachment.writable)return;
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
  recover=()=>resync();
  recoveryReady=()=>!gate.current&&!client.uncertain&&!client.snapshot?.state?.editor?.editingLocked;
  const requestResync=()=>exchange?.recover?exchange.recover():resync();
  async function resync(){
    if(gate.current)return;gate.current=true;setBusy(true);
    const previous=client.snapshot?.state?.editor,raw=draftRef.current;
    try{await client.resync();setError('');}catch(e){setError(e.message);}finally{
      const current=client.snapshot?.state?.editor;
      const orphan=orphanedDraft(previous,current,raw);
      if(orphan){recoveryRef.current=orphan;setRecoveredDraft(orphan);}
      // Do not restore an unchanged pre-Apply value over a confirmed choice.
      // Preserve genuinely local edits and expose detached drafts for copying.
      apply(current?.editorId===previous?.editorId&&hasDraftChanges(previous,raw));
      gate.current=false;setBusy(false);
    }
  }
  const state=snapshot?.state;
  const listCheck=listCheckPresentation(snapshot);
  const navigationLocked=inputBlocked||client.uncertain||Boolean(editor);
  const catalogs=editor?preview.catalogs:state?.catalogs||[];
  const list=editor?preview.list:state?.list;
  const selected=selectedReference(selection,list);
  const liveList=()=>!gate.current&&!client.uncertain&&client.snapshot?.state?.kind==='list'&&!client.snapshot.state.editor?client.snapshot.state.list:null;
  const choose=(row,multiple=false)=>{
    const current=liveList();if(!current)return;
    setSelection(selectionModel.current.select(current,row.reference,multiple));
  };
  const openSelected=()=>{
    const current=liveList();if(!current)return;
    const target=selectionModel.current.target(current);
    if(target)run('openCard',{reference:target});
  };
  const checkSelected=(empty=false)=>{
    const current=liveList();if(!current||!listCheckPresentation(client.snapshot).available)return;
    if(empty){if(selectionModel.current.empty(current))run('checkCard',{reference:null});return;}
    const target=selectionModel.current.target(current);
    if(target)run('checkCard',{reference:target});
  };
  const rowKey=(event,row)=>{
    if(event.target!==event.currentTarget||navigationLocked)return;
    if(event.key===' '){event.preventDefault();choose(row,event.ctrlKey||event.metaKey);}
    else if(event.key==='Enter'){event.preventDefault();if(selectionModel.current.target(liveList())?.record===row.reference.record)openSelected();}
    else if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();const sibling=event.key==='ArrowDown'?event.currentTarget.nextElementSibling:event.currentTarget.previousElementSibling;
      sibling?.focus();
    }
  };
  const visibleCatalogs=catalogs.filter(c=>c.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return <main onPointerDownCapture={e=>{actionPointer.current=Boolean(e.target.closest?.('[data-editor-action]'));}}
    onPointerUpCapture={()=>{actionPointer.current=false;}} onPointerCancelCapture={()=>{actionPointer.current=false;}}>
    <header><div><span class="brand">YADINASSI</span><h1>Catalog workspace</h1></div>
      <div class="header-actions"><span class="badge connection">Local SQLite</span>
      <label class="theme-control"><span>Theme</span><select aria-label="Color theme" value={theme}
        onChange={e=>changeTheme(e.currentTarget.value)}><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label>
      {snapshot&&state.kind!=='closed'&&<button data-editor-action="close" class="quiet" disabled={inputBlocked||client.uncertain||editor?.editingLocked} onClick={()=>run('close',{},true)}>Close database</button>}</div>
    </header>
    <p class="scope">{editor?.originalForm?'Imported name-validation handlers · local host form adapter · no native parity claim':'Auto-generated editor · bounded references and tabular rows · no imported 1C forms'}</p>
    {recoveredDraft&&<section class="notice warning" role="status"><strong>Unsubmitted input from an earlier editor</strong>
      <p>These inputs were not applied to the current record. Copy anything you need before dismissing them.</p>
      {Object.entries(recoveredDraft.fields).concat(Object.entries(recoveredDraft.rows)).map(([name,value])=><p>{name}: {String(value)}</p>)}
      <button disabled={busy} onClick={()=>{recoveryRef.current=null;setRecoveredDraft(null);}}>Dismiss recovered inputs</button></section>}
    {error&&<section role="alert" class="notice error"><strong>Action not completed</strong><span>{error}</span>
      {client.uncertain&&token&&<button disabled={busy} onClick={requestResync}>Resynchronize — do not repeat Save</button>}</section>}
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
        <div class="list-toolbar" role="toolbar" aria-label="Record commands">
          <button disabled={navigationLocked||!selected} onClick={openSelected}>Open selected</button>
          {listCheck.available&&<><button disabled={navigationLocked||!selected} onClick={()=>checkSelected()}>Проверить карточку</button>
          <button disabled={navigationLocked||selection.records.length!==0} onClick={()=>checkSelected(true)}>Проверить без выбора</button></>}
          <span class="selection-count" aria-label="Selected record count" aria-live="polite">{selection.records.length} selected</span>
        </div>
        <div class="list-toolbar" role="search" aria-label="Search records">
          <input type="search" aria-label="Search records" maxLength={128} disabled={navigationLocked} value={recordQuery} onInput={event=>setRecordQuery(event.currentTarget.value)}/>
          <select aria-label="Record order" disabled={navigationLocked} value={recordOrder} onChange={event=>setRecordOrder(event.currentTarget.value)}><option value="code">Code</option><option value="description">Description</option></select>
          <button disabled={navigationLocked} onClick={()=>run('filterRecords',{query:recordQuery,order:recordOrder})}>Search records</button>
          <button disabled={navigationLocked} onClick={()=>run('refreshRecords')}>Refresh records</button>
        </div>
        {snapshot?.state?.listQuery?.notice&&<p role="status">{snapshot.state.listQuery.notice}</p>}
        {editor&&<p class="preview-note">Last confirmed records · updated after Save</p>}
        {listCheck.messages.length>0&&<div role="status" class="notice" aria-label="Результат проверки карточки">
          {listCheck.messages.map((message,index)=><div key={index}>{message.field&&<strong>{message.field}: </strong>}<span>{message.text}</span></div>)}
        </div>}
        <div class="table-scroll"><table class="record-list"><thead><tr><th class="selection-column"><span class="sr-only">Selection</span></th><th>Code</th><th>Description</th></tr></thead><tbody>
          {list.rows.map(row=><tr key={row.reference.record} tabIndex={navigationLocked?-1:0} aria-selected={selection.records.includes(row.reference.record.toLowerCase())}
            onClick={event=>{if(!event.target.closest('input'))choose(row,event.ctrlKey||event.metaKey);}} onKeyDown={event=>rowKey(event,row)}
            class={selection.records.includes(row.reference.record.toLowerCase())?'selected-record':editor?.reference?.record===row.reference.record?'current-record':undefined}>
            <td class="selection-column"><input type="checkbox" aria-label={'Select record '+text(row.code)} checked={selection.records.includes(row.reference.record.toLowerCase())}
              disabled={navigationLocked} onChange={()=>choose(row,true)}/></td>
            <td class="code">{text(row.code)}</td><td>{text(row.description)||<span class="muted">Untitled</span>}{isDeletionMarked(row)&&<span class="badge deletion-mark">Помечен на удаление</span>}</td>
          </tr>)}</tbody></table></div>
        {!list.rows.length&&<div class="empty">No records on this page.</div>}
        <footer class="pagination"><button disabled={navigationLocked||list.offset===0} onClick={()=>run('page',{offset:Math.max(0,list.offset-list.limit),limit:list.limit})}>← Previous</button>
          <span>{Math.min(list.offset+1,list.total)}–{Math.min(list.offset+list.limit,list.total)} of {list.total}</span>
          <button disabled={navigationLocked||list.offset+list.limit>=list.total} onClick={()=>run('page',{offset:list.offset+list.limit,limit:list.limit})}>Next →</button></footer>
      </>:<div class="empty"><h2>{editor?editor.catalogName:'Choose a catalog'}</h2><p>{editor?'List unavailable. Resolve the save outcome or return to records.':'Open a record or create a new one. Changes are only persisted after Save.'}</p></div>}</section>
    {editor&&<section class="panel editor" aria-label="Record editor"><div class="section-head"><div><button data-editor-action="back" class="quiet back" disabled={inputBlocked||client.uncertain||editor.editingLocked} onClick={()=>run('closeCard',{},true)}>← Back to records</button>
      <h2>{editor.isNew?'New record':'Edit record'} <span class="muted">/ {editor.catalogName}</span></h2></div>
      <span class={'badge '+((localDirty||editor.dirty)?'dirty':'saved')}>{editor.editingLocked?'Outcome pending':localDirty||editor.dirty?'Unsaved changes':editor.saveState==='saved'?'Saved':'No unsaved changes'}</span></div>
      {editor.status&&(!localDirty||editor.error)&&<div role="status" class={'notice '+(editor.error?'error':'success')}>{editor.status}</div>}
      {editor.sourceStale&&<div role="alert" class="notice error">Configuration source changed. Edits are preserved; discard closes this database. Reopen the database to use the current source.</div>}
      {(editor.fieldMessages||[]).length>0&&<div role="alert" class="notice error">{editor.fieldMessages.map((message,index)=><div key={index}><strong>{message.field}</strong><span>{message.text}</span></div>)}</div>}
      <form onSubmit={e=>{e.preventDefault();run('command',{control:'SaveButton'},true);}}>
        <div class="fields">{editor.fields.filter(field=>field.visible).map(field=><label key={field.control} class={field.kind==='boolean'?'check-field':'field'}>
          <span>{field.title||field.name}</span>
          {field.kind==='catalog_ref'?<select aria-label={field.name} value={draft.fields[field.control]}
            disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onChange={e=>changeField(field.control,e.currentTarget.value)}>
            {field.choices.map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}
          </select>:field.kind==='boolean'?<input aria-label={field.title||field.name} aria-describedby={field.name==='DeletionMark'?'deletion-mark-note':undefined} type="checkbox" checked={draft.fields[field.control]===true} disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onChange={e=>changeField(field.control,e.currentTarget.checked)}/>:
          <input aria-label={field.name} type={field.kind==='datetime'?'datetime-local':'text'} step={field.kind==='datetime'?'1':undefined}
            inputMode={field.kind==='number'?'decimal':undefined} value={draft.fields[field.control]??''}
            disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||!field.enabled||field.readOnly}
            onInput={e=>changeField(field.control,e.currentTarget.value)}
            onBlur={e=>commitImportedField(field,e.currentTarget.value,e.relatedTarget)}/>}
          {field.lazyChoice&&<button data-editor-action="reference-choice" type="button" aria-label={'Choose '+field.name}
            disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||field.readOnly||!field.enabled}
            onClick={()=>run('referenceChoice',{action:{action:'begin',control:field.control,section:null,row:null}},true)}>Choose reference</button>}
          {field.kind==='number'&&<small>Exact decimal · decimal point “.”</small>}
        </label>)}</div>
        {editor.fields.some(field=>field.visible&&field.name==='DeletionMark')&&<p id="deletion-mark-note" class="section-note">Пометка удаления изменяется только после «Save changes». Запись и строки не удаляются физически.</p>}
        {editor.references.length>0&&<section class="references"><h3>References <span class="badge">Read-only</span></h3>
          {editor.references.map(ref=><div key={ref.name}><strong>{ref.name}</strong><span>{ref.presentation||'Empty reference'}</span></div>)}
          <p>These references are preserved: choices are unavailable or the current value is not selectable. Native FormData is not supported.</p></section>}
        {(editor.sections||[]).length>0&&<section class="tabular-sections" aria-label="Tabular sections"><h3>Tabular sections</h3>
          {editor.sections.map(section=><section key={section.name} class="tabular-section" aria-label={section.title||section.name}>
            <div class="tabular-head"><div><h4>{section.title||section.name}</h4><span class="muted">{section.rowCount??section.rows.length} rows</span></div>
              {section.readOnly?<span class="badge">Read-only</span>:<button data-editor-action="add-row" type="button"
                aria-label={'Add row to '+(section.title||section.name)} disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||!section.canAdd}
                onClick={()=>run('addRow',{section:section.name},true)}>+ Add row</button>}</div>
            {section.readOnly?<p class="section-readonly">Rows are preserved and cannot be edited here. {sectionReason(section.reason)}</p>:
              section.rows.length?<div class="table-scroll"><table class="section-rows"><thead><tr><th scope="col">#</th><th scope="col">{section.rows[0].field.name}</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead><tbody>
                {section.rows.map(row=><tr key={row.id}><td class="code">{row.number}</td><td>
                  <select aria-label={(section.title||section.name)+' row '+row.number+': '+row.field.name}
                    value={draft.rows[rowDraftKey(section.name,row.id)]??row.field.inputText}
                    disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||row.field.readOnly}
                    onChange={e=>changeRow(section.name,row.id,e.currentTarget.value)}>
                    {!row.field.choices.some(choice=>choice.value===row.field.inputText)&&
                      <option value={row.field.inputText}>Unavailable reference · {row.field.inputText}</option>}
                    {row.field.choices.map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}
                  </select>{row.field.lazyChoice&&<button data-editor-action="reference-choice" type="button"
                    aria-label={'Choose '+(section.title||section.name)+' row '+row.number}
                    disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale||row.field.readOnly}
                    onClick={()=>run('referenceChoice',{action:{action:'begin',control:null,section:section.name,row:row.id}},true)}>Choose reference</button>}</td><td><button data-editor-action="delete-row" type="button"
                    aria-label={'Delete row '+row.number+' from '+(section.title||section.name)}
                    disabled={inputBlocked||client.uncertain||editor.editingLocked||editor.sourceStale}
                    onClick={()=>run('deleteRow',{section:section.name,row:row.id},true)}>Delete</button></td></tr>)}
              </tbody></table></div>:<p class="section-empty">No rows. Add a row to select a reference.</p>}
          </section>)}
          <p class="section-note">Row editing is limited to records with at most 32 total rows. Changes are saved with the record.</p>
        </section>}
        <div class="editor-actions"><button data-editor-action="discard" type="button" disabled={inputBlocked||client.uncertain||editor.editingLocked} onClick={()=>run('command',{control:'CancelButton'})}>Discard &amp; return</button>
          <button data-editor-action="save" type="submit" class="primary" disabled={inputBlocked||client.uncertain||(editor.sourceStale&&!editor.editingLocked)}>{busy?'Working…':editor.editingLocked?'Resolve save outcome':'Save changes'}</button></div>
      </form>
    </section>}
    </div>}
    <dialog ref={pickerRef} aria-label="Choose reference" onCancel={event=>{event.preventDefault();if(picker&&!busy)run('referenceChoice',{action:{action:'cancel',ticket:picker.ticket}});}}>
      {picker&&<section class="reference-picker">
        <h2>Choose reference</h2>
        {error&&<p role="alert">{error}</p>}
        {client.uncertain&&<><p role="status">Outcome unknown. Read current state before choosing again; the previous action will not be repeated.</p>
          <button disabled={busy} onClick={requestResync}>Resynchronize choice</button></>}
        <label>Search references<input aria-label="Search references" type="search" maxLength={128} value={pickerQuery} disabled={busy||client.uncertain} onInput={event=>setPickerQuery(event.currentTarget.value)}/></label>
        <button disabled={busy||client.uncertain} onClick={()=>run('referenceChoice',{action:{action:'search',ticket:picker.ticket,query:pickerQuery}})}>Search references</button>
        <button disabled={busy||client.uncertain} onClick={()=>run('referenceChoice',{action:{action:'refresh',ticket:picker.ticket}})}>Refresh choices</button>
        <p role="status">Page {picker.navigation.page} of {picker.navigation.pages}; {picker.navigation.total} matching records</p>
        <div class="reference-picker-rows">{picker.rows.map(row=><button key={row.choice} disabled={busy||client.uncertain} onClick={()=>run('referenceChoice',{action:{action:'apply',ticket:picker.ticket,choice:row.choice}})}>{row.code} · {row.description}</button>)}</div>
        {!picker.rows.length&&<p>No matching references.</p>}
        <button disabled={busy||client.uncertain||!picker.navigation.previous} onClick={()=>run('referenceChoice',{action:{action:'page',ticket:picker.ticket,cursor:picker.navigation.previous}})}>Previous choices</button>
        <button disabled={busy||client.uncertain||!picker.navigation.next} onClick={()=>run('referenceChoice',{action:{action:'page',ticket:picker.ticket,cursor:picker.navigation.next}})}>Next choices</button>
        <button disabled={busy||client.uncertain} onClick={()=>run('referenceChoice',{action:{action:'clear',ticket:picker.ticket}})}>Empty reference</button>
        <button disabled={busy||client.uncertain} onClick={()=>run('referenceChoice',{action:{action:'cancel',ticket:picker.ticket}})}>Cancel choice</button>
      </section>}
    </dialog>
    <footer class="app-footer">Runtime-owned form state · exact typed values · changes stay on this computer</footer>
  </main>;
}
render(<App/>,browserHost.content);
return {ready,client,recoveryReady:()=>recoveryReady(),pending:()=>pending(),canLeave:()=>leave(),resume(){if(disposed||!recover)throw new Error('Editor mount unavailable');return recover();},destroy(){
  if(disposed)return;disposed=true;
  rejectReady(new Error('Editor mount destroyed'));
  render(null,browserHost.content);
}};
}
if(typeof window!=='undefined'&&window.document?.getElementById('app'))mountEditor(window,window.document.getElementById('app'));
