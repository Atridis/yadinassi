/** Закрытые pure helpers только для единого демо; общий launcher не расширяется. */
export function mainDemoLaunchURL(value) {
  if(typeof value!=='string'||!/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}\/#session=[A-Za-z0-9_-]{43}&attachment=1$/.test(value))throw Error('invalid_launch_url');
  const url=new URL(value);if(Number(url.port)>65535)throw Error('invalid_launch_url');return url;
}
export function mainDemoLaunchOutputReader(){
  let buffered='',settled=false;
  return chunk=>{
    if(settled)return null;
    if(!Buffer.isBuffer(chunk)||Buffer.byteLength(buffered)+chunk.length>4096){settled=true;buffered='';throw Error('host_output_budget');}
    buffered+=chunk.toString();
    const match=buffered.match(/^http:\/\/127\.0\.0\.1:[0-9]+\/#session=[A-Za-z0-9_-]{43}&attachment=1(?=\r?\n)/m);
    if(!match)return null;
    settled=true;buffered='';return mainDemoLaunchURL(match[0]);
  };
}
export function mainDemoAllowedRequest(value,origin){
  try{
    const url=new URL(value),base=new URL(origin);
    return base.protocol==='http:'&&base.hostname==='127.0.0.1'&&base.origin===origin&&
      url.origin===origin&&!url.username&&!url.password&&!url.search&&
      ['/', '/app.js','/style.css','/catalog.js','/configuration.js','/catalog.css','/configuration.css','/rpc','/attachment','/favicon.ico'].includes(url.pathname);
  }catch{return false;}
}

export function verifyMainDemoAudit(saved,assert){
  const named=(fields,values)=>{
    assert.equal(fields.length,values.length,'audit_field_count');
    return Object.fromEntries(fields.map((field,index)=>[field.name,values[index]]));
  };
  const section=(schema,card,name)=>{
    const declaration=schema.tabular_sections.find(s=>s.name===name);assert.ok(declaration,'audit_section_schema');
    const stored=card.tabular_sections.find(s=>s.section_id===declaration.identity);assert.ok(stored,'audit_section_values');
    assert.equal(stored.rows.length,1,'audit_single_line');return named(declaration.fields,stored.rows[0].values);
  };
  assert.equal(saved.readOnlyAudit,true);
  assert.equal(saved.catalogs['ВидыНоменклатуры'].length,1);assert.equal(saved.catalogs['Номенклатура'].length,1);
  const kind=saved.catalogs['ВидыНоменклатуры'][0],product=saved.catalogs['Номенклатура'][0];
  const warehouse=code=>{const rows=saved.catalogs['Склады'].filter(r=>r.code===code);assert.equal(rows.length,1);return rows[0].key;};
  const productValues=named(saved.catalogSchemas['Номенклатура'].fields,product.values);
  assert.deepEqual(productValues['ВидНоменклатуры'],kind.key,'audit_product_kind');
  assert.deepEqual(section(saved.catalogSchemas['Номенклатура'],product,'Склады')['Склад'],warehouse('W069'),'audit_product_section');
  assert.equal(saved.documents.Receipt.length,1);assert.equal(saved.documents.Issue.length,0);
  const receipt=saved.documents.Receipt[0],schema=saved.documentSchemas.Receipt;
  assert.equal(receipt.number,'RQA1');assert.equal(receipt.posted,true);assert.equal(receipt.deletion_mark,false);
  assert.deepEqual(named(schema.fields,receipt.values).Warehouse,warehouse('W000'),'audit_receipt_warehouse');
  const line=section(schema,receipt,'Lines');
  assert.deepEqual(line.Product,product.key,'audit_line_product');
  assert.equal(Number(line.Quantity),3,'audit_line_quantity');assert.equal(Number(line.Amount),123,'audit_line_amount');
  assert.equal(saved.movementRows.length,1);const movement=saved.movementRows[0],stock=saved.registerSchemas.Stock;
  assert.equal(movement[0],stock.identity);assert.equal(movement[1],receipt.key.document_id);assert.equal(movement[2],receipt.key.record_id);
  assert.equal(movement[3],1);assert.equal(movement[5],1);assert.equal(movement[6],'receipt');
  const encoded=JSON.parse(movement[7]);assert.equal(encoded.length,3);
  const dimensions=named(stock.dimensions,encoded[0]),resources=named(stock.resources,encoded[1]);
  const ref=key=>['r',key.catalog_id,key.record_id];
  assert.deepEqual(dimensions.Product,ref(product.key),'audit_movement_product');
  assert.deepEqual(dimensions.Warehouse,ref(warehouse('W000')),'audit_movement_warehouse');
  for(const [name,expected] of [['Quantity',3],['Amount',123]]){
    assert.equal(resources[name][0],'n');assert.equal(Number(resources[name][1]),expected,'audit_movement_'+name);
  }
}
