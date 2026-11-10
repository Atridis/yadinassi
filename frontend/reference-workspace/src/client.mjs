import {FormError, validateScalar, validateSnapshot, LIMITS, PROTOCOL as FORM_PROTOCOL} from '../../form/src/client.mjs';

export const REFERENCE_PROTOCOL = 'yadinassi-reference-orders/1';
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === expected.length && expected.every(name => Object.hasOwn(value,name));
const integer = value => Number.isInteger(value) && value >= 0 && value <= LIMITS.counter;
const text = (value, max) => typeof value === 'string' && value.length <= max;
const sessionId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const invalid = () => { throw new FormError('transport'); };
function nestedReply(nested, id) {
  if (!keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || nested.id !== id ||
      !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL ||
      !(nested.result.error === null || ['invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit'].includes(nested.result.error))) invalid();
  validateSnapshot(nested.result.state);
}
export function validateReferenceReply(reply, request, previous) {
  if (!keys(reply,['jsonrpc','id','result']) || reply.jsonrpc !== '2.0' || reply.id !== request.id) invalid();
  const result = reply.result, state = result?.state;
  if (!keys(result,['protocol','state','error','session','form']) || result.protocol !== REFERENCE_PROTOCOL ||
      !(result.error === null || text(result.error,128)) || !(result.session === null || sessionId(result.session)) ||
      !keys(state,['kind','revision','orders','truncated','sessions','uncertain']) ||
      !['workspace','closed'].includes(state.kind) || !integer(state.revision) || previous && state.revision < previous.revision ||
      typeof state.truncated !== 'boolean' || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.orders) || state.orders.length > 32 || !Array.isArray(state.sessions) || state.sessions.length > 2) invalid();
  const rows = new Set(), sessions = new Map();
  for (const row of state.orders) {
    if (!keys(row,['id','code','description','total']) || !integer(row.id) || !row.id || rows.has(row.id) ||
        !text(row.code,8) || !text(row.description,64) || row.total?.type !== 'Number') invalid();
    validateScalar(row.total); rows.add(row.id);
  }
  let order = null, choice = null;
  for (const session of state.sessions) {
    if (!keys(session,['id','kind','owner']) || !sessionId(session.id) || sessions.has(session.id)) invalid();
    if (session.kind === 'order' && session.owner === null && !order) order = session;
    else if (session.kind === 'choice' && sessionId(session.owner) && !choice) choice = session;
    else invalid();
    const prior = previous?.sessions.find(value => value.id === session.id);
    if (prior && (prior.kind !== session.kind || prior.owner !== session.owner)) invalid();
    sessions.set(session.id,session);
  }
  if (choice && choice.owner !== order?.id || state.kind === 'closed' && sessions.size) invalid();
  if (request.method === 'workspace.form') {
    if (result.session !== request.params.session) invalid();
    if (result.error === null || result.form !== null) {
      nestedReply(result.form,request.params.request.id);
      if ((result.form.result.state.kind === 'closed') === sessions.has(result.session)) invalid();
    }
  } else if (request.method === 'workspace.open') {
    if (result.error === null && (sessions.get(result.session)?.kind !== 'order' || !result.form)) invalid();
    if (result.form !== null) {
      nestedReply(result.form,1);
      if (result.form.result.error !== null || result.form.result.state.kind !== 'form' || sessions.get(result.session)?.kind !== 'order') invalid();
    }
  } else if (result.form !== null || result.session !== null) invalid();
  // Session changes must be attributable to this one authoritative operation.
  if (previous && !state.uncertain) {
    for (const prior of previous.sessions) if (!sessions.has(prior.id) &&
        !(request.method === 'workspace.form' && request.params.session === prior.id && result.form?.result.state.kind === 'closed')) invalid();
    for (const session of sessions.values()) if (!previous.sessions.some(prior => prior.id === session.id)) {
      if (session.kind === 'order' && !(request.method === 'workspace.open' && result.session === session.id && result.error === null)) invalid();
      if (session.kind === 'choice' && !(request.method === 'workspace.form' && request.params.session === session.owner &&
          request.params.request.method === 'form.event' && request.params.request.params.event === 'command' &&
          ['ChooseCustomerButton','ChooseProductButton'].includes(request.params.request.params.control))) invalid();
    }
  }
  return result;
}
export class ReferenceClient {
  constructor(exchange, changed = () => {}, failed = () => {}) {
    this.exchange = exchange; this.changed = changed; this.failed = failed; this.state = null;
    this.formRevisions = new Map(); this.issued = new Map(); this.id = 0; this.pending = 0; this.terminal = false; this.tail = Promise.resolve();
  }
  lock() { if (!this.terminal) { this.terminal = true; this.failed(); } }
  request(method, params) {
    this.pending++;
    const operation = this.tail.then(async () => {
      if (this.terminal || this.state?.kind === 'closed') throw new FormError('transport');
      const request = {jsonrpc:'2.0',id:++this.id,method,params};
      let result;
      try {
        if (!integer(this.id)) invalid();
        result = validateReferenceReply(await this.exchange(request),request,this.state);
        for (const session of result.state.sessions) {
          if (this.issued.has(session.id) && !this.state?.sessions.some(prior => prior.id === session.id)) invalid();
          if (!this.issued.has(session.id) && this.issued.size >= 256) invalid();
          this.issued.set(session.id,session);
        }
        if (result.form !== null) {
          const revision = result.form.result.state.revision;
          if (revision < (this.formRevisions.get(result.session) ?? 0)) invalid();
          this.formRevisions.set(result.session,revision);
        }
      } catch { this.lock(); throw new FormError('transport'); }
      this.state = result.state;
      if (this.state.uncertain || result.form?.result.state.uncertain || result.form?.result.error === 'outcome_unknown') {
        this.lock(); throw new FormError('transport');
      }
      this.changed(result);
      return result;
    });
    this.tail = operation.catch(() => {});
    return operation.finally(() => { this.pending--; });
  }
  async form(session, request) {
    const result = await this.request('workspace.form',{session,request});
    if (result.error !== null || !result.form) { this.lock(); throw new FormError('transport'); }
    return result.form;
  }
}
