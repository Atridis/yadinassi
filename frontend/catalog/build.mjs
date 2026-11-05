import {build} from 'esbuild';
import {mkdir, readFile, writeFile, copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.dirname(fileURLToPath(import.meta.url));
const target=path.resolve(root,'../../yadinassi/ui/assets/catalog');
await mkdir(target,{recursive:true});
await build({entryPoints:[path.join(root,'src/app.jsx')],outfile:path.join(target,'app.js'),
  bundle:true,minify:true,format:'esm',platform:'browser',target:['es2020'],jsxFactory:'h',jsxFragment:'Fragment',
  legalComments:'eof',banner:{js:'/* Yadinassi optional catalog renderer. Preact MIT license: LICENSE.txt. Built from frontend/catalog. */'}});
for (const name of ['index.html','style.css']) await copyFile(path.join(root,'src',name),path.join(target,name));
await copyFile(path.join(root,'PREACT-LICENSE.txt'),path.join(target,'LICENSE.txt'));
const files=['package.json','package-lock.json','build.mjs','src/app.jsx','src/client.mjs','src/presentation.mjs','src/index.html','src/style.css'];
const hashes={};
for (const name of files) hashes[name]=createHash('sha256').update(await readFile(path.join(root,name))).digest('hex');
const outputs={};
for (const name of ['app.js','index.html','style.css','LICENSE.txt']) outputs[name]=createHash('sha256').update(await readFile(path.join(target,name))).digest('hex');
await writeFile(path.join(target,'build-manifest.json'),JSON.stringify({schema:'yadinassi-catalog-assets/0',
  dependencies:{preact:'11.1.1',esbuild:'0.28.2'},sources:hashes,outputs},null,2)+'\n');
