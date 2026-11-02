import {h,render,Fragment} from 'preact';
import {useEffect,useRef,useState} from 'preact/hooks';
import {EditorClient,typedInput,readBoundedJSON,takeSessionCapability} from './client.mjs';

let token=takeSessionCapability(location,history);
// The capability is memory-only: no cookies/localStorage or persisted credentials.
// Reopen the launch URL after a page reload to reattach without replaying writes.
const transport=async request=>readBoundedJSON(await fetch('/rpc',{method:'POST',cache:'no-store',
  credentials:'omit',headers:{'Content-Type':'application/x-ndjson','X-Yadinassi-Session':token||''},
  body:JSON.stringify(request)+'\n'}));
const client=new EditorClient(transport);
const text=value=>value?.type==='String'?value.value:value?.type==='Boolean'?(value.value?'Yes':'No'):value?.value??'';
const initialDraft=snapshot=>Object.fromEntries((snapshot?.state?.editor?.fields||[]).map(field=>[field.control,field.inputText]));

function App(){
  const [snapshot,setSnapshot]=useState(null),[draft,setDraft]=useState({}),[busy,setBusy]=useState(false),
    [error,setError]=useState(''),[filter,setFilter]=useState('');
  const gate=useRef(false);
  const apply=(preserveDraft=false)=>{if(client.snapshot){setSnapshot(client.snapshot);if(!preserveDraft)setDraft(initialDraft(client.snapshot));}};
  const editor=snapshot?.state?.editor;
  const localDirty=editor?.fields.some(field=>draft[field.control]!==field.inputText);
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
    if(gate.current)return;
    gate.current=true;setBusy(true);setError('');
    let flushComplete=!flush;
    try{
      if(flush&&editor&&!editor.editingLocked){
        for(const field of editor.fields){
          if(draft[field.control]!==field.inputText)
            await client.event('change',{control:field.control,value:typedInput(field,draft[field.control])});
        }
      }
      flushComplete=true;
      await client.event(event,values);
      const current=client.snapshot?.state?.editor;
      if((event==='closeCard'||event==='close')&&current?.state==='open'&&current.dirty&&
          confirm('Discard unsaved changes?')){
        await client.event('command',{control:'CancelButton'});
        if(event==='close')await client.event('close');
      }
    }catch(e){setError(e.message);}
    finally{apply(!flushComplete&&client.snapshot?.state?.editor?.editorId===editor?.editorId);gate.current=false;setBusy(false);}
  }
  async function resync(){
    if(gate.current)return;gate.current=true;setBusy(true);
    try{await client.resync();setError('');}catch(e){setError(e.message);}finally{apply(client.snapshot?.state?.editor?.editorId===editor?.editorId);gate.current=false;setBusy(false);}
  }
  const state=snapshot?.state;
  return <main>
    <header><div><span class="brand">YADINASSI</span><h1>Catalog workspace</h1></div>
      <div class="header-actions"><span class="badge">Local SQLite</span>
      {snapshot&&state.kind!=='closed'&&<button class="quiet" disabled={busy||editor?.editingLocked} onClick={()=>run('close',{},true)}>Close database</button>}</div>
    </header>
    <p class="scope">Auto-generated scalar editor · references read-only · no imported 1C forms</p>
    {error&&<section role="alert" class="notice error"><strong>Action not completed</strong><span>{error}</span>
      {client.uncertain&&token&&<button disabled={busy} onClick={resync}>Resynchronize — do not repeat Save</button>}</section>}
    {!snapshot&&<section class="panel empty">{busy?'Opening database…':'Use the host launcher to select a supported SQLite file.'}</section>}
    {state?.kind==='closed'&&<section class="panel empty"><h2>Database closed</h2><p>No further changes can be made in this session.</p></section>}
    {snapshot&&state.kind!=='closed'&&!editor&&<div class="workspace">
      <aside class="panel"><h2>Catalogs</h2><input aria-label="Filter catalogs" placeholder="Find catalog…" value={filter} onInput={e=>setFilter(e.currentTarget.value)}/>
        <nav>{state.catalogs.filter(c=>c.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase())).map(c=><button key={c.id}
          disabled={busy} class={state.list?.catalog===c.id?'catalog selected':'catalog'} onClick={()=>run('selectCatalog',{catalog:c.id})}>{c.name}<span>›</span></button>)}</nav>
      </aside>
      <section class="panel records">{state.list?<><div class="section-head"><div><h2>{state.list.catalogName}</h2><span class="muted">{state.list.total} records</span></div>
        <button class="primary" disabled={busy||!snapshot.capabilities.canCreate} onClick={()=>run('create')}>＋ New record</button></div>
        <table><thead><tr><th>Code</th><th>Description</th><th></th></tr></thead><tbody>
          {state.list.rows.map(row=><tr key={row.reference.record}><td class="code">{text(row.code)}</td><td>{text(row.description)||<span class="muted">Untitled</span>}</td>
            <td><button disabled={busy} onClick={()=>run('openCard',{reference:row.reference})}>Open →</button></td></tr>)}</tbody></table>
        {!state.list.rows.length&&<div class="empty">No records on this page.</div>}
        <footer class="pagination"><button disabled={busy||state.list.offset===0} onClick={()=>run('page',{offset:Math.max(0,state.list.offset-state.list.limit),limit:state.list.limit})}>← Previous</button>
          <span>{Math.min(state.list.offset+1,state.list.total)}–{Math.min(state.list.offset+state.list.limit,state.list.total)} of {state.list.total}</span>
          <button disabled={busy||state.list.offset+state.list.limit>=state.list.total} onClick={()=>run('page',{offset:state.list.offset+state.list.limit,limit:state.list.limit})}>Next →</button></footer>
      </>:<div class="empty"><h2>Choose a catalog</h2><p>Open a record or create a new one. Changes are only persisted after Save.</p></div>}</section>
    </div>}
    {editor&&state.kind!=='closed'&&<section class="panel editor"><div class="section-head"><div><button class="quiet back" disabled={busy||editor.editingLocked} onClick={()=>run('closeCard',{},true)}>← Back to records</button>
      <h2>{editor.isNew?'New record':'Edit record'} <span class="muted">/ {editor.catalogName}</span></h2></div>
      <span class={'badge '+((localDirty||editor.dirty)?'dirty':'saved')}>{editor.editingLocked?'Outcome pending':localDirty||editor.dirty?'Unsaved changes':editor.saveState==='saved'?'Saved':'No unsaved changes'}</span></div>
      {editor.status&&<div role="status" class={'notice '+(editor.error?'error':'success')}>{editor.status}</div>}
      <form onSubmit={e=>{e.preventDefault();run('command',{control:'SaveButton'},true);}}>
        <div class="fields">{editor.fields.filter(field=>field.visible).map(field=><label key={field.control} class={field.kind==='boolean'?'check-field':'field'}>
          <span>{field.title||field.name}</span>
          {field.kind==='boolean'?<input type="checkbox" checked={draft[field.control]===true} disabled={busy||client.uncertain||editor.editingLocked||!field.enabled||field.readOnly}
            onChange={e=>setDraft({...draft,[field.control]:e.currentTarget.checked})}/>:
          <input aria-label={field.name} type={field.kind==='datetime'?'datetime-local':'text'} step={field.kind==='datetime'?'1':undefined}
            inputMode={field.kind==='number'?'decimal':undefined} value={draft[field.control]??''}
            disabled={busy||client.uncertain||editor.editingLocked||!field.enabled||field.readOnly}
            onInput={e=>setDraft({...draft,[field.control]:e.currentTarget.value})}/>}
          {field.kind==='number'&&<small>Exact decimal · decimal point “.”</small>}
        </label>)}</div>
        {editor.references.length>0&&<section class="references"><h3>References <span class="badge">Read-only</span></h3>
          {editor.references.map(ref=><div key={ref.name}><strong>{ref.name}</strong><span>{ref.presentation||'Empty reference'}</span></div>)}
          <p>Existing typed references are preserved. Reference editing and native FormData are not supported yet.</p></section>}
        <div class="editor-actions"><button type="button" disabled={busy||editor.editingLocked} onClick={()=>run('command',{control:'CancelButton'})}>Discard &amp; return</button>
          <button type="submit" class="primary" disabled={busy}>{busy?'Working…':editor.editingLocked?'Resolve save outcome':'Save changes'}</button></div>
      </form>
    </section>}
    <footer class="app-footer">Runtime-owned form state · exact typed values · changes stay on this computer</footer>
  </main>;
}
render(<App/>,document.getElementById('app'));
