import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url), target=new URL('../../yadinassi/ui/assets/reference-workspace/',root);

test('reference manifest has the exact schema, closed source inventory and current hashes', async () => {
  const manifest=JSON.parse(await readFile(new URL('build-manifest.json',target),'utf8'));
  assert.equal(manifest.schema,'yadinassi-reference-workspace-assets/0'); assert.deepEqual(manifest.dependencies,{});
  assert.deepEqual(Object.keys(manifest.sources).sort(),['package.json','build.mjs','src/index.html','src/style.css','src/client.mjs','src/app.mjs',
    '../form/src/attachment.mjs','../form/src/client.mjs','../form/src/view.mjs','../form/src/app.mjs','../form/src/style.css','../form/LICENSE.txt'].sort());
  assert.deepEqual(Object.keys(manifest.outputs).sort(),['app.js','index.html','style.css','LICENSE.txt'].sort());
  for (const [name,hash] of Object.entries(manifest.sources)) assert.equal(createHash('sha256').update(await readFile(new URL(name,root))).digest('hex'),hash,name);
  for (const [name,hash] of Object.entries(manifest.outputs)) assert.equal(createHash('sha256').update(await readFile(new URL(name,target))).digest('hex'),hash,name);
});

test('reference bundle has exactly five local assets and no dynamic scripts or unsafe HTML', async () => {
  assert.deepEqual((await readdir(target)).sort(),['LICENSE.txt','app.js','build-manifest.json','index.html','style.css'].sort());
  const bundle=await readFile(new URL('app.js',target),'utf8');
  assert.equal(/^\s*(?:import|export)\s/m.test(bundle),false);
  assert.equal(/(?:localStorage|innerHTML|eval\(|new Function)/.test(bundle),false);
  assert.ok(bundle.includes('sessionStorage.setItem(RESUME_KEY, value.resume)'));
  const html=await readFile(new URL('index.html',target),'utf8');
  assert.ok(html.includes('id="reference-orders-app"')); assert.ok(html.includes('type="module" src="/app.js"')); assert.equal(/https?:\/\//.test(html),false);
});
