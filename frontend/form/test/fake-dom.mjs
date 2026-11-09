/** Small DOM contract double; no browser/parser dependency and no implicit HTML handling. */
export class FakeElement {
  constructor(document, tag) {
    this.ownerDocument = document; this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null;
    this.dataset = {}; this.attributes = new Map(); this.listeners = new Map(); this._text = '';
    this.value = ''; this.checked = false; this.hidden = false; this._disabled = false;
    this.selectionStart = 0; this.selectionEnd = 0; this.selectionDirection = 'none';
  }
  set textContent(value) { this._text = String(value); this.replaceChildren(); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(_) { throw Error('Untrusted HTML must never be parsed'); }
  get disabled() { return this._disabled; }
  set disabled(value) {
    this._disabled = value;
    if (value && this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body;
  }
  append(...nodes) { for (const node of nodes) this.insertBefore(node, null); }
  insertBefore(node, before) {
    if (node.parentNode) node.remove();
    const index = before === null ? this.children.length : this.children.indexOf(before);
    this.children.splice(index, 0, node); node.parentNode = this;
  }
  replaceChildren(...nodes) { for (const child of [...this.children]) child.remove(); this.append(...nodes); }
  remove() {
    if (this.contains(this.ownerDocument.activeElement)) this.ownerDocument.activeElement = this.ownerDocument.body;
    if (this.parentNode) this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1);
    this.parentNode = null;
  }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  closest(selector) {
    if (selector === '[hidden]' && this.hidden || selector === '[data-form-action]' && this.dataset.formAction) return this;
    return this.parentNode?.closest(selector) || null;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  addEventListener(name, callback) { const list = this.listeners.get(name) || []; list.push(callback); this.listeners.set(name, list); }
  emit(name, values = {}) {
    const event = {target: this, preventDefault() {}, ...values};
    for (const callback of this.listeners.get(name) || []) callback(event);
    if (values.bubbles && this.parentNode) this.parentNode.emit(name, event);
  }
  focus() { if (!this.disabled && !this.closest('[hidden]')) this.ownerDocument.activeElement = this; }
  setSelectionRange(start, end, direction) { this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction; }
}
export class FakeDocument {
  constructor() { this.body = new FakeElement(this, 'body'); this.activeElement = this.body; this.root = this.createElement('div'); this.body.append(this.root); }
  createElement(tag) { return new FakeElement(this, tag); }
  getElementById(id) { return all(this.body).find(node => node.id === id) || null; }
}
export const all = root => [root, ...root.children.flatMap(all)];
export const input = document => all(document.root).find(node => node.tagName === 'INPUT');
export const buttons = document => all(document.root).filter(node => node.tagName === 'BUTTON');
export function environment(fetcher) {
  const document = new FakeDocument(), listeners = new Map(), historyCalls = [];
  return {document, fetch: fetcher, location: {hash: '#session=' + 'a'.repeat(43), pathname: '/'},
    history: {replaceState(...values) { historyCalls.push(values); }}, historyCalls,
    addEventListener(name, callback) { listeners.set(name, callback); }, listeners};
}
