import {FormError, validateScalar, validateSnapshot, typedInput, scalarEqual, scalarText} from '../../form/src/client.mjs';

export const INPUT_CAPABILITY = 'yadinassi-owned-input/1';
const keys = (v,names) => v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).sort().join() === [...names].sort().join();
const token = v => typeof v === 'string' && /^[0-9a-f]{32}$/.test(v);
const text = (v,max) => typeof v === 'string' && [...v].length <= max &&
  !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v) && !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(v);
const scalar = value => {
  validateScalar(value);
  if (!['String','Number','Boolean','Date'].includes(value.type)) throw new FormError('transport');
};
/** Reuse the closed form scalar editor contract, without adding a real control. */
export function inputField(input) {
  scalar(input.value);
  const boolean = input.value.type === 'Boolean';
  if (boolean && (!keys(input.editor,['kind']) || input.editor.kind !== 'boolean')) throw new FormError('transport');
  const field = {name:'Input',kind:'field',title:'Value',visible:true,enabled:true,readOnly:false,
    view:boolean ? 'checkbox' : 'input',value:input.value,...(boolean ? {} : {editor:input.editor})};
  validateSnapshot({kind:'form',revision:0,lifecycle:'open',title:'Input',uncertain:false,items:[field],messages:[]});
  return field;
}
export function validateInputs(result, sessions, dialogOwners, dialogTickets) {
  const owners = new Set(), tickets = new Set();
  if (result.inputCapability !== INPUT_CAPABILITY || !Array.isArray(result.inputs) || result.inputs.length > 8 ||
      !Object.hasOwn(result,'updates') && result.inputs.length) throw new FormError('transport');
  for (const input of result.inputs) {
    const fields = input?.kind === 'input' ? ['ticket','owner','kind','title','text','value','editor']
      : ['ticket','owner','kind','title','choices','initial'];
    if (!keys(input,fields) || !['input','choice'].includes(input.kind) || !token(input.ticket) ||
        tickets.has(input.ticket) || dialogTickets.has(input.ticket) || !sessions.has(input.owner) ||
        owners.has(input.owner) || dialogOwners.has(input.owner) || !text(input.title,256) ||
        result.state.choice?.session === input.owner || result.state.entries.find(e => e.id === result.state.sessions.find(s => s.id === input.owner).entry).kind === 'posting-document') throw new FormError('transport');
    if (input.kind === 'input') {
      if (!text(input.text,4096)) throw new FormError('transport');
      inputField(input);
    } else {
      if (!Array.isArray(input.choices) || input.choices.length > 128 ||
          new TextEncoder().encode(JSON.stringify({choices:input.choices})).length > 32768) throw new FormError('transport');
      const choices = new Set();
      for (const row of input.choices) {
        if (!keys(row,['choice','value','presentation']) || !token(row.choice) || choices.has(row.choice) || !text(row.presentation,1024)) throw new FormError('transport');
        scalar(row.value); choices.add(row.choice);
      }
      if (input.initial !== null && !choices.has(input.initial)) throw new FormError('transport');
    }
    owners.add(input.owner); tickets.add(input.ticket);
  }
  return owners;
}
export function validInputAnswer(params, inputs) {
  const input = inputs.find(value => value.owner === params?.session && value.ticket === params?.ticket);
  if (!input) return false;
  if (params.action === 'cancel') return keys(params,['session','ticket','action']);
  if (params.action === 'choose') return input.kind === 'choice' && keys(params,['session','ticket','action','choice']) && input.choices.some(row => row.choice === params.choice);
  if (params.action !== 'accept' || input.kind !== 'input' || !keys(params,['session','ticket','action','value'])) return false;
  try {
    scalar(params.value);
    const field = inputField(input);
    if (params.value.type !== input.value.type) return false;
    // Reuse qualifier parsing for strings/numbers/booleans. Dates are checked
    // by the same editor validation without a timezone-dependent conversion.
    if (params.value.type === 'Date') { inputField({...input,value:params.value}); return scalarEqual(typedInput(field,scalarText(params.value,input.editor)),params.value); }
    return scalarEqual(typedInput(field,params.value.value),params.value);
  } catch { return false; }
}
