/** Read-only stock projections. A label is never a reference or write capability. */
import {FormError, validateScalar, scalarText} from '../../form/src/client.mjs';
const keys = (v,names) => v !== null && typeof v === 'object' && !Array.isArray(v) &&
  Object.keys(v).length === names.length && names.every(n => Object.hasOwn(v,n));
const text = (v,n=1152) => typeof v === 'string' && v.length <= n*2 && [...v].length <= n &&
  !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v);
const views = ['Movements','Balance','Turnovers'];
const date = value => {
  if (!text(value,19) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value)) return false;
  const [year,month,day,hour,minute,second]=value.match(/\d+/g).map(Number);
  const leap=year%4===0 && (year%100!==0 || year%400===0);
  return year>=1 && month>=1 && month<=12 && day>=1 && day<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1] && hour<24 && minute<60 && second<60;
};
export function validReportRequest(params, state) {
  if (!keys(params,['report','at','start','end']) || !state?.reports?.some(r=>r.id===params.report) ||
      state.kind==='closed' || state.choice || state.uncertain || state.posting?.some(p=>['uncertain','committed'].includes(p.state))) return false;
  const view=state.reports.find(r=>r.id===params.report).view;
  return view==='Movements' ? params.at===null && params.start===null && params.end===null
    : view==='Balance' ? date(params.at) && params.start===null && params.end===null
    : params.at===null && date(params.start) && date(params.end) && params.start<=params.end;
}
export function validateReports(state, previous) {
  const enabled=Object.hasOwn(state,'reports');
  if (enabled !== Object.hasOwn(state,'report') || previous && enabled!==Object.hasOwn(previous,'reports')) throw new FormError('transport');
  if (!enabled) return;
  if (!Array.isArray(state.reports) || state.reports.length>96 || previous && JSON.stringify(state.reports)!==JSON.stringify(previous.reports)) throw new FormError('transport');
  const seen=new Set();
  for (const report of state.reports) {
    if (!keys(report,['id','title','view']) || !text(report.id,128) || !/^[\p{ID_Start}_][\p{ID_Continue}]*$/u.test(report.id) ||
        seen.has(report.id) || !text(report.title,256) || !views.includes(report.view)) throw new FormError('transport');
    seen.add(report.id);
  }
  if (state.report===null) return;
  const result=state.report, declared=state.reports.find(r=>r.id===result?.report);
  if (!keys(result,['report','view','at','start','end','columns','rows']) || !declared || declared.view!==result.view ||
      !validReportRequest({report:result.report,at:result.at,start:result.start,end:result.end},{...state,choice:null,posting:[],uncertain:false}) ||
      !Array.isArray(result.columns) || !result.columns.length || result.columns.length>32 ||
      !Array.isArray(result.rows) || result.rows.length>1000 || result.rows.length*result.columns.length>25000) throw new FormError('transport');
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
export function reportCellText(cell) {
  return ['Catalog','Document'].includes(cell.type) ? cell.text : scalarText(cell);
}
export function createReportPanel(document, host, request, blocked) {
  const el=(tag,content='')=>{const n=document.createElement(tag);n.textContent=content;return n;};
  const title=el('h2','Stock reports'), navigation=el('nav'), controls=el('div'), output=el('div'), notice=el('p');
  host.className='configuration-reports';host.setAttribute('aria-label','Saved stock reports');host.hidden=true;
  navigation.setAttribute('aria-label','Declared stock reports');notice.setAttribute('role','status');
  const input=(labelText)=>{const label=el('label',labelText),field=el('input');field.type='datetime-local';field.step='1';field.setAttribute('aria-label',labelText);label.append(field);controls.append(label);return {label,field};};
  const at=input('Balance before moment (exclusive)'), start=input('From moment (inclusive)'), end=input('Through moment (inclusive)');
  const now=new Date(),pad=v=>String(v).padStart(2,'0');
  const today=`${String(now.getFullYear()).padStart(4,'0')}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
  at.field.value=today+'T23:59:59';start.field.value=today+'T00:00:00';end.field.value=today+'T23:59:59';
  const show=el('button','Show saved stock');show.type='button';controls.append(show);
  host.append(title,el('p','Read-only saved database state. Unsaved form edits are not included. No movement or total can be edited here.'),navigation,controls,notice,output);
  let state=null, selected=null, busy=false, localError='', lastResult=undefined;
  function paint() {
    host.hidden=!state?.reports?.length;if(host.hidden)return;
    if(!state.reports.some(r=>r.id===selected))selected=state.reports[0].id;
    const disabled=busy || blocked(), report=state.reports.find(r=>r.id===selected);
    navigation.replaceChildren();
    for(const item of state.reports){const button=el('button',item.title);button.type='button';button.disabled=disabled;button.setAttribute('aria-pressed',String(item.id===selected));
      button.addEventListener('click',()=>{if(busy || blocked())return;selected=item.id;localError='';paint();});navigation.append(button);}
    at.label.hidden=report.view!=='Balance';start.label.hidden=end.label.hidden=report.view!=='Turnovers';
    for(const field of [at.field,start.field,end.field])field.disabled=disabled;
    show.disabled=disabled;notice.textContent=localError || (disabled?'Finish the current selection or uncertain operation before reading stock.':'');
    const result=state.report?.report===selected?state.report:null;
    if(result!==lastResult){output.replaceChildren();lastResult=result;
      if(result){const table=el('table'),header=el('tr'),head=el('thead'),body=el('tbody');
        table.setAttribute('aria-label',report.title+' results');
        for(const column of result.columns)header.append(el('th',column.name));head.append(header);table.append(head,body);
        for(const values of result.rows){const row=el('tr');for(const cell of values)row.append(el('td',reportCellText(cell)));body.append(row);}
        const bounds=result.view==='Balance'?`Displayed balance before ${result.at} (exclusive).`:result.view==='Turnovers'?`Displayed turnovers from ${result.start} through ${result.end} (inclusive).`:'Displayed saved movements, without a period filter.';
        output.append(el('p',bounds+' Editing the controls does not change this result until Show saved stock.'));
        output.append(el('p',`${result.rows.length} saved rows. Refresh explicitly after another writer changes the database.`),table);
        if(!result.rows.length)output.append(el('p','No saved rows for these boundaries.'));
      }else output.append(el('p','Choose boundaries and show saved stock. Changes to forms clear the previous report.'));
    }
  }
  show.addEventListener('click',async()=>{
    if(busy || blocked() || !state)return;
    const report=state.reports.find(r=>r.id===selected);
    const value=field=>field.value.length===16?field.value+':00':field.value;
    const params={report:selected,at:report.view==='Balance'?value(at.field):null,start:report.view==='Turnovers'?value(start.field):null,end:report.view==='Turnovers'?value(end.field):null};
    if(!validReportRequest(params,state)){localError='Enter valid whole-second boundaries; the start must not exceed the end.';paint();return;}
    busy=true;localError='';paint();
    try{const result=await request(params);if(result?.error)localError=result.error==='report_busy'?'Resolve the pending saved operation first.':'This report is unavailable or exceeds the bounded result limit.';}
    catch{localError='Report request did not finish. It will not be repeated automatically.';}
    finally{busy=false;paint();}
  });
  return {update(next){state=next;paint();},pending:()=>busy};
}
