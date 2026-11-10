import {FormError, validateSnapshot, PROTOCOL as FORM_PROTOCOL} from '../../form/src/client.mjs';

export const APPLICATION_PROTOCOL = 'yadinassi-configuration-app/2';
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join() === [...expected].sort().join();
const integer = value => Number.isSafeInteger(value) && value > 0;
const text = (value, max) => typeof value === 'string' && value.length <= max;
const sessionId = value => typeof value === 'string' && /^form-[1-9][0-9]{0,5}$/.test(value);
const recordKey = value => typeof value === 'string' && /^record-[1-9][0-9]{0,8}$/.test(value);
const errors = ['closed','outcome_unknown','capacity','open_failed','retired_session','forms_open',
  'catalog_unavailable','catalog_limit','invalid_record','object_required','save_recovery_required'];
export function validateApplicationReply(reply, request, previous) {
  if (!keys(reply,['jsonrpc','id','result']) || reply.jsonrpc !== '2.0' || reply.id !== request.id) throw new FormError('transport');
  const result = reply.result, state = result?.state;
  if (!keys(result,['protocol','state','error','session','form']) || result.protocol !== APPLICATION_PROTOCOL ||
      !(result.error === null || errors.includes(result.error)) || !(result.session === null || sessionId(result.session)) ||
      !keys(state,['kind','title','entries','sessions','active','uncertain','catalog']) || !['application','closed'].includes(state.kind) ||
      !text(state.title,1024) || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.entries) || !state.entries.length || state.entries.length > 64 ||
      !Array.isArray(state.sessions) || state.sessions.length > 8) throw new FormError('transport');
  const entries = new Set(), sessions = new Set();
  for (const entry of state.entries) {
    if (!keys(entry,['id','title','kind']) || !integer(entry.id) || entries.has(entry.id) || !text(entry.title,1024) ||
        !['form','catalog-object'].includes(entry.kind)) throw new FormError('transport');
    entries.add(entry.id);
  }
  if (previous && JSON.stringify(state.entries) !== JSON.stringify(previous.entries)) throw new FormError('transport');
  if (state.catalog !== null) {
    const catalog = state.catalog;
    if (!keys(catalog,['entry','version','rows']) || !state.entries.some(e => e.id === catalog.entry && e.kind === 'catalog-object') ||
        !Number.isSafeInteger(catalog.version) || catalog.version < 0 || catalog.version > 2147483647 ||
        !Array.isArray(catalog.rows) || catalog.rows.length > 256) throw new FormError('transport');
    const seen = new Set();
    for (const row of catalog.rows) {
      if (!keys(row,['key','code','description','deletionMark']) || !recordKey(row.key) || seen.has(row.key) ||
          !text(row.code,1024) || !text(row.description,1024) || typeof row.deletionMark !== 'boolean') throw new FormError('transport');
      seen.add(row.key);
    }
    if (previous?.catalog?.entry === catalog.entry && catalog.version < previous.catalog.version) throw new FormError('transport');
  }
  for (const session of state.sessions) {
    if (!keys(session,['id','entry','title']) || !sessionId(session.id) || sessions.has(session.id) ||
        !entries.has(session.entry) || !text(session.title,1024)) throw new FormError('transport');
    const old = previous?.sessions.find(value => value.id === session.id);
    if (old && old.entry !== session.entry) throw new FormError('transport');
    sessions.add(session.id);
  }
  if (!(state.active === null || sessions.has(state.active)) || state.kind === 'closed' && sessions.size) throw new FormError('transport');
  if (request.method === 'application.form' && result.session !== request.params.session) throw new FormError('transport');
  if (result.form !== null) {
    const nested = result.form;
    if (!['application.form','application.open','application.openRecord','application.hello'].includes(request.method) || !result.session ||
        !keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || !integer(nested.id) ||
        request.method === 'application.form' && nested.id !== request.params.request.id ||
        !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL ||
        !(nested.result.error === null || ['invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit'].includes(nested.result.error))) throw new FormError('transport');
    validateSnapshot(nested.result.state);
    if ((nested.result.state.kind === 'closed') === sessions.has(result.session)) throw new FormError('transport');
  } else if (request.method === 'application.form' && result.error === null) throw new FormError('transport');
  if (['application.open','application.openRecord'].includes(request.method) && result.error === null && !sessions.has(result.session)) throw new FormError('transport');
  return result;
}
export class ApplicationClient {
  constructor(exchange, changed = () => {}, failed = () => {}) {
    this.exchange = exchange; this.changed = changed; this.failed = failed; this.state = null;
    this.formRevisions = new Map(); this.catalogVersions = new Map(); this.retired = new Set(); this.id = 0; this.pending = 0; this.terminal = false; this.tail = Promise.resolve();
  }
  lock() { if (!this.terminal) { this.terminal = true; this.failed(); } }
  request(method, params) {
    this.pending++;
    const operation = this.tail.then(async () => {
      if (this.terminal || this.state?.kind === 'closed') throw new FormError('transport');
      const request = {jsonrpc:'2.0',id:++this.id,method,params}; let result;
      try {
        if (!Number.isSafeInteger(this.id)) throw new FormError('transport');
        result = validateApplicationReply(await this.exchange(request),request,this.state);
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
      } catch { this.lock(); throw new FormError('transport'); }
      this.state = result.state;
      if (this.state.uncertain) { this.lock(); throw new FormError('transport'); }
      this.changed(result,request); return result;
    });
    this.tail = operation.catch(() => {});
    return operation.finally(() => { this.pending--; });
  }
  async form(session, request) {
    const result = await this.request('application.form',{session,request});
    // A queued child opening can fail while the originating form event has a
    // valid authoritative reply. Keep that parent snapshot; never replay it.
    if (!result.form) { this.lock(); throw new FormError('transport'); }
    return result.form;
  }
}
