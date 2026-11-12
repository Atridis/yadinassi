// Uses the existing catalog lockfile/toolchain; no additional dependencies.
import {createRequire} from 'node:module';
import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const require=createRequire(new URL('../catalog/package.json',import.meta.url));
const {build,version}=require('esbuild');
if(version!=='0.28.2')throw Error('Pinned esbuild required');
const root=path.dirname(fileURLToPath(import.meta.url)),target=path.resolve(root,'../../yadinassi/ui/assets/main-demo');
await mkdir(target,{recursive:true});
await build({entryPoints:[path.join(root,'src/app.mjs')],outfile:path.join(target,'app.js'),bundle:true,minify:true,format:'esm',platform:'browser',target:['es2020'],external:['/catalog.js','/configuration.js']});
for(const name of ['index.html','style.css'])await copyFile(path.join(root,'src',name),path.join(target,name));
await copyFile(path.join(root,'../form/LICENSE.txt'),path.join(target,'LICENSE.txt'));
const sources={},outputs={};
for(const name of ['build.mjs','src/app.mjs','src/client.mjs','src/index.html','src/style.css','../form/LICENSE.txt','../catalog/package.json','../catalog/package-lock.json','../form/src/attachment.mjs','../form/src/client.mjs'])sources[name]=createHash('sha256').update(await readFile(path.join(root,name))).digest('hex');
for(const name of ['app.js','index.html','style.css','LICENSE.txt'])outputs[name]=createHash('sha256').update(await readFile(path.join(target,name))).digest('hex');
await writeFile(path.join(target,'build-manifest.json'),JSON.stringify({schema:'yadinassi-main-demo-assets/0',dependencies:{esbuild:'0.28.2'},sources,outputs},null,2)+'\n');
