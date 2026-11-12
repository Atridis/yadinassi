import {validReportRequest, validReportAction, validateReports, validateReportReply} from './reports.mjs';
import {INPUT_CAPABILITY, validateInputs, validInputAnswer} from './inputs.mjs';
import {FormError, validateSnapshot, PROTOCOL as FORM_PROTOCOL} from '../../form/src/client.mjs';

export const APPLICATION_PROTOCOL = 'yadinassi-configuration-app/3';
export const DIALOG_CAPABILITY = 'yadinassi-owned-dialog/1';
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join() === [...expected].sort().join();
const integer = value => Number.isSafeInteger(value) && value > 0;
const text = (value, max) => typeof value === 'string' && value.length <= max * 2 && [...value].length <= max &&
  !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value);
const sessionId = value => typeof value === 'string' && /^form-[1-9][0-9]{0,5}$/.test(value);
const recordKey = value => typeof value === 'string' && /^record-[1-9][0-9]{0,8}$/.test(value);
const errors = ['closed','outcome_unknown','capacity','form_capacity','open_failed','retired_session','forms_open',
  'catalog_unavailable','catalog_limit','report_unavailable','report_busy','invalid_record','object_required','save_recovery_required',
  'startup_cancelled','startup_failed','exit_cancelled','reference_refused','owned_child_open','completion_failed','dialog_pending','dialog_refused','dialog_retired','input_pending','input_refused','input_retired','input_stale'];
const opaque = value => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
const locator = value => text(value.control,128) && value.control.length > 0 &&
  (value.row === null && value.column === null || Number.isInteger(value.row) && value.row >= 1 && value.row <= 4096 && text(value.column,128) && value.column.length > 0);
function referenceAction(action, state, session) {
  if (!Object.hasOwn(state || {}, 'choice') || !state.sessions.some(value => value.id === session)) return false;
  if (['begin','clear'].includes(action?.action))
    return state.choice === null && keys(action,['action','control','row','column']) && locator(action);
  if (state.choice?.session !== session || action?.ticket !== state.choice.ticket) return false;
  if (action.action === 'cancel') return keys(action,['action','ticket']);
  if (action.action === 'filter') return keys(action,['action','ticket','code']) && text(action.code,64);
  return action.action === 'apply' && keys(action,['action','ticket','choice']) && opaque(action.choice) &&
    state.choice.error === null && state.choice.rows.some(row => row.choice === action.choice);
}
export function validateApplicationReply(reply, request, previous) {
  if (!keys(reply,['jsonrpc','id','result']) || reply.jsonrpc !== '2.0' || reply.id !== request.id) throw new FormError('transport');
  const result = reply.result, state = result?.state;
  const ownedResults = Object.hasOwn(result || {}, 'updates');
  const dialogCapability = Object.hasOwn(result || {}, 'dialogCapability');
  const inputCapability = Object.hasOwn(result || {}, 'inputCapability');
  const shape = ['kind','title','entries','sessions','active','uncertain','catalog','lifecycle','messages','exitWarning'];
  if (state && Object.hasOwn(state,'choice')) shape.push('choice');
  if (state && Object.hasOwn(state,'posting')) shape.push('posting');
  if (state && Object.hasOwn(state,'reports')) shape.push('reports','report');
  if (state && Object.hasOwn(state,'reportSetup')) shape.push('reportSetup');
  if (!keys(result,['protocol','state','error','session','form',...(ownedResults ? ['updates'] : []),...(dialogCapability ? ['dialogCapability','dialogs'] : []),...(inputCapability ? ['inputCapability','inputs'] : [])]) || result.protocol !== APPLICATION_PROTOCOL ||
      !(result.error === null || errors.includes(result.error)) || !(result.session === null || sessionId(result.session)) ||
      !keys(state,shape) || !['application','closed'].includes(state.kind) ||
      !['forms','prepared','starting','running','before_exit','exiting','cancelled','failed','closed'].includes(state.lifecycle) ||
      !Array.isArray(state.messages) || state.messages.length > 64 || state.messages.some(message => !text(message,4096)) || !text(state.exitWarning,4096) ||
      !text(state.title,1024) || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.entries) || !state.entries.length || state.entries.length > 64 ||
      !Array.isArray(state.sessions) || state.sessions.length > 8) throw new FormError('transport');
  validateReports(state,previous);
  validateReportReply(result,request,previous);
  const entries = new Set(), sessions = new Set();
  for (const entry of state.entries) {
    if (!keys(entry,['id','title','kind']) || !integer(entry.id) || entries.has(entry.id) || !text(entry.title,1024) ||
        !['form','catalog-object','document-object','posting-document'].includes(entry.kind)) throw new FormError('transport');
    entries.add(entry.id);
  }
  if (previous && Object.hasOwn(previous,'posting') !== Object.hasOwn(state,'posting')) throw new FormError('transport');
  if (previous && Object.hasOwn(previous,'choice') !== Object.hasOwn(state,'choice')) throw new FormError('transport');
  if (previous && JSON.stringify(state.entries) !== JSON.stringify(previous.entries)) throw new FormError('transport');
  if (state.catalog !== null) {
    const catalog = state.catalog;
    if (!keys(catalog,['entry','version','rows']) || !state.entries.some(e => e.id === catalog.entry && ['catalog-object','document-object','posting-document'].includes(e.kind)) ||
        !Number.isSafeInteger(catalog.version) || catalog.version < 0 || catalog.version > 2147483647 ||
        !Array.isArray(catalog.rows) || catalog.rows.length > 256) throw new FormError('transport');
    const kind = state.entries.find(entry => entry.id === catalog.entry).kind;
    const seen = new Set(), document = ['document-object','posting-document'].includes(kind), posting = kind === 'posting-document';
    for (const row of catalog.rows) {
      const fields = posting ? ['key','number','date','deletionMark','posted'] : document ? ['key','number','date','deletionMark'] : ['key','code','description','deletionMark'];
      if (posting && typeof row.posted !== 'boolean') throw new FormError('transport');
      if (!keys(row,fields) || !recordKey(row.key) || seen.has(row.key) || typeof row.deletionMark !== 'boolean' ||
          (document ? !text(row.number,9) || typeof row.date !== 'string' || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(row.date)
                    : !text(row.code,1024) || !text(row.description,1024))) throw new FormError('transport');
      seen.add(row.key);
    }
    if (previous?.catalog?.entry === catalog.entry && catalog.version < previous.catalog.version) throw new FormError('transport');
  }
  for (const session of state.sessions) {
    if (!keys(session,['id','entry','title',...(ownedResults ? ['owner','blocked'] : [])]) || !sessionId(session.id) || sessions.has(session.id) ||
        !entries.has(session.entry) || !text(session.title,1024)) throw new FormError('transport');
    const old = previous?.sessions.find(value => value.id === session.id);
    if (old && (old.entry !== session.entry || Object.hasOwn(old,'owner') !== ownedResults || ownedResults && old.owner !== session.owner)) throw new FormError('transport');
    if (ownedResults && (!(session.owner === null || sessionId(session.owner)) || typeof session.blocked !== 'boolean')) throw new FormError('transport');
    sessions.add(session.id);
  }
  const dialogOwners = new Set(), dialogTickets = new Set();
  if (dialogCapability) {
    if (result.dialogCapability !== DIALOG_CAPABILITY || !Array.isArray(result.dialogs) || result.dialogs.length > 8 ||
        !ownedResults && result.dialogs.length) throw new FormError('transport');
    for (const dialog of result.dialogs) {
      if (!keys(dialog,['ticket','owner','kind','title','text','choices']) || !opaque(dialog.ticket) || dialogTickets.has(dialog.ticket) ||
          !sessions.has(dialog.owner) || dialogOwners.has(dialog.owner) || !['question','warning'].includes(dialog.kind) ||
          !text(dialog.title,256) || !text(dialog.text,4096) || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(dialog.title + dialog.text) ||
          !(dialog.kind === 'warning' ? JSON.stringify(dialog.choices) === '["dismiss"]'
            : ['["ok"]','["ok","cancel"]','["yes","no"]','["yes","no","cancel"]'].includes(JSON.stringify(dialog.choices))) ||
          state.entries.find(e => e.id === state.sessions.find(s => s.id === dialog.owner).entry).kind === 'posting-document' ||
          state.choice?.session === dialog.owner) throw new FormError('transport');
      dialogOwners.add(dialog.owner); dialogTickets.add(dialog.ticket);
    }
  }
  const inputOwners = inputCapability ? validateInputs(result,sessions,dialogOwners,dialogTickets) : new Set();
  if (ownedResults) {
    const nodes = new Map(state.sessions.map(value => [value.id,value]));
    for (const session of state.sessions) {
      const children = state.sessions.filter(value => value.owner === session.id);
      if (children.length > 1 || children.length && (dialogOwners.has(session.id) || inputOwners.has(session.id)) || session.blocked !== (children.length === 1 || dialogOwners.has(session.id) || inputOwners.has(session.id))) throw new FormError('transport');
      const visited = new Set([session.id]); let owner = session.owner;
      if (owner !== null && state.entries.find(value => value.id === session.entry).kind !== 'form') throw new FormError('transport');
      while (owner !== null) {
        const parent = nodes.get(owner);
        if (!parent || visited.has(owner) || state.entries.find(value => value.id === parent.entry).kind === 'posting-document') throw new FormError('transport');
        visited.add(owner); owner = parent.owner;
      }
    }
    if (!Array.isArray(result.updates) || result.updates.length > 8) throw new FormError('transport');
    const updated = new Set();
    for (const update of result.updates) {
      const prior = previous?.sessions.find(value => value.id === update?.session);
      if (!keys(update,['session','form']) || !sessions.has(update.session) || update.session === result.session || updated.has(update.session) ||
          !prior?.blocked || !previous.sessions.some(value => value.owner === update.session && !sessions.has(value.id))) throw new FormError('transport');
      const nested = update.form;
      if (!keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || nested.id !== 1 ||
          !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL ||
          ![null,'event_failed','outcome_unknown'].includes(nested.result.error)) throw new FormError('transport');
      validateSnapshot(nested.result.state);
      if (nested.result.state.kind === 'closed') throw new FormError('transport');
      updated.add(update.session);
    }
  }
  if (!(state.active === null || sessions.has(state.active)) || state.kind === 'closed' && sessions.size) throw new FormError('transport');
  if (Object.hasOwn(state,'choice') && state.choice !== null) {
    const choice = state.choice;
    if (!keys(choice,['session','ticket','control','row','column','title','code','rows','error']) ||
        !sessions.has(choice.session) || !opaque(choice.ticket) || !locator(choice) || !text(choice.title,1024) || !text(choice.code,64) ||
        ![null,'too_many_matches'].includes(choice.error) || !Array.isArray(choice.rows) || choice.rows.length > 32 ||
        choice.error === 'too_many_matches' && choice.rows.length) throw new FormError('transport');
    const tokens = new Set();
    for (const row of choice.rows) {
      if (!keys(row,['choice','code','description']) || !opaque(row.choice) || tokens.has(row.choice) ||
          !text(row.code,64) || !text(row.description,1024)) throw new FormError('transport');
      tokens.add(row.choice);
    }
  }
  if (Object.hasOwn(state,'posting')) {
    if (!Array.isArray(state.posting) || state.posting.length > 8) throw new FormError('transport');
    const owners = new Set();
    for (const item of state.posting) {
      if (!keys(item,['session','receipt','state','error','posted']) || !sessions.has(item.session) || owners.has(item.session) ||
          !(item.receipt === null || opaque(item.receipt)) || !['new','unchanged','saved','committed','uncertain','rejected'].includes(item.state) ||
          ![null,'refresh_required','outcome_unknown','operation_refused'].includes(item.error) || (['uncertain','committed'].includes(item.state) ? item.posted !== null : typeof item.posted !== 'boolean')) throw new FormError('transport');
      owners.add(item.session);
    }
  }
  if (['application.form','application.reference','application.recoverPosting','application.answerDialog','application.answerInput'].includes(request.method) && result.session !== request.params.session) throw new FormError('transport');
  if (result.form !== null) {
    const nested = result.form;
    if (!['application.form','application.open','application.openRecord','application.hello','application.reference','application.recoverPosting','application.answerDialog','application.answerInput'].includes(request.method) || !result.session ||
        !keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || !integer(nested.id) ||
        request.method === 'application.form' && nested.id !== request.params.request.id ||
        ['application.reference','application.recoverPosting','application.answerDialog','application.answerInput'].includes(request.method) && nested.id !== 1 ||
        !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL ||
        !(nested.result.error === null || ['invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit','reference_refused'].includes(nested.result.error))) throw new FormError('transport');
    validateSnapshot(nested.result.state);
    if ((nested.result.state.kind === 'closed') === sessions.has(result.session)) throw new FormError('transport');
  } else if (['application.form','application.reference','application.recoverPosting','application.answerDialog','application.answerInput'].includes(request.method) && result.error === null) throw new FormError('transport');
  if (['application.open','application.openRecord'].includes(request.method) && result.error === null && !sessions.has(result.session)) throw new FormError('transport');
  return result;
}
export class ApplicationClient {
  constructor(exchange, changed = () => {}, failed = () => {}) {
    this.exchange = exchange; this.changed = changed; this.failed = failed; this.state = null;
    this.formRevisions = new Map(); this.catalogVersions = new Map(); this.retired = new Set(); this.id = 0; this.pending = 0; this.terminal = false; this.tail = Promise.resolve();
    this.ownedResults = null; this.dialogCapability = null; this.dialogs = []; this.retiredDialogs = new Set();
    this.inputCapability = null; this.inputs = []; this.retiredInputs = new Set();
  }
  lock() { if (!this.terminal) { this.terminal = true; this.failed(); } }
  request(method, params) {
    this.pending++;
    const operation = this.tail.then(async () => {
      if (this.terminal || this.state?.kind === 'closed') throw new FormError('transport');
      // A modal that arrived after an intent was queued must stop that older
      // business intent too. Read-only reconciliation is still allowed.
      if ((this.dialogs.length || this.inputs.length) && (['application.open','application.openRecord','application.close','application.reference','application.recoverPosting','application.report','application.reportSetup','application.reportPage'].includes(method) ||
          method === 'application.form' && !['form.hello','form.snapshot'].includes(params.request?.method))) {
        const error = new FormError(this.inputs.length ? 'input_pending' : 'dialog_pending'); error.preDispatch = true; throw error;
      }
      if (this.state?.sessions.some(value => value.id === params?.session && value.blocked) &&
          (method === 'application.reference' || method === 'application.recoverPosting' ||
           method === 'application.form' && !['form.hello','form.snapshot'].includes(params.request?.method))) {
        const error = new FormError(this.inputs.some(d => d.owner === params.session) ? 'input_pending' : this.dialogs.some(d => d.owner === params.session) ? 'dialog_pending' : 'owned_child_open'); error.preDispatch = true; throw error;
      }
      if (method === 'application.report' && !validReportRequest(params,this.state) ||
          ['application.reportSetup','application.reportPage'].includes(method) && !validReportAction(method,params,this.state)) {
        const error=new FormError('unavailable'); error.preDispatch=true; throw error;
      }
      if (method === 'application.reference' && (!keys(params,['session','revision','action']) ||
          !Number.isInteger(params.revision) || params.revision < 0 || params.revision > 2147483647 ||
          !referenceAction(params.action,this.state,params.session))) {
        const error = new FormError('reference_refused'); error.preDispatch = true; throw error;
      }
      if (method === 'application.recoverPosting' && (!keys(params,['session','receipt']) || !opaque(params.receipt) ||
          !this.state?.posting?.some(item => item.session === params.session && item.receipt === params.receipt && ['uncertain','committed'].includes(item.state)))) {
        const error = new FormError('unavailable'); error.preDispatch = true; throw error;
      }
      if (method === 'application.answerDialog' && (!keys(params,['session','ticket','answer']) ||
          !this.dialogs.some(d => d.owner === params.session && d.ticket === params.ticket && d.choices.includes(params.answer)))) {
        const error = new FormError('dialog_refused'); error.preDispatch = true; throw error;
      }
      if (method === 'application.answerInput' && !validInputAnswer(params,this.inputs)) {
        const error = new FormError('input_refused'); error.preDispatch = true; throw error;
      }
      const request = {jsonrpc:'2.0',id:++this.id,method,params}; let result;
      try {
        if (!Number.isSafeInteger(this.id)) throw new FormError('transport');
        result = validateApplicationReply(await this.exchange(request),request,this.state);
        const negotiated = Object.hasOwn(result,'dialogCapability');
        if (method === 'application.hello' && negotiated !== (params?.dialogCapability === DIALOG_CAPABILITY) ||
            this.dialogCapability !== null && this.dialogCapability !== negotiated) throw new FormError('transport');
        const nextDialogs = result.dialogs || [];
        for (const dialog of nextDialogs) {
          const previous = this.dialogs.find(d => d.ticket === dialog.ticket);
          if (this.retiredDialogs.has(dialog.ticket) || previous && ['owner','kind','title','text','choices'].some(key => JSON.stringify(previous[key]) !== JSON.stringify(dialog[key]))) throw new FormError('transport');
        }
        for (const dialog of this.dialogs) if (!nextDialogs.some(d => d.ticket === dialog.ticket)) this.retiredDialogs.add(dialog.ticket);
        if (this.retiredDialogs.size > 256) throw new FormError('transport');
        const inputNegotiated = Object.hasOwn(result,'inputCapability');
        if (method === 'application.hello' && inputNegotiated !== (params?.inputCapability === INPUT_CAPABILITY) ||
            this.inputCapability !== null && this.inputCapability !== inputNegotiated) throw new FormError('transport');
        const nextInputs = result.inputs || [];
        for (const input of nextInputs) {
          const previous = this.inputs.find(value => value.ticket === input.ticket);
          if (this.retiredInputs.has(input.ticket) || previous && JSON.stringify(previous) !== JSON.stringify(input)) throw new FormError('transport');
        }
        for (const input of this.inputs) if (!nextInputs.some(value => value.ticket === input.ticket)) this.retiredInputs.add(input.ticket);
        if (this.retiredInputs.size > 256) throw new FormError('transport');
        const owned = Object.hasOwn(result,'updates');
        if (this.ownedResults !== null && this.ownedResults !== owned) throw new FormError('transport');
        if (result.state.catalog) {
          const {entry,version} = result.state.catalog;
          if (version < (this.catalogVersions.get(entry) ?? 0)) throw new FormError('transport');
          this.catalogVersions.set(entry,version);
        }
        for (const session of result.state.sessions) if (this.retired.has(session.id)) throw new FormError('transport');
        for (const session of this.state?.sessions || []) if (!result.state.sessions.some(value => value.id === session.id)) this.retired.add(session.id);
        if (result.form !== null) {
          const revision = result.form.result.state.revision;
          if (revision < (this.formRevisions.get(result.session) ?? 0)) throw new FormError('transport');
          this.formRevisions.set(result.session,revision);
        }
        for (const update of result.updates || []) {
          const revision = update.form.result.state.revision;
          if (this.retired.has(update.session) || revision < (this.formRevisions.get(update.session) ?? 0)) throw new FormError('transport');
          this.formRevisions.set(update.session,revision);
        }
        this.ownedResults = owned; this.dialogCapability = negotiated; this.dialogs = nextDialogs; this.inputCapability = inputNegotiated; this.inputs = nextInputs;
      } catch (error) { if (error?.preDispatch === true) throw error; this.lock(); throw new FormError('transport'); }
      this.state = result.state;
      if (this.state.uncertain) { this.lock(); throw new FormError('transport'); }
      this.changed(result,request); return result;
    });
    this.tail = operation.catch(() => {});
    return operation.finally(() => { this.pending--; });
  }
  async reference(session, revision, action) {
    const result = await this.request('application.reference',{session,revision,action});
    if (!result.form) { this.lock(); throw new FormError('transport'); }
    return result.form;
  }
  async form(session, request) {
    const result = await this.request('application.form',{session,request});
    // A queued child opening can fail while the originating form event has a
    // valid authoritative reply. Keep that parent snapshot; never replay it.
    if (!result.form) { this.lock(); throw new FormError('transport'); }
    return result.form;
  }
}
