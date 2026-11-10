import {REFERENCE_PROTOCOL} from '../src/client.mjs';
import {mountReferenceWorkspace} from '../src/app.mjs';
import {environment, all} from '../../form/test/fake-dom.mjs';
import {state, reply, field, button, table, column} from '../../form/test/fixtures.mjs';
export const workspace = (extra = {}) => ({kind:'workspace',revision:0,orders:[],truncated:false,sessions:[],uncertain:false,...extra});
export const response = (request, snapshot = workspace(), extra = {}) => ({jsonrpc:'2.0',id:request.id,result:{protocol:REFERENCE_PROTOCOL,state:snapshot,error:null,session:null,form:null,...extra}});
export const order = (id = 'o1') => ({id,kind:'order',owner:null});
export const choice = (id = 'c1', owner = 'o1') => ({id,kind:'choice',owner});
export const findInput = (entry,label) => all(entry.panel).find(node => node.tagName === 'INPUT' && node.getAttribute('aria-label') === label);
export const edit = (node,value) => { node.value = value; node.emit('input'); };
export const unload = env => {
  const event = {prevented:false,preventDefault(){this.prevented=true;}};
  env.listeners.get('beforeunload')(event); return event;
};
export const tick = () => new Promise(resolve => setImmediate(resolve));
export const ownerEntry = app => [...app.mounts.values()].find(entry => entry.kind === 'order');
export const childEntry = app => [...app.mounts.values()].find(entry => entry.kind === 'choice');

/** Protocol double only. Real catalog identity, persistence and recovery belong to Python/browser acceptance. */
export function host() {
  let snapshot = workspace(), next = 0, ownerRevision = 0, childRevision = 0;
  let quantity = '1.00', customer = '', product = '', dirty = false, selected = null;
  const requests = [], env = environment();
  const ownerState = () => state(ownerRevision, {title:'Order',dirty,discardCommands:['DiscardButton'],items:[
    field('FieldCode',{type:'String',value:'ORD00001'}),
    field('FieldCustomer',{type:'String',value:customer},{readOnly:true}),
    table({name:'LinesTable',title:'Order lines',columns:[column('Product','String',{readOnly:true}),column('Quantity','Number')],
      rows:[{id:1,values:[{type:'String',value:product},{type:'Number',value:quantity}]}],currentRow:selected}),
    ...['ChooseCustomerButton','ChooseProductButton','SaveOrderButton','DiscardButton'].map(button),
  ]});
  const childState = () => state(childRevision,{title:'Choose customer or product',items:[
    field('FieldSearchCode',{type:'String',value:''}),
    table({name:'ChoicesTable',title:'Choices',readOnly:true,columns:[column('Code','String',{readOnly:true}),column('Description','String',{readOnly:true})],
      rows:[{id:1,values:[{type:'String',value:'REF00001'},{type:'String',value:'Reference record'}]}],currentRow:1}),
    ...['SearchChoicesButton','ChooseButton','CancelButton'].map(button),
  ]});
  let target = 'customer';
  const exchange = async request => {
    requests.push(structuredClone(request));
    if (request.method === 'workspace.open') {
      const descriptor = order(`o${++next}`); ownerRevision = 0; dirty = false;
      snapshot = {...snapshot,revision:snapshot.revision+1,sessions:[descriptor]};
      return response(request,snapshot,{session:descriptor.id,form:reply({id:1},ownerState())});
    }
    if (request.method === 'workspace.close') snapshot = {...snapshot,kind:'closed',revision:snapshot.revision+1};
    if (request.method === 'workspace.list') snapshot = {...snapshot,revision:snapshot.revision+1};
    if (request.method !== 'workspace.form') return response(request,snapshot);
    const nested = request.params.request, descriptor = snapshot.sessions.find(value=>value.id===request.params.session);
    const {event,control} = nested.params;
    let form;
    if (descriptor.kind === 'order') {
      if (nested.method === 'form.event') {
        ownerRevision++;
        if (event === 'cell') { quantity = nested.params.value.value; dirty = true; }
        if (event === 'select') selected = nested.params.row;
        if (event === 'command' && ['ChooseCustomerButton','ChooseProductButton'].includes(control)) {
          target = control === 'ChooseCustomerButton' ? 'customer' : 'product'; childRevision = 0;
          snapshot = {...snapshot,revision:snapshot.revision+1,sessions:[descriptor,choice(`c${++next}`,descriptor.id)]};
        }
        if (event === 'command' && control === 'SaveOrderButton') dirty = false;
        if (event === 'command' && control === 'DiscardButton') { dirty = false; quantity = '1.00'; }
      }
      form = ownerState();
    } else {
      if (nested.method === 'form.event') childRevision++;
      form = childState();
    }
    if (event === 'close' || descriptor.kind === 'choice' && event === 'command' && ['ChooseButton','CancelButton'].includes(control)) {
      if (descriptor.kind === 'choice') {
        if (control === 'ChooseButton') { if (target === 'customer') customer='Chosen customer'; else product='Chosen product'; dirty=true; }
        ownerRevision++;
      }
      snapshot = {...snapshot,revision:snapshot.revision+1,sessions:snapshot.sessions.filter(value=>value.id!==descriptor.id)};
      form = {...form,kind:'closed',lifecycle:'closed',items:[],discardCommands:[]};
    }
    return response(request,snapshot,{session:descriptor.id,form:reply(nested,form)});
  };
  const app = mountReferenceWorkspace(env,env.document.root,exchange);
  return {app,env,requests,exchange};
}
