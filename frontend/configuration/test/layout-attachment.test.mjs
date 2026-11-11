import test from 'node:test';
import assert from 'node:assert/strict';
import {mountApplication} from '../src/app.mjs';
import {APPLICATION_PROTOCOL} from '../src/client.mjs';
import {validateSnapshot} from '../../form/src/client.mjs';
import {BROWSER_PROTOCOL} from '../../form/src/attachment.mjs';
import {environment,all} from '../../form/test/fake-dom.mjs';
import {reply,response,pageLayout} from '../../form/test/fixtures.mjs';

const issued={protocol:BROWSER_PROTOCOL,attachment:'attachment-1',role:'writer',generation:1,leaseSeconds:90,graceSeconds:30,
  recovery:false,closed:false,credential:'c'.repeat(43),resume:'r'.repeat(43)};
const initial=()=>({kind:'application',lifecycle:'forms',messages:[],exitWarning:'',title:'Layouts',
  entries:[{id:1,title:'Layout',kind:'form'}],sessions:[],active:null,uncertain:false,catalog:null});

test('real attachment wrapper permits locked layout inspection but no outer Open Close edits commands or replay',async()=>{
  let state=initial();const requests=[];const form=pageLayout();validateSnapshot(form);
  const env=environment(async(path,options)=>{
    const request=JSON.parse(options.body);requests.push({path,request});
    if(path==='/attachment')return response(issued);
    const result={protocol:APPLICATION_PROTOCOL,state,error:null,session:null,form:null};
    if(request.method==='application.open'){
      state={...state,active:'form-1',sessions:[{id:'form-1',entry:1,title:'Layout'}]};
      Object.assign(result,{state,session:'form-1',form:reply({id:1},form)});
    }else if(request.method==='application.form'){
      const nested=request.params.request;
      if(nested.params.event==='change')throw Error('lost completed reply');
      Object.assign(result,{session:'form-1',form:reply(nested,form)});
    }
    return response({jsonrpc:'2.0',id:request.id,result});
  });
  env.location.hash='#session='+'l'.repeat(43)+'&attachment=1';env.crypto={getRandomValues(bytes){bytes.fill(7);return bytes;}};
  const storage=new Map();env.sessionStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  env.setInterval=()=>1;env.clearInterval=()=>{};
  const app=mountApplication(env,env.document.root);await app.ready;await app.openForm(1);
  const entry=app.mounts.get('form-1');await entry.mount.ready;
  const input=name=>all(entry.panel).find(node=>node.tagName==='INPUT'&&node.getAttribute('aria-label')===name);
  const tab=name=>all(entry.panel).find(node=>node.getAttribute('role')==='tab'&&node.textContent===name);
  input('Name').value='uncertain';input('Name').emit('input');tab('Second').emit('click');
  input('Notes').value='  retained  ';input('Notes').emit('input');tab('First').emit('click');
  await entry.mount.run('change','Name');const count=requests.length;
  assert.equal(app.client.terminal,true);assert.equal(entry.mount.client.locked,true);
  assert.equal(app.browserHost.attachment.writable,false);assert.equal(app.browserHost.content.inert,false);
  assert.equal(app.browserHost.content.dataset.inspection,'true');assert.equal(app.browserHost.content.getAttribute('aria-disabled'),'false');
  tab('Second').emit('click');assert.equal(tab('Second').getAttribute('aria-selected'),'true');
  assert.equal(input('Notes').value,'  retained  ');assert.equal(input('Notes').disabled,true);
  assert.ok(entry.panel.textContent.includes('Notes:   retained  '));
  const nodes=all(env.document.root);
  const entries=nodes.find(node=>node.getAttribute('aria-label')==='Declared forms');
  assert.ok(entries.children.every(node=>node.disabled));
  const close=nodes.find(node=>node.tagName==='BUTTON'&&node.textContent==='Close application');assert.equal(close.disabled,true);
  close.emit('click');await app.openForm(1);await app.client.tail;
  await entry.mount.run('change','Notes');await entry.mount.run('command','SaveSecond');await entry.mount.run('close');await entry.mount.refresh();
  await assert.rejects(app.browserHost.transport({jsonrpc:'2.0',id:99,method:'application.close',params:{}}),{code:'not_writer'});
  assert.equal(requests.length,count);assert.equal(app.client.terminal,true);assert.equal(entry.mount.client.locked,true);
  app.client.pending=1;app.browserHost.notify();assert.equal(app.browserHost.content.inert,true);
  app.client.pending=0;app.client.state={...app.client.state,choice:{}};app.browserHost.notify();assert.equal(app.browserHost.content.inert,true);
  app.client.state={...app.client.state,choice:null};app.browserHost.notify();assert.equal(app.browserHost.content.inert,false);
  const {credential,resume,...publicStatus}=issued;app.browserHost.attachment.adopt({...publicStatus,generation:2});assert.equal(app.browserHost.content.inert,true);
  assert.equal(input('Notes').value,'  retained  ');assert.equal(requests.length,count);app.browserHost.attachment.dispose();
});
