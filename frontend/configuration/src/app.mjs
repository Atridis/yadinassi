import {createReportPanel} from './reports.mjs';
import {INPUT_CAPABILITY, inputField, validInputAnswer} from './inputs.mjs';
import {FormError, createTransport, takeSessionCapability, scalarText, inputHint, typedInput} from '../../form/src/client.mjs';
import {mountForm} from '../../form/src/app.mjs';
import {createBrowserHost, documentInstance} from '../../form/src/attachment.mjs';
import {APPLICATION_PROTOCOL, DIALOG_CAPABILITY, ApplicationClient} from './client.mjs';

export function mountApplication(environment, root, exchange = null) {
  const browserHost = exchange ? null : createBrowserHost(environment, root);
  root = browserHost?.content || root;
  const instance = browserHost?.instance || documentInstance(environment);
  const document = environment.document;
  const el = (tag, text = '') => { const node = document.createElement(tag); node.textContent = text; return node; };
  const shell = el('main'), title = el('h1','Configuration forms'), toolbar = el('nav'), entries = el('nav'), tabs = el('nav'), panels = el('div');
  const workarea = el('div'), catalogPanel = el('section'); workarea.className = 'configuration-workarea';
  panels.className = 'configuration-form-panels';
  catalogPanel.className = 'configuration-catalog'; catalogPanel.setAttribute('aria-label','Catalog records'); catalogPanel.hidden = true;
  shell.className = 'configuration-app'; entries.setAttribute('aria-label','Declared forms'); tabs.setAttribute('aria-label','Open forms');
  const reportPanel=el('section');
  const reportView=createReportPanel(document,reportPanel,params=>perform('application.report',params),
    ()=>Boolean(!client || client.pending || client.terminal || client.state?.kind==='closed' || client.state?.uncertain || client.state?.choice || dialogModal() || client.state?.posting?.some(p=>['uncertain','committed'].includes(p.state))),
    (method,params)=>perform(method,params));
  const postingPanel = el('section'); postingPanel.setAttribute('aria-label','Posting operation');
  const notice = el('p'); notice.setAttribute('role','status');
  const applicationMessages = el('section'), exitWarning = el('p');
  applicationMessages.setAttribute('aria-label','Application messages'); applicationMessages.setAttribute('aria-live','polite');
  exitWarning.setAttribute('role','status');
  const mounts = new Map(), openings = new Map(); let active = null, openToken = 0, status = '', navigation = 0, client;
  const intents = new Map();
  let dialogBusy = false, dialogTicket = null, dialogReturn = null;
  const dialog = el('section'), dialogTitle = el('h2'), dialogText = el('p'), dialogStatus = el('p'), dialogActions = el('div');
  dialog.className = 'configuration-dialog'; dialog.hidden = true; dialog.setAttribute('role','dialog');
  dialogTitle.id = `question-title-${instance}`; dialog.setAttribute('aria-labelledby',dialogTitle.id);
  dialogText.id = `question-text-${instance}`; dialog.setAttribute('aria-describedby',dialogText.id);
  dialogStatus.setAttribute('role','status'); dialogActions.className = 'dialog-commands';
  dialog.append(dialogTitle,dialogText,dialogStatus,dialogActions);
  const dialogModal = () => Boolean((client?.dialogs?.length || client?.inputs?.length) && !client.terminal);
  let inputBusy = false, inputTicket = null, inputReturn = null, inputControl = null, inputSelected = null, inputRows = [], inputError = '', inputNeedsFocus = false, inputInitialText = null;
  const inputDialog = el('section'), inputTitle = el('h2'), inputText = el('p'), inputStatus = el('p'), inputBody = el('div'), inputActions = el('div');
  inputDialog.className = 'configuration-dialog configuration-value-input'; inputDialog.hidden = true; inputDialog.setAttribute('role','dialog');
  inputTitle.id = `input-title-${instance}`; inputStatus.id = `input-status-${instance}`;
  inputDialog.setAttribute('aria-labelledby',inputTitle.id); inputDialog.setAttribute('aria-describedby',inputStatus.id);
  inputStatus.setAttribute('role','status'); inputActions.className = 'dialog-commands'; inputBody.className = 'typed-input-body';
  inputDialog.append(inputTitle,inputText,inputBody,inputStatus,inputActions);

  let pickerBusy = false, pickerTicket = null, pickerReturn = null, pickerQueryBaseline = null, pickerCodeBaseline = null;
  const picker = el('section'), pickerTitle = el('h2'), pickerHelp = el('p'), pickerError = el('p');
  const pickerActions = el('div'), pickerRows = el('div'), codeLabel = el('label','Exact code'), pickerCode = el('input');
  picker.className = 'panel reference-picker'; picker.setAttribute('role','dialog'); picker.setAttribute('aria-modal','true'); picker.hidden = true;
  pickerTitle.id = `reference-title-${instance}`; picker.setAttribute('aria-labelledby',pickerTitle.id);
  pickerCode.type = 'text'; pickerCode.maxLength = 64; pickerCode.autocomplete = 'off'; pickerCode.spellcheck = false;
  pickerCode.setAttribute('aria-label','Exact code'); codeLabel.append(pickerCode);
  const queryLabel=el('label','Code or description'),pickerQuery=el('input');
  pickerQuery.type='search';pickerQuery.maxLength=128;pickerQuery.setAttribute('aria-label','Reference search');queryLabel.append(pickerQuery);
  pickerHelp.textContent = 'Choose an existing record. Enter its exact code to filter. Cancel keeps the current value.';
  pickerError.setAttribute('role','status'); pickerRows.setAttribute('aria-label','Reference matches');
  picker.append(pickerTitle,pickerHelp,codeLabel,queryLabel,pickerActions,pickerError,pickerRows);
  let selectedEntry = null; const selectedRecords = new Set();
  let queryEntry=null,queryBaseline='',queryDraft='';
  const button = (text, parent, action) => {
    const node = el('button',text); node.type = 'button'; node.dataset.formAction = 'application-navigation';
    node.addEventListener('pointerdown',event => event.preventDefault()); node.addEventListener('click',action); parent.append(node); return node;
  };
  const pending = () => Boolean(inputBusy || client.inputs.length || dialogBusy || client.dialogs.length || pickerBusy || client.state?.choice || client.state?.posting?.some(item => ['uncertain','committed'].includes(item.state)) || client.pending || client.terminal || client.state?.uncertain || [...mounts.values()].some(entry => entry.mount?.hasPending()));
  function show(id, userNavigation = true) {
    if (userNavigation && (client.state?.choice || dialogModal())) return;
    if (userNavigation) navigation++;
    active = id;
    for (const [key, entry] of mounts) {
      if (!entry.panel.hidden && entry.panel.contains(document.activeElement)) {
        const node = document.activeElement; entry.focus = {node,start:node.selectionStart,end:node.selectionEnd};
      }
      entry.panel.hidden = key !== id; entry.tab.setAttribute('aria-selected',String(key === id));
    }
    const saved = mounts.get(id)?.focus;
    if (saved?.node && !saved.node.disabled) { saved.node.focus({preventScroll:true}); if (typeof saved.start === 'number') saved.node.setSelectionRange(saved.start,saved.end); }
    workarea.className = active && client.state?.catalog ? 'configuration-workarea with-form' : 'configuration-workarea';
    if (client.state) paint();
  }
  async function choose(action, ticket = client.state?.choice?.ticket) {
    const choice = client.state?.choice;
    if (!choice || choice.ticket !== ticket || pickerBusy || client.pending || client.terminal || client.state.uncertain) return;
    const entry = mounts.get(choice.session); if (!entry?.mount) return;
    if (action.action === 'filter' && (typeof action.code !== 'string' || [...action.code].length > 64 ||
        /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(action.code))) {
      status = 'Enter an exact code of at most 64 characters.'; paint(); return;
    }
    if(action.action==='search'&&(typeof action.query!=='string'||[...action.query].length>128||
      /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(action.query))){
      status='Enter a search of at most 128 characters.';paint();return;
    }
    // Do not route cancellation through native form validation or raw code parsing.
    pickerBusy = true; paint();
    try { await entry.mount.reference({...action,ticket}); }
    finally { pickerBusy = false; paint(); }
  }
  const filter = button('Find exact code',pickerActions,() => choose({action:'filter',code:pickerCode.value}));
  const searchChoice=button('Search references',pickerActions,()=>choose({action:'search',query:pickerQuery.value}));
  const previousChoice=button('Previous choices',pickerActions,()=>choose({action:'page',cursor:client.state?.choice?.navigation?.previous}));
  const nextChoice=button('Next choices',pickerActions,()=>choose({action:'page',cursor:client.state?.choice?.navigation?.next}));
  pickerQuery.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();choose({action:'search',query:pickerQuery.value});}});
  const cancel = button('Cancel selection',pickerActions,() => choose({action:'cancel'}));
  pickerCode.addEventListener('keydown',event => {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); choose({action:'filter',code:pickerCode.value}); }
  });
  picker.addEventListener('keydown',event => {
    if (event.key === 'Escape') { event.preventDefault(); choose({action:'cancel'}); }
    if (event.key !== 'Tab') return;
    const descendants = node => [node,...Array.from(node.children || []).flatMap(descendants)];
    const nodes = descendants(picker).filter(node => ['BUTTON','INPUT','TEXTAREA'].includes(node.tagName) && !node.disabled && !node.closest('[hidden]'));
    const index = nodes.indexOf(document.activeElement);
    if (nodes.length && (event.shiftKey && index <= 0 || !event.shiftKey && (index < 0 || index === nodes.length - 1))) {
      event.preventDefault(); nodes[event.shiftKey ? nodes.length - 1 : 0].focus();
    }
  });
  function drawPicker() {
    const choice = client.state?.choice;
    picker.hidden = !choice;
    for (const node of [toolbar,entries,tabs,workarea,reportPanel]) node.inert = Boolean(choice || dialogModal());
    for (const entry of mounts.values()) entry.mount?.repaint();
    if (!choice) {
      pickerTicket = null;
      if (pickerReturn && !client.terminal) {
        const owner = mounts.get(pickerReturn.session);
        if (!owner || owner.panel.hidden || owner.mount?.view.focusReference(pickerReturn)) pickerReturn = null;
      }
      return;
    }
    const newTicket = pickerTicket !== choice.ticket;
    if (newTicket) { pickerTicket = choice.ticket; pickerReturn = choice; }
    if(newTicket||pickerCodeBaseline!==choice.code){pickerCode.value=choice.code;pickerCodeBaseline=choice.code;}
    pickerTitle.textContent = 'Choose ' + choice.title;
    const disabled = pickerBusy || client.pending > 0 || client.terminal || client.state.uncertain;
    filter.disabled = cancel.disabled = pickerCode.disabled = disabled;
    const paged=Object.hasOwn(choice,'navigation'),nav=choice.navigation;
    for(const node of [queryLabel,searchChoice,previousChoice,nextChoice])node.hidden=!paged;
    pickerQuery.disabled=searchChoice.disabled=disabled;
    previousChoice.disabled=disabled||!nav?.previous;nextChoice.disabled=disabled||!nav?.next;
    if(newTicket||pickerQueryBaseline!==(nav?.query??'')){pickerQuery.value=nav?.query??'';pickerQueryBaseline=nav?.query??'';}
    pickerHelp.textContent=paged?'Search code or description in a bounded snapshot, or read fresh exact-code matches. Selection rechecks the saved record. Cancel keeps the current value.':'Choose an existing record. Enter its exact code to filter. Cancel keeps the current value.';
    pickerError.textContent = client.terminal ? 'The outcome may be unknown. Selection is locked; no request will be repeated.'
      : choice.error === 'snapshot_limit' ? 'The complete result exceeds the supported snapshot budget. No partial rows are shown. Enter an exact code to narrow the read.'
      : choice.error === 'too_many_matches' ? 'Too many matches. Enter an exact code to continue.'
      : status || (nav ? `Page ${nav.page} of ${nav.pages}; ${nav.total} matching records` : choice.rows.length ? `${choice.rows.length} matching records` : 'No matching records.');
    pickerRows.replaceChildren();
    for (const row of choice.rows) {
      const entry = el('div'), description = el('span',row.code + ' · ' + row.description);
      entry.append(description);
      const select = button('Choose record',entry,() => choose({action:'apply',choice:row.choice},choice.ticket));
      select.setAttribute('aria-label','Choose ' + row.code + ' ' + row.description); select.disabled = disabled;
      pickerRows.append(entry);
    }
    if (newTicket || !disabled && picker.contains(document.activeElement) && document.activeElement.disabled) pickerCode.focus({preventScroll:true});
    if (!disabled && document.activeElement === document.body) pickerCode.focus({preventScroll:true});
  }
  async function answerDialog(owner, ticket, answer) {
    if (dialogBusy || client.pending || client.terminal || client.state?.uncertain ||
        !client.dialogs.some(value => value.owner === owner && value.ticket === ticket && value.choices.includes(answer))) return;
    dialogBusy = true; paint();
    try { await perform('application.answerDialog',{session:owner,ticket,answer}); }
    finally { dialogBusy = false; paint(); }
  }
  dialog.addEventListener('keydown',event => {
    // There is no implicit timeout/default/Escape outcome in this profile.
    if (event.key === 'Escape') { event.preventDefault(); return; }
    if (event.key !== 'Tab') return;
    const nodes = Array.from(dialogActions.children).filter(node => !node.disabled);
    const index = nodes.indexOf(document.activeElement);
    if (nodes.length && (event.shiftKey && index <= 0 || !event.shiftKey && (index < 0 || index === nodes.length - 1))) {
      event.preventDefault(); nodes[event.shiftKey ? nodes.length - 1 : 0].focus();
    }
  });
  function drawDialog() {
    const value = client.dialogs[0]; dialog.hidden = !value;
    dialog.setAttribute('aria-modal',String(Boolean(value && !client.terminal)));
    dialog.dataset.locked = String(client.terminal);
    if (!value) {
      dialogTicket = null;
      if (dialogReturn && !client.terminal) {
        if (document.body.contains(dialogReturn) && !dialogReturn.disabled) dialogReturn.focus({preventScroll:true});
        dialogReturn = null;
      }
      return;
    }
    const fresh = dialogTicket !== value.ticket;
    if (fresh) { dialogTicket = value.ticket; dialogReturn = document.activeElement; }
    dialogTitle.textContent = value.title || (value.kind === 'question' ? 'Question' : 'Message');
    dialogText.textContent = value.text;
    dialogStatus.textContent = client.terminal ? 'The outcome may be unknown. No answer will be repeated. Retained form text can be copied.'
      : dialogBusy || client.pending ? 'Sending answer…' : 'Choose a button to continue. The owner form is paused.';
    const prior = document.activeElement?.dataset?.dialogAnswer;
    dialogActions.replaceChildren();
    for (const answer of value.choices) {
      const node = button(({ok:'OK',cancel:'Cancel',yes:'Yes',no:'No',dismiss:'Continue'})[answer],dialogActions,
        () => answerDialog(value.owner,value.ticket,answer));
      node.dataset.dialogAnswer = answer;
      node.disabled = Boolean(dialogBusy || client.pending || client.terminal || client.state.uncertain);
    }
    const target = [...dialogActions.children].find(node => node.dataset.dialogAnswer === prior) || dialogActions.children[0];
    if (!target?.disabled && (fresh || dialog.contains(document.activeElement) || document.activeElement === document.body)) target.focus({preventScroll:true});
  }
  async function answerInput(owner, ticket, action) {
    if (inputBusy || client.pending || client.terminal || client.state?.uncertain ||
        !client.inputs.some(value => value.owner === owner && value.ticket === ticket)) return;
    inputBusy = true; inputError = ''; paint();
    try {
      const result = await client.request('application.answerInput',{session:owner,ticket,...action});
      if (result.error) inputError = result.error === 'input_refused' ? 'This answer was refused. Review the value before confirming.'
        : result.error === 'input_stale' ? 'The source list changed. Nothing was selected.' : 'The completion did not finish normally. Review the owner form.';
    } catch (error) {
      inputError = error?.preDispatch ? 'Enter a supported value within the field limits.' : 'The answer outcome may be unknown. No action will be repeated.';
    } finally { inputBusy = false; paint(); }
  }
  function confirmInput(owner, ticket) {
    const value = client.inputs.find(item => item.owner === owner && item.ticket === ticket);
    if (!value || ticket !== inputTicket || inputBusy || client.pending || client.terminal) return;
    let action;
    try {
      action = value.kind === 'choice' ? {action:'choose',choice:inputSelected} : {
        action:'accept',value:value.value.type === 'String' && inputControl.value === inputInitialText ? {...value.value} : typedInput(inputField(value),value.value.type === 'Boolean' ? inputControl.checked : inputControl.value)};
      if (!validInputAnswer({session:owner,ticket,...action},client.inputs)) throw Error('Invalid input');
    } catch { inputError = 'Enter a supported value within the field limits.'; paint(); return; }
    return answerInput(owner,ticket,action);
  }
  inputDialog.addEventListener('keydown',event => {
    const value = client.inputs[0]; if (!value || inputDialog.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); answerInput(value.owner,value.ticket,{action:'cancel'}); return; }
    if (event.key === 'Enter' && !event.isComposing && !event.shiftKey && event.target === inputControl && (inputControl.tagName !== 'TEXTAREA' || event.ctrlKey || event.metaKey)) {
      event.preventDefault(); confirmInput(value.owner,value.ticket); return;
    }
    if (event.key !== 'Tab' || client.terminal) return;
    const descendants = node => [node,...Array.from(node.children || []).flatMap(descendants)];
    const nodes = descendants(inputDialog).filter(node => ['BUTTON','INPUT','TEXTAREA'].includes(node.tagName) && !node.disabled && !node.closest('[hidden]'));
    const index = nodes.indexOf(document.activeElement);
    if (nodes.length && (event.shiftKey && index <= 0 || !event.shiftKey && (index < 0 || index === nodes.length - 1))) {
      event.preventDefault(); nodes[event.shiftKey ? nodes.length - 1 : 0].focus();
    }
  });
  function drawInput() {
    const value = client.inputs[0]; inputDialog.hidden = !value || client.dialogs.length > 0;
    inputDialog.setAttribute('aria-modal',String(Boolean(value && !client.terminal && !inputDialog.hidden)));
    inputDialog.dataset.locked = String(client.terminal);
    if (!value) {
      inputTicket = null; inputControl = null; inputRows = []; inputNeedsFocus = false; inputBody.replaceChildren(); inputActions.replaceChildren();
      if (inputReturn && !client.terminal) {
        if (document.body.contains(inputReturn) && !inputReturn.disabled) inputReturn.focus({preventScroll:true});
        inputReturn = null;
      }
      return;
    }
    const fresh = inputTicket !== value.ticket;
    if (fresh) {
      inputTicket = value.ticket; inputReturn = document.activeElement; inputError = ''; inputNeedsFocus = true; inputSelected = value.initial;
      inputBody.replaceChildren(); inputActions.replaceChildren(); inputControl = null; inputRows = [];
      if (value.kind === 'input') {
        const label = el('label','Value'); inputControl = el(value.value.type === 'String' ? 'textarea' : 'input'); inputControl.dataset.valueInput = 'scalar';
        inputControl.setAttribute('aria-label',value.text || 'Value'); inputControl.autocomplete = 'off';
        if (value.value.type === 'Boolean') { inputControl.type = 'checkbox'; inputControl.checked = value.value.value; }
        else { if (value.value.type !== 'String') inputControl.type = 'text'; else inputControl.rows = 3; inputControl.value = scalarText(value.value,value.editor);
          inputControl.spellcheck = false; if (value.value.type === 'Number') inputControl.inputMode = 'decimal'; }
        inputInitialText = inputControl.value;
        const hint = el('p',value.value.type === 'String' ? 'Enter keeps a line break. Ctrl+Enter confirms. Unchanged text preserves its original line endings.' : inputHint(inputField(value))); inputControl.setAttribute('aria-describedby',inputStatus.id);
        inputControl.addEventListener('input',() => { inputError = ''; inputStatus.textContent = hint.textContent; });
        label.append(inputControl); inputBody.append(label,hint);
      } else {
        const group = el('div'); group.setAttribute('role','radiogroup'); group.setAttribute('aria-label',value.title || 'Choose a value');
        for (const row of value.choices) {
          const label = el('label'), radio = el('input'); radio.type = 'radio'; radio.name = `input-choice-${instance}`;
          radio.dataset.valueChoice = row.choice; radio.checked = inputSelected === row.choice;
          radio.setAttribute('aria-label',row.presentation || scalarText(row.value));
          radio.addEventListener('change',() => {
            if (client.terminal || inputBusy || client.pending || inputTicket !== value.ticket || !client.inputs.some(i => i.ticket === value.ticket)) return;
            inputSelected = row.choice; inputError = ''; paint();
          });
          label.append(radio,el('span',row.presentation || scalarText(row.value))); group.append(label); inputRows.push(radio);
        }
        if (!value.choices.length) group.append(el('p','No choices are available. Cancel to continue.'));
        inputBody.append(group);
      }
      const accept = button('OK',inputActions,() => confirmInput(value.owner,value.ticket)); accept.dataset.inputAction = 'accept';
      const cancelInput = button('Cancel',inputActions,() => answerInput(value.owner,value.ticket,{action:'cancel'})); cancelInput.dataset.inputAction = 'cancel';
    }
    const disabled = Boolean(inputBusy || client.pending || client.terminal || client.state.uncertain);
    inputTitle.textContent = value.title || (value.kind === 'input' ? 'Enter a value' : 'Choose a value');
    inputText.textContent = value.kind === 'input' ? value.text : 'Choose one item and confirm. Cancel returns no value.';
    inputStatus.textContent = client.terminal ? 'The outcome may be unknown. Retained input is copy-only; no answer will be repeated.'
      : inputBusy || client.pending ? 'Sending answer…' : inputError || 'The owner form is paused. Cancel does not submit the input.';
    if (inputControl) { inputControl.readOnly = disabled; inputControl.disabled = value.value.type === 'Boolean' && disabled; }
    for (const radio of inputRows) { radio.checked = radio.dataset.valueChoice === inputSelected; radio.disabled = disabled; }
    for (const node of inputActions.children) node.disabled = disabled || node.dataset.inputAction === 'accept' && value.kind === 'choice' && inputSelected === null;
    if (inputNeedsFocus && !disabled && !inputDialog.hidden) {
      const target = inputControl || inputRows.find(row => row.checked) || inputRows[0] || inputActions.children[1];
      target.focus({preventScroll:true});
      if (document.activeElement === target) inputNeedsFocus = false;
    }
  }
  function reconcileSelection() {
    const catalog = client.state?.catalog;
    if (!catalog || selectedEntry !== catalog.entry) selectedRecords.clear();
    selectedEntry = catalog?.entry ?? null;
    const keys = new Set(catalog?.rows.map(row => row.key) || []);
    for (const key of selectedRecords) if (!keys.has(key)) selectedRecords.delete(key);
  }
  function drawCatalog() {
    reconcileSelection(); catalogPanel.replaceChildren();
    const catalog = client.state?.catalog;
    catalogPanel.hidden = !catalog;
    workarea.className = active && catalog ? 'configuration-workarea with-form' : 'configuration-workarea';
    if (!catalog) return;
    const entry = client.state.entries.find(entry => entry.id === catalog.entry);
    const posting = entry.kind === 'posting-document', document = posting || entry.kind === 'document-object';
    const heading = el('h2',entry.title), actions = el('div'); actions.className = 'catalog-commands';
    const unavailable = () => Boolean(client.state?.choice || dialogModal()) || client.terminal || client.state?.uncertain || client.state?.kind === 'closed' || client.pending > 0;
    const create = button(document ? 'New document' : 'New record',actions,() => { if (!unavailable()) openForm(catalog.entry); });
    const openSelected = () => {
      // Resolve from the live set and latest projection, never a captured row
      // index or a previous render's single selection.
      reconcileSelection();
      const current = client.state?.catalog, key = [...selectedRecords][0];
      if (!unavailable() && selectedRecords.size === 1 && current?.rows.some(row => row.key === key)) openForm(current.entry,key);
    };
    const open = button('Open selected',actions,openSelected);
    const refresh = button('Refresh records',actions,() => { if (!unavailable()) perform('application.catalog',{entry:catalog.entry}); });
    if (catalog.navigation) {
      const nav=catalog.navigation;
      if(queryEntry!==catalog.entry||queryBaseline!==nav.query){queryEntry=catalog.entry;queryBaseline=nav.query;queryDraft=nav.query;}
      const search=el('input');search.type='search';search.value=queryDraft;search.maxLength=128;search.setAttribute('aria-label','Search records');
      search.addEventListener('input',()=>{queryDraft=search.value;});
      const order=el('select');order.setAttribute('aria-label','Record order');
      for(const key of (document?['date','number']:['code','description'])){const option=el('option',key);option.value=key;order.append(option);}
      order.value=nav.order;
      const apply=()=>{if(!unavailable())perform('application.catalogFilter',{entry:catalog.entry,snapshot:nav.snapshot,query:queryDraft,order:order.value});};
      search.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();apply();}});
      actions.append(search,order);const filter=button('Search records',actions,apply);
      const previous=button('Previous records',actions,()=>{if(!unavailable()&&nav.previous)perform('application.catalogPage',{entry:catalog.entry,snapshot:nav.snapshot,cursor:nav.previous});});
      const next=button('Next records',actions,()=>{if(!unavailable()&&nav.next)perform('application.catalogPage',{entry:catalog.entry,snapshot:nav.snapshot,cursor:nav.next});});
      previous.disabled=unavailable()||nav.previous===null;next.disabled=unavailable()||nav.next===null;
      search.disabled=order.disabled=filter.disabled=unavailable();
      const page=el('span',`Page ${nav.page} of ${nav.pages}; ${nav.total} matching records`);page.setAttribute('aria-live','polite');actions.append(page);
    }
    const count = el('span'); count.setAttribute('aria-label','Selected record count'); count.setAttribute('aria-live','polite'); actions.append(count);
    const table = el('table'), head = el('thead'), headings = el('tr');
    for (const title of (document ? ['Select','Number','Date','Deletion mark',...(posting ? ['Posted'] : [])] : ['Select','Code','Description','Deletion mark'])) headings.append(el('th',title));
    head.append(headings);table.append(head);const body = el('tbody'); table.append(body);
    const rows = [];
    function paintSelection() {
      for (const {row,check,key} of rows) { const checked = selectedRecords.has(key); check.checked = checked; check.disabled = unavailable(); row.setAttribute('aria-selected',String(checked)); }
      count.textContent = `${selectedRecords.size} selected`;
      open.disabled = unavailable() || selectedRecords.size !== 1; create.disabled = refresh.disabled = unavailable();
    }
    function select(key, multiple) {
      if (unavailable()) return;
      if (multiple) { if (selectedRecords.has(key)) selectedRecords.delete(key); else selectedRecords.add(key); }
      else { selectedRecords.clear(); selectedRecords.add(key); }
      paintSelection();
    }
    for (const record of catalog.rows) {
      const row = el('tr'), selectCell = el('td'), check = el('input'); check.type = 'checkbox'; row.tabIndex = 0;
      row.dataset.recordKey = record.key;check.setAttribute('aria-label',`Select ${document ? record.number : record.code} ${document ? record.date : record.description}`);
      check.addEventListener('click',event => { event.stopPropagation?.(); select(record.key,true); });
      row.addEventListener('click',event => select(record.key,Boolean(event.ctrlKey || event.metaKey)));
      row.addEventListener('keydown',event => {
        if (event.target && event.target !== row) return;
        if (event.key === ' ') { event.preventDefault();select(record.key,Boolean(event.ctrlKey || event.metaKey)); }
        if (event.key === 'Enter') { event.preventDefault();if (selectedRecords.size === 1 && selectedRecords.has(record.key)) openSelected(); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); const index = rows.findIndex(item => item.row === row);
          rows[index+(event.key === 'ArrowDown'?1:-1)]?.row.focus();
        }
      });
      selectCell.append(check);row.append(selectCell,el('td',document ? record.number : record.code),el('td',document ? record.date : record.description),el('td',record.deletionMark?'Marked':''));
      if (posting) row.append(el('td',record.posted ? 'Posted' : 'Not posted'));
      rows.push({row,check,key:record.key});body.append(row);
    }
    catalogPanel.append(heading,actions,el('p','Records snapshot. Refresh shows external changes; Save refreshes this list without replacing other open drafts.'),table);
    if (!catalog.rows.length) catalogPanel.append(el('p','No records yet.'));
    paintSelection();
    workarea.className = active ? 'configuration-workarea with-form' : 'configuration-workarea';
  }
  function paint() {
    browserHost?.notify();
    applicationMessages.replaceChildren(...(client.state?.messages || []).map(message => el('p',message)));
    applicationMessages.hidden = !client.state?.messages?.length;
    exitWarning.textContent = client.state?.exitWarning || ''; exitWarning.hidden = !exitWarning.textContent;
    title.textContent = client.state?.title || 'Configuration forms';
    notice.textContent = client.terminal ? 'Connection lost. All forms are locked; copy pending edits before leaving. Requests will not be replayed.' : status;
    const disabled = client.terminal || !client.state || client.state.kind === 'closed' || Boolean(client.state.choice || dialogModal());
    close.disabled = disabled; entries.replaceChildren();
    for (const entry of client.state?.entries || []) {
      const node = button(entry.title || `Form ${entry.id}`,entries,() => {
        if (['catalog-object','document-object','posting-document'].includes(entry.kind)) { show(null);perform('application.catalog',{entry:entry.id}); }
        else openForm(entry.id);
      });
      node.disabled = disabled || !['catalog-object','document-object','posting-document'].includes(entry.kind) && client.state.sessions.length >= 8;
    }
    for (const [id,entry] of mounts) {
      const blocked = Boolean(client.state?.sessions.find(value => value.id === id)?.blocked);
      entry.ownerNotice.hidden = !blocked;
      entry.ownerNotice.textContent = client.inputs.some(value => value.owner === id) ? 'This form is paused for an input answer. Pending text is retained.' : client.dialogs.some(value => value.owner === id) ? 'This form is paused for a dialog answer. Pending text is retained.' : blocked ? 'This form is paused while its owned form is open. Pending text is retained; finish or close the owned form to continue.' : '';
      if (client.terminal) entry.mount?.lock();
      else entry.mount?.repaint();
    }
    postingPanel.replaceChildren();
    const posting = client.state?.posting?.find(item => item.session === active);
    postingPanel.hidden = !posting;
    if (posting) {
      postingPanel.append(el('p',`Posting operation: ${posting.state}${posting.error ? ' ('+posting.error+')' : ''}. ${['uncertain','committed'].includes(posting.state) ? 'Posted state awaiting authoritative refresh' : posting.posted ? 'Posted' : 'Not posted'}.`));
      if (['uncertain','committed'].includes(posting.state)) {
        const recover = button('Resolve saved operation',postingPanel,async () => {
          if (client.pending || client.terminal || client.state.uncertain) return;
          const owner = posting.session, receipt = posting.receipt;
          const result = await perform('application.recoverPosting',{session:owner,receipt});
          if (result && mounts.has(owner)) await mounts.get(owner).mount.refresh();
        });
        recover.disabled = !posting.receipt || client.pending > 0 || client.terminal || client.state.uncertain;
        postingPanel.append(el('p','Recovery uses this host’s saved receipt. It never repeats posting handlers. Keep this application open.'));
      }
    }
    drawCatalog(); drawPicker(); drawDialog(); drawInput(); reportView.update(client.state);
  }
  function reconcile(result, request) {
    status = result.error === 'form_capacity'
      ? 'This saved document exceeds the editor row or cell limit. Nothing was opened or changed. Other forms and reports remain available.'
      : result.error ? `Application: ${result.error}` : '';
    const fresh = []; let removedActive = false;
    for (const [id, entry] of mounts) if (!client.state.sessions.some(session => session.id === id)) {
      entry.panel.remove(); entry.tab.remove(); mounts.delete(id); if (active === id) { active = null; removedActive = true; }
    }
    for (const session of client.state.sessions) {
      if (mounts.has(session.id)) { mounts.get(session.id).tab.textContent = session.title; continue; }
      const id = session.id, panel = el('section'); panel.hidden = true; panels.append(panel);
      const tab = button(session.title || 'Form',tabs,() => show(id));
      const ownerNotice = el('p'); ownerNotice.hidden = true; ownerNotice.setAttribute('role','status');
      const entry = {panel,tab,ownerNotice,mount:null,focus:null}; mounts.set(id,entry); fresh.push(id);
      entry.mount = mountForm(environment,panel,{transport: request => client.form(id,request),isActive: () => active === id,
        businessBlocked: () => Boolean(client.state?.sessions.find(value => value.id === id)?.blocked),
        referenceActive: () => Boolean(client.state?.choice || dialogModal()),
        onReference: Object.hasOwn(client.state,'choice') ? ({revision,action}) => client.reference(id,revision,action) : null,
        onChange: () => { if (entry.mount?.client?.transportFailed) client.lock(); paint(); }});
      // mountForm creates its own root content. Attach the owner notice after
      // that initial replacement, otherwise the retained node is detached.
      panel.insertBefore(ownerNotice, panel.children[0] || null);
    }
    try {
      if (['application.answerDialog','application.answerInput'].includes(request?.method) && result.form) {
        const target = mounts.get(result.session);
        if (!target?.mount) throw Error('Retired dialog owner');
        target.mount.adoptExternal(result.form);
      }
      for (const update of result.updates || []) {
        const target = mounts.get(update.session);
        if (!target?.mount) throw Error('Retired completion owner');
        target.mount.adoptExternal(update.form);
      }
    } catch {
      // A malformed/stale or concurrently busy owner cannot safely adopt an
      // already executed completion. Lock the family; never replay the result.
      client.lock(); status = 'Completion state could not be reconciled. All forms are locked.';
    }
    const generation = ['application.open','application.openRecord'].includes(request?.method) ? intents.get(request.params.request) : undefined;
    if (fresh.length && (generation === undefined || generation === navigation)) show(client.state.active || fresh.at(-1),false);
    else if (removedActive) show(client.state.active,false);
    paint();
  }
  async function perform(method,params) {
    try { return await client.request(method,params); }
    catch(error) {
      if(error?.preDispatch && method.startsWith('application.report'))return {error:'report_unavailable'};
      status = 'Application connection failed.'; paint();
    }
    finally { paint(); }
  }
  function openForm(entry, record = null) {
    if (client.state?.choice || dialogModal()) return Promise.resolve();
    const key = `${entry}:${record ?? ''}`;
    if (openings.has(key)) return openings.get(key);
    const token = `open-${instance}-${++openToken}`; intents.set(token,navigation);
    const params = {entry,request:token}; if (record !== null) params.record = record;
    const opening = perform(record === null?'application.open':'application.openRecord',params).finally(() => { openings.delete(key); intents.delete(token);paint(); });
    openings.set(key,opening); return opening;
  }
  const close = button('Close application',toolbar,async () => {
    if (pending() || mounts.size) { status = 'Close each form, including hidden tabs, before closing the application.'; paint(); return; }
    await perform('application.close',{});
  });
  workarea.append(catalogPanel,panels);shell.append(title,toolbar,applicationMessages,exitWarning,entries,tabs,notice,postingPanel,workarea,reportPanel,picker,dialog,inputDialog); root.replaceChildren(shell);
  if (!exchange) exchange = browserHost.transport;
  client = new ApplicationClient(exchange,reconcile,() => { for (const entry of mounts.values()) entry.mount?.lock(); paint(); });
  environment.addEventListener('beforeunload',event => { if (pending()) { event.preventDefault(); event.returnValue = ''; } });
  browserHost?.setPending(pending, () => Boolean(client.terminal || client.state?.uncertain));
  browserHost?.setInspectionAllowed(() => Boolean((client.terminal || client.state?.uncertain) && !client.pending &&
    !pickerBusy && !client.state?.choice && mounts.size &&
    [...mounts.values()].every(entry => entry.mount?.client?.locked && !entry.mount.client.busy) &&
    ([...mounts.values()].some(entry => entry.mount?.client?.snapshot?.items.some(item => item.kind === 'group')) ||
      client.state.sessions.some(session => Object.hasOwn(session,'owner')))));
  const resume = async () => {
    try {
      if (client.terminal) throw Error('Unknown previous outcome');
      const retained = new Set(mounts.keys());
      const result = await client.request('application.hello',{protocol:APPLICATION_PROTOCOL,dialogCapability:DIALOG_CAPABILITY,inputCapability:INPUT_CAPABILITY});
      for (const [id,entry] of mounts) {
        if (retained.has(id)) await entry.mount.reconcileOwnership(); else await entry.mount.ready;
        if (entry.mount.client?.transportFailed || entry.mount.client?.outcomeUnknown) throw Error('Unknown form outcome');
      }
      return result;
    } finally {
      // Reconciliation paints while the hello request is still pending.
      // Recompute controls after it settles; ownership and error gates remain.
      paint();
    }
  };
  paint(); const ready = browserHost ? browserHost.start(resume) : perform('application.hello',{protocol:APPLICATION_PROTOCOL,dialogCapability:DIALOG_CAPABILITY,inputCapability:INPUT_CAPABILITY});
  return {ready,client,mounts,show,pending,openForm,browserHost};
}
if (typeof window !== 'undefined' && window.document?.getElementById('configuration-app')) mountApplication(window,window.document.getElementById('configuration-app'));
