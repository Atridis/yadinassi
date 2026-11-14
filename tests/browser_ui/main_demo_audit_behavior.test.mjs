import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyMainDemoAudit} from './main_demo_browser_support.mjs';

const key=(catalog,id)=>({catalog_id:catalog,record_id:id});
function sample(){
 const kind=key('kinds','kind1'), product=key('products','product1');
 const warehouses=[{key:key('warehouses','w0'),code:'W000'},{key:key('warehouses','w69'),code:'W069'}];
 const fields=names=>names.map(name=>({name}));
 return {readOnlyAudit:true,
  catalogs:{'ВидыНоменклатуры':[{key:kind}], 'Номенклатура':[{key:product,values:[kind],tabular_sections:[{section_id:'ps',rows:[{values:[warehouses[1].key]}]}]}], 'Склады':warehouses},
  catalogSchemas:{'Номенклатура':{fields:fields(['ВидНоменклатуры']),tabular_sections:[{name:'Склады',identity:'ps',fields:fields(['Склад'])}]}},
  documents:{Receipt:[{key:{document_id:'receipts',record_id:'r1'},number:'RQA1',posted:true,deletion_mark:false,values:[warehouses[0].key],tabular_sections:[{section_id:'lines',rows:[{values:[product,'3','123']}]}]}],Issue:[]},
  documentSchemas:{Receipt:{fields:fields(['Warehouse']),tabular_sections:[{name:'Lines',identity:'lines',fields:fields(['Product','Quantity','Amount'])}]}},
  registerSchemas:{Stock:{identity:'stock',dimensions:fields(['Product','Warehouse']),resources:fields(['Quantity','Amount'])}},
  movementRows:[['stock','receipts','r1',1,'period',1,'receipt',JSON.stringify([[['r','products','product1'],['r','warehouses','w0']],[['n','3'],['n','123']],[]])]]};
}
test('audit validates actual typed references, values and recorder movement',()=>verifyMainDemoAudit(sample(),assert));
for(const [name,mutate] of Object.entries({
 readonly:s=>s.readOnlyAudit=false,
 missingKind:s=>s.catalogs['ВидыНоменклатуры']=[],
 kindReference:s=>s.catalogs['Номенклатура'][0].values[0]=key('kinds','wrong'),
 warehouseReference:s=>s.documents.Receipt[0].values[0]=key('warehouses','wrong'),
 productSection:s=>s.catalogs['Номенклатура'][0].tabular_sections[0].rows[0].values[0]=key('warehouses','wrong'),
 extraIssue:s=>s.documents.Issue.push({}),
 notPosted:s=>s.documents.Receipt[0].posted=false,
 productLine:s=>s.documents.Receipt[0].tabular_sections[0].rows[0].values[0]=key('products','wrong'),
 quantity:s=>s.documents.Receipt[0].tabular_sections[0].rows[0].values[1]='4',
 amount:s=>s.documents.Receipt[0].tabular_sections[0].rows[0].values[2]='124',
 recorder:s=>s.movementRows[0][2]='wrong',
 direction:s=>s.movementRows[0][6]='expense',
 inactive:s=>s.movementRows[0][5]=0,
 movementProduct:s=>{const v=JSON.parse(s.movementRows[0][7]);v[0][0][2]='wrong';s.movementRows[0][7]=JSON.stringify(v);},
 movementWarehouse:s=>{const v=JSON.parse(s.movementRows[0][7]);v[0][1][2]='wrong';s.movementRows[0][7]=JSON.stringify(v);},
 movementQuantity:s=>{const v=JSON.parse(s.movementRows[0][7]);v[1][0][1]='4';s.movementRows[0][7]=JSON.stringify(v);},
 movementAmount:s=>{const v=JSON.parse(s.movementRows[0][7]);v[1][1][1]='124';s.movementRows[0][7]=JSON.stringify(v);},
 extraMovement:s=>s.movementRows.push(s.movementRows[0]),
}))test(`audit rejects ${name} mutation`,()=>{const saved=sample();mutate(saved);assert.throws(()=>verifyMainDemoAudit(saved,assert));});
