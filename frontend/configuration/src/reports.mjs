/** Read-only stock projections. A label is never a reference or write capability. */
import {FormError, validateScalar, readOnlyScalarText} from '../../form/src/client.mjs';
const keys = (v,names) => v !== null && typeof v === 'object' && !Array.isArray(v) &&
  Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v,n));
const text = (v,n=1152) => typeof v === 'string' && v.length <= n*2 && [...v].length <= n &&
  !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v);
const views = ['Movements','Balance','Turnovers','BalanceAndTurnovers'];
const statement = value => value?.view==='BalanceAndTurnovers';
const ticket = (v,prefix) => typeof v==='string' && new RegExp('^'+prefix+'-[0-9a-f]{32}-[1-9][0-9]{0,15}$').test(v);
const rowToken = value => typeof value==='string' && /^[0-9a-f]{32}$/.test(value);
const safe = state => state?.kind!=='closed' && !state?.choice && !state?.uncertain && !state?.posting?.some(p=>['uncertain','committed'].includes(p.state));
const date = value => {
  if (!text(value,19) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value)) return false;
  const [year,month,day,hour,minute,second]=value.match(/\d+/g).map(Number);
  const leap=year%4===0 && (year%100!==0 || year%400===0);
  return year>=1 && month>=1 && month<=12 && day>=1 && day<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1] && hour<24 && minute<60 && second<60;
};
function filterValues(values,declared) {
  return Array.isArray(values) && values.length===declared.filters.length && values.every((v,i)=>
    keys(v,['id','mode','text']) && v.id===declared.filters[i].id && ['all','empty','selected'].includes(v.mode) && text(v.text) &&
    (v.mode!=='all' || v.text==='') && (v.mode!=='empty' || v.text==='(empty reference)'));
}
function setupValid(setup,reports) {
  const declared=reports.find(r=>r.id===setup?.report);
  if(!keys(setup,['report','ticket','filters','choice']) || !statement(declared) || !ticket(setup.ticket,'setup') || !filterValues(setup.filters,declared))return false;
  const choice=setup.choice;if(choice===null)return true;
  if(!keys(choice,['filter','ticket','code','rows','error']) || !declared.filters.some(f=>f.id===choice.filter) || !ticket(choice.ticket,'choice') || !text(choice.code,64) ||
     ![null,'too_many_matches'].includes(choice.error) || !Array.isArray(choice.rows) || choice.rows.length>32 || choice.error!==null && choice.rows.length)return false;
  const seen=new Set();return choice.rows.every(row=>{
    if(!keys(row,['choice','code','description']) || !rowToken(row.choice) || seen.has(row.choice) || !text(row.code,64) || !text(row.description,1024))return false;
    seen.add(row.choice);return true;
  });
}
export function validReportRequest(params,state) {
  const declared=state?.reports?.find(r=>r.id===params?.report), extra=statement(declared)?['periodicity','setup']:[];
  if (!keys(params,['report','at','start','end',...extra]) || !declared || !safe(state)) return false;
  const bounds=declared.view==='Movements' ? params.at===null && params.start===null && params.end===null
    : declared.view==='Balance' ? date(params.at) && params.start===null && params.end===null
    : params.at===null && date(params.start) && date(params.end) && params.start<=params.end;
  return bounds && (!statement(declared) || declared.periodicities.includes(params.periodicity) &&
    params.start>='1900-01-01T00:00:00' && params.end<='2099-12-31T23:59:59' &&
    state.reportSetup?.report===params.report && state.reportSetup.ticket===params.setup && !state.reportSetup.choice);
}
export function validReportAction(method,params,state) {
  if(!safe(state))return false;
  if(method==='application.reportPage'){
    const page=state?.report?.page;
    return keys(params,['snapshot','cursor']) && !!page && page.snapshot===params.snapshot && [page.cursor,page.previous,page.next].includes(params.cursor) && params.cursor!==null;
  }
  if(method!=='application.reportSetup')return false;
  const declared=state?.reports?.find(r=>r.id===params?.report);if(!statement(declared))return false;
  if(params.action==='open')return keys(params,['report','action']);
  const setup=state.reportSetup;
  if(!setup || setup.report!==params.report || setup.ticket!==params.ticket)return false;
  const base=['report','ticket','action'];
  if(['begin','clear','empty'].includes(params.action))return keys(params,[...base,'filter']) && setup.choice===null && declared.filters.some(f=>f.id===params.filter);
  if(!setup.choice || setup.choice.ticket!==params.choice)return false;
  if(params.action==='filter')return keys(params,[...base,'choice','code']) && text(params.code,64);
  if(params.action==='cancel')return keys(params,[...base,'choice']);
  return params.action==='apply' && keys(params,[...base,'choice','value']) && setup.choice.error===null && setup.choice.rows.some(r=>r.choice===params.value);
}
function pageValid(page,rows) {
  if(!keys(page,['snapshot','cursor','previous','next','offset','total']) || !/^report-[A-Za-z0-9_-]{32}-[1-9][0-9]{0,15}$/.test(page.snapshot) ||
     !Number.isSafeInteger(page.offset) || !Number.isSafeInteger(page.total) || page.offset<0 || page.offset>page.total || page.total>1000 || rows.length>50 ||
     page.offset+rows.length>page.total || page.total>0 && !rows.length || (page.previous===null)!==(page.offset===0) || (page.next===null)!==(page.offset+rows.length===page.total))return false;
  const cursors=[page.cursor,...[page.previous,page.next].filter(v=>v!==null)];
  return cursors.every(v=>typeof v==='string' && /^page-[A-Za-z0-9_-]{32}$/.test(v)) && new Set(cursors).size===cursors.length;
}
export function validateReports(state,previous) {
  const enabled=Object.hasOwn(state,'reports');
  if (enabled !== Object.hasOwn(state,'report') || previous && enabled!==Object.hasOwn(previous,'reports')) throw new FormError('transport');
  if (!enabled) { if(Object.hasOwn(state,'reportSetup'))throw new FormError('transport'); return; }
  if (!Array.isArray(state.reports) || state.reports.length>96 || previous && JSON.stringify(state.reports)!==JSON.stringify(previous.reports)) throw new FormError('transport');
  const seen=new Set();
  for (const report of state.reports) {
    if (!keys(report,['id','title','view',...(statement(report)?['periodicities','filters']:[])]) || !text(report.id,128) || !/^[\p{ID_Start}_][\p{ID_Continue}]*$/u.test(report.id) ||
        seen.has(report.id) || !text(report.title,256) || !views.includes(report.view)) throw new FormError('transport');
    if(statement(report)){
      if(!Array.isArray(report.periodicities) || !report.periodicities.length || report.periodicities.length>3 || new Set(report.periodicities).size!==report.periodicities.length ||
         report.periodicities.some(p=>!['None','Day','Month'].includes(p)) || !Array.isArray(report.filters) || report.filters.length>16 || new Set(report.filters.map(f=>f?.id)).size!==report.filters.length ||
         report.filters.some(f=>!keys(f,['id','title']) || !text(f.id,128) || !/^[\p{ID_Start}_][\p{ID_Continue}]*$/u.test(f.id) || !text(f.title,128)))throw new FormError('transport');
    }
    seen.add(report.id);
  }
  if(Object.hasOwn(state,'reportSetup')!==state.reports.some(statement) || state.reportSetup!==undefined && state.reportSetup!==null && !setupValid(state.reportSetup,state.reports))throw new FormError('transport');
  if (state.report===null) return;
  const result=state.report, declared=state.reports.find(r=>r.id===result?.report), extra=statement(declared)?['periodicity','setup','filters','page']:[];
  const request={report:result.report,at:result.at,start:result.start,end:result.end,...(statement(declared)?{periodicity:result.periodicity,setup:result.setup}:{})};
  if (!keys(result,['report','view','at','start','end','columns','rows',...extra]) || !declared || declared.view!==result.view ||
      !validReportRequest(request,{...state,choice:null,posting:[],uncertain:false}) ||
      !Array.isArray(result.columns) || !result.columns.length || result.columns.length>32 ||
      !Array.isArray(result.rows) || result.rows.length>1000 || result.rows.length*result.columns.length>25000 ||
      statement(declared) && (!filterValues(result.filters,declared) || !pageValid(result.page,result.rows) ||
        result.filters.some((f,i)=>f.id!==state.reportSetup.filters[i].id || f.mode!==state.reportSetup.filters[i].mode))) throw new FormError('transport');
  for (const column of result.columns) {
    if (!keys(column,['name','type']) || !text(column.name,128) ||
        !['String','Number','Boolean','Date','Catalog','Document'].includes(column.type)) throw new FormError('transport');
  }
  for (const row of result.rows) {
    if (!Array.isArray(row) || row.length!==result.columns.length) throw new FormError('transport');
    row.forEach((cell,index)=>{
      if (cell?.type!==result.columns[index].type) throw new FormError('transport');
      if (['Catalog','Document'].includes(cell.type)) {
        if (!keys(cell,['type','text']) || !text(cell.text)) throw new FormError('transport');
      } else validateScalar(cell);
    });
  }
}
export function validateReportReply(result,request,previous) {
  if(result.error!==null)return;
  const state=result.state;
  if(request.method==='application.report'){
    if(!state.report || Object.keys(request.params).some(k=>state.report[k]!==request.params[k]))throw new FormError('transport');
    if(statement(state.report) && state.report.page.offset!==0)throw new FormError('transport');
  }
  if(request.method==='application.reportPage'){
    const prior=previous?.report,next=state.report;
    const header=value=>Object.fromEntries(Object.entries(value).filter(([k])=>!['page','rows'].includes(k)));
    if(!prior?.page || !next?.page || next.page.snapshot!==request.params.snapshot || next.page.cursor!==request.params.cursor ||
       next.page.total!==prior.page.total || JSON.stringify(header(prior))!==JSON.stringify(header(next)))throw new FormError('transport');
  }
  if(request.method==='application.reportSetup'){
    const next=state.reportSetup,old=previous?.reportSetup,action=request.params.action;
    if(!next || next.report!==request.params.report || state.report!==null)throw new FormError('transport');
    if(action!=='open'){
      if(!old || old.ticket!==request.params.ticket)throw new FormError('transport');
      const changed=['apply','empty','clear'].includes(action);
      if(changed===(next.ticket===old.ticket) || !changed && JSON.stringify(next.filters)!==JSON.stringify(old.filters))throw new FormError('transport');
      if(['begin','filter'].includes(action)){
        if(!next.choice || next.choice.filter!==(action==='begin'?request.params.filter:old.choice?.filter) || next.choice.ticket===old.choice?.ticket)throw new FormError('transport');
      }else if(next.choice!==null)throw new FormError('transport');
    }
  }
}
export function reportCellText(cell) {
  return ['Catalog','Document'].includes(cell.type) ? cell.text : readOnlyScalarText(cell);
}
export function reportColumnTitle(column) {
  // Presentation only; the unchanged exact source name is displayed alongside.
  return column.name.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/([A-Z])([A-Z][a-z])/g, '$1 $2');
}
export function createReportPanel(document, host, request, blocked, command=null) {
  const el=(tag,content='')=>{const n=document.createElement(tag);n.textContent=content;return n;};
  const title=el('h2','Stock reports'), navigation=el('nav'), controls=el('div'), filters=el('section'), output=el('div'), notice=el('p');
  host.className='configuration-reports';host.dataset.formAction='application-navigation';host.setAttribute('aria-label','Saved stock reports');host.hidden=true;
  navigation.setAttribute('aria-label','Declared stock reports');notice.setAttribute('role','status');filters.setAttribute('aria-label','Statement catalog filters');
  const input=(labelText)=>{const label=el('label',labelText),field=el('input');field.type='datetime-local';field.step='1';field.setAttribute('aria-label',labelText);label.append(field);controls.append(label);return {label,field};};
  const at=input('Balance before moment (exclusive)'), start=input('From moment (inclusive)'), end=input('Through moment (inclusive)');
  const now=new Date(),pad=v=>String(v).padStart(2,'0');
  const today=`${String(now.getFullYear()).padStart(4,'0')}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
  at.field.value=today+'T23:59:59';start.field.value=today+'T00:00:00';end.field.value=today+'T23:59:59';
  const periodLabel=el('label','Statement periodicity'),period=el('select');period.setAttribute('aria-label','Statement periodicity');periodLabel.append(period);controls.append(periodLabel);
  const show=el('button','Show saved stock');show.type='button';show.addEventListener('pointerdown',event=>event.preventDefault());controls.append(show);
  host.append(title,el('p','Read-only saved database state. Unsaved form edits are not included. No movement or total can be edited here.'),navigation,controls,filters,notice,output);
  let state=null, selected=null, busy=false, localError='', lastResult=undefined, periodOwner=null, navigationGeneration=0;
  const invoke=(method,params)=>method==='application.report'?request(params):command ? command(method,params):Promise.reject(new FormError('unavailable'));
  const button=(parent,label,disabled,action)=>{const b=el('button',label);b.type='button';b.disabled=disabled;b.addEventListener('pointerdown',event=>event.preventDefault());b.addEventListener('click',()=>{if(!b.disabled)action();});parent.append(b);return b;};
  async function run(method,params) {
    if(busy || blocked() || !state)return;
    if(method==='application.report' ? !validReportRequest(params,state):!validReportAction(method,params,state))return;
    const generation=navigationGeneration;
    busy=true;localError='';paint();
    try{const result=await invoke(method,params);if(generation===navigationGeneration && result?.error)localError=result.error==='report_busy'?'Resolve the pending saved operation first.':'This report is unavailable or exceeds the bounded result limit.';}
    catch{if(generation===navigationGeneration)localError='Report request did not finish. It will not be repeated automatically.';}
    finally{busy=false;paint();}
  }
  function drawFilters(report,disabled) {
    filters.replaceChildren();filters.hidden=!statement(report);if(filters.hidden)return;
    const setup=state.reportSetup?.report===selected?state.reportSetup:null;
    if(!setup){
      filters.append(el('p','Prepare the statement filters before reading. All dimensions start unfiltered.'));
      button(filters,'Prepare statement',disabled,()=>run('application.reportSetup',{report:selected,action:'open'}));return;
    }
    const base={report:selected,ticket:setup.ticket};
    for(const filter of setup.filters){
      const line=el('div'),declared=report.filters.find(f=>f.id===filter.id);
      line.append(el('span',declared.title+': '+(filter.mode==='all'?'All saved values':filter.text)));
      button(line,'Choose '+declared.title,disabled || setup.choice!==null,()=>run('application.reportSetup',{...base,action:'begin',filter:filter.id}));
      button(line,'All '+declared.title,disabled || setup.choice!==null,()=>run('application.reportSetup',{...base,action:'clear',filter:filter.id}));
      button(line,'Empty '+declared.title,disabled || setup.choice!==null,()=>run('application.reportSetup',{...base,action:'empty',filter:filter.id}));
      filters.append(line);
    }
    const choice=setup.choice;if(!choice)return;
    const picker=el('section'),label=el('label','Exact code'),code=el('input');
    picker.setAttribute('aria-label','Statement filter choice');picker.append(el('h3','Choose '+choice.filter));
    code.type='text';code.maxLength=64;code.value=choice.code;code.setAttribute('aria-label','Statement exact code');code.disabled=disabled;label.append(code);picker.append(label);
    const captured={...base,choice:choice.ticket};
    const search=()=>{if(!text(code.value,64)){localError='Enter an exact code of at most 64 characters.';paint();return;}run('application.reportSetup',{...captured,action:'filter',code:code.value});};
    button(picker,'Find statement code',disabled,search);
    button(picker,'Cancel statement choice',disabled,()=>run('application.reportSetup',{...captured,action:'cancel'}));
    code.addEventListener('keydown',event=>{if(event.key==='Enter' && !event.isComposing){event.preventDefault();search();}});
    picker.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();run('application.reportSetup',{...captured,action:'cancel'});}});
    if(choice.error)picker.append(el('p','Too many matches. Enter an exact code; no partial choices are shown.'));
    for(const row of choice.rows)button(picker,row.description || row.code,disabled,()=>run('application.reportSetup',{...captured,action:'apply',value:row.choice}));
    if(!choice.error && !choice.rows.length)picker.append(el('p','No matching saved record.'));
    filters.append(picker);
  }
  function paint() {
    host.hidden=!state?.reports?.length;if(host.hidden)return;
    if(!state.reports.some(r=>r.id===selected))selected=state.reports[0].id;
    const disabled=busy || blocked(), report=state.reports.find(r=>r.id===selected);
    navigation.replaceChildren();
    for(const item of state.reports){const b=button(navigation,item.title,disabled,()=>{if(busy || blocked())return;selected=item.id;navigationGeneration++;localError='';paint();});b.setAttribute('aria-pressed',String(item.id===selected));}
    at.label.hidden=report.view!=='Balance';start.label.hidden=end.label.hidden=!['Turnovers','BalanceAndTurnovers'].includes(report.view);
    periodLabel.hidden=!statement(report);
    if(periodOwner!==report.id){period.replaceChildren();for(const name of report.periodicities || []){const option=el('option',name);option.value=name;period.append(option);}period.value=report.periodicities?.[0] || '';periodOwner=report.id;}
    for(const field of [at.field,start.field,end.field,period])field.disabled=disabled;
    const setup=state.reportSetup?.report===selected?state.reportSetup:null;
    show.disabled=disabled || statement(report) && (!setup || setup.choice!==null);
    notice.textContent=localError || (disabled?'Finish the current selection or uncertain operation before reading stock.':'');
    drawFilters(report,disabled);
    const result=state.report?.report===selected?state.report:null;
    // Button state changes with the queue even when the immutable page does not.
    if(result!==lastResult || result?.page){output.replaceChildren();lastResult=result;
      if(result){const table=el('table'),header=el('tr'),head=el('thead'),body=el('tbody');
        table.setAttribute('aria-label',report.title+' results');
        for(const column of result.columns){
          const title=reportColumnTitle(column),th=el('th',title);th.setAttribute('scope','col');
          if(title!==column.name){const original=el('small',column.name);original.className='configuration-report-source-name';th.append(original);}
          header.append(th);
        }head.append(header);table.append(head,body);
        const viewport=el('div');viewport.className='configuration-report-table-scroll';
        viewport.setAttribute('role','region');viewport.setAttribute('aria-label',report.title+' saved rows');
        viewport.setAttribute('tabindex','0');viewport.append(table);
        for(const values of result.rows){const row=el('tr');for(const cell of values)row.append(el('td',reportCellText(cell)));body.append(row);}
        const bounds=result.view==='Balance'?`Displayed balance before ${result.at} (exclusive).`:['Turnovers','BalanceAndTurnovers'].includes(result.view)?`Displayed saved period from ${result.start} through ${result.end} (inclusive).`:'Displayed saved movements, without a period filter.';
        output.append(el('p',bounds+' Editing the controls does not change this result until Show saved stock.'));
        if(statement(result)){
          output.append(el('p',`Statement periodicity: ${result.periodicity}. Opening is strictly before the start; sparse boundary rows do not fill every empty day or month.`));
          for(const filter of result.filters)output.append(el('p',filter.id+': '+(filter.mode==='all'?'All saved values':filter.text)));
        }
        const page=result.page;
        output.append(el('p',page?`${page.total? page.offset+1:0}–${page.offset+result.rows.length} of ${page.total} saved rows. Pages share this detached snapshot. Refresh explicitly after another writer changes the database.`:`${result.rows.length} saved rows. Refresh explicitly after another writer changes the database.`),el('p','Dates have no timezone conversion. Focus the saved rows region to scroll wide tables with the keyboard.'),viewport);
        if(page){const nav=el('nav');nav.setAttribute('aria-label','Statement pages');
          for(const [label,cursor] of [['Previous saved page',page.previous],['Next saved page',page.next]])button(nav,label,disabled || cursor===null,()=>run('application.reportPage',{snapshot:page.snapshot,cursor}));output.append(nav);}
        if(!result.rows.length)output.append(el('p','No saved rows for these boundaries.'));
      }else output.append(el('p','Choose boundaries and show saved stock. Changes to forms clear the previous report.'));
    }
  }
  show.addEventListener('click',()=>{
    if(busy || blocked() || !state)return;
    const report=state.reports.find(r=>r.id===selected),ranged=['Turnovers','BalanceAndTurnovers'].includes(report.view);
    const value=field=>field.value.length===16?field.value+':00':field.value;
    const params={report:selected,at:report.view==='Balance'?value(at.field):null,start:ranged?value(start.field):null,end:ranged?value(end.field):null,
      ...(statement(report)?{periodicity:period.value,setup:state.reportSetup?.ticket}:{})};
    if(!validReportRequest(params,state)){localError='Enter valid whole-second boundaries; the start must not exceed the end. Statements support 1900–2099 and require prepared filters.';paint();return;}
    run('application.report',params);
  });
  return {update(next){state=next;paint();},pending:()=>busy};
}
