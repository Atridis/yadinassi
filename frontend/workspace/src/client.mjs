import {FormError, validateScalar, validateSnapshot, PROTOCOL as FORM_PROTOCOL} from '../../form/src/client.mjs';

export const WORKSPACE_PROTOCOL = 'yadinassi-orders-workspace/1';
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join() === [...expected].sort().join();
const integer = value => Number.isSafeInteger(value) && value >= 0;
const text = (value, max) => typeof value === 'string' && value.length <= max;
const sessionId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
export function validateWorkspaceReply(reply, request, previous) {
  if (!keys(reply, ['jsonrpc','id','result']) || reply.jsonrpc !== '2.0' || reply.id !== request.id) throw new FormError('transport');
  const result = reply.result, state = result?.state;
  if (!keys(result, ['protocol','state','error','session','form']) || result.protocol !== WORKSPACE_PROTOCOL ||
      !(result.error === null || text(result.error, 128)) || !(result.session === null || sessionId(result.session)) ||
      !keys(state, ['kind','revision','orders','truncated','sessions','uncertain']) ||
      !['workspace','closed'].includes(state.kind) || !integer(state.revision) || previous && state.revision < previous.revision ||
      typeof state.truncated !== 'boolean' || typeof state.uncertain !== 'boolean' ||
      !Array.isArray(state.orders) || state.orders.length > 32 || !Array.isArray(state.sessions) || state.sessions.length > 4) throw new FormError('transport');
  const rows = new Set(), sessions = new Set();
  for (const order of state.orders) {
    if (!keys(order, ['id','code','description','total']) || !integer(order.id) || !order.id || rows.has(order.id) ||
        !text(order.code, 8) || !text(order.description, 64) || order.total?.type !== 'Number') throw new FormError('transport');
    validateScalar(order.total); rows.add(order.id);
  }
  for (const session of state.sessions) {
    if (!keys(session,['id','kind']) || !sessionId(session.id) || sessions.has(session.id) || !['intake','editor'].includes(session.kind)) throw new FormError('transport');
    sessions.add(session.id);
  }
  if (request.method === 'workspace.form') {
    if (result.session !== request.params.session) throw new FormError('transport');
    const nested = result.form;
    if (result.error === null || nested !== null) {
      if (!keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || nested.id !== request.params.request.id ||
          !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL ||
          !(nested.result.error === null || ['invalid_request','stale_revision','event_failed','closed','outcome_unknown','busy','request_limit'].includes(nested.result.error))) throw new FormError('transport');
      validateSnapshot(nested.result.state);
      if ((nested.result.state.kind === 'closed') === sessions.has(result.session)) throw new FormError('transport');
    }
  } else if (request.method === 'workspace.open' && result.form !== null) {
    const nested = result.form;
    if (!keys(nested,['jsonrpc','id','result']) || nested.jsonrpc !== '2.0' || !integer(nested.id) ||
        !keys(nested.result,['protocol','state','error']) || nested.result.protocol !== FORM_PROTOCOL || nested.result.error !== null) throw new FormError('transport');
    validateSnapshot(nested.result.state);
  } else if (result.form !== null) throw new FormError('transport');
  if (request.method === 'workspace.open' && result.error === null && (!result.session || !sessions.has(result.session))) throw new FormError('transport');
  if (request.method === 'workspace.discard' && (result.session !== request.params.session || result.error === null && sessions.has(result.session))) throw new FormError('transport');
  if (state.kind === 'closed' && state.sessions.length) throw new FormError('transport');
  return result;
}
export class WorkspaceClient {
  constructor(exchange, changed = () => {}, failed = () => {}) {
    this.exchange = exchange; this.changed = changed; this.failed = failed; this.state = null;
    this.formRevisions = new Map(); this.id = 0; this.pending = 0; this.terminal = false; this.tail = Promise.resolve();
  }
  lock() { if (!this.terminal) { this.terminal = true; this.failed(); } }
  request(method, params) {
    this.pending++;
    const operation = this.tail.then(async () => {
      if (this.terminal || this.state?.kind === 'closed') throw new FormError('transport');
      const request = {jsonrpc:'2.0', id:++this.id, method, params};
      let result;
      try {
        if (!Number.isSafeInteger(this.id)) throw new FormError('transport');
        result = validateWorkspaceReply(await this.exchange(request), request, this.state);
        if (result.form !== null) {
          const revision = result.form.result.state.revision;
          if (revision < (this.formRevisions.get(result.session) ?? 0)) throw new FormError('transport');
          this.formRevisions.set(result.session,revision);
        }
      } catch { this.lock(); throw new FormError('transport'); }
      this.state = result.state;
      if (this.state.uncertain) { this.lock(); throw new FormError('transport'); }
      this.changed(result);
      return result;
    });
    this.tail = operation.catch(() => {});
    return operation.finally(() => { this.pending--; });
  }
  async form(session, request) {
    const result = await this.request('workspace.form', {session,request});
    if (result.error !== null || !result.form) { this.lock(); throw new FormError('transport'); }
    return result.form;
  }
}
