/** Closed, dependency-free deterministic configuration bundle. */
import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(root,'../../yadinassi/ui/assets/configuration');
await mkdir(target,{recursive:true});
const modules = [
  ['formClient','../form/src/client.mjs',['PROTOCOL','LIMITS','ERROR_MESSAGES','FormError','decimalText','validateScalar','validateSnapshot','scalarText','editable','tableCell','typedInput','scalarEqual','FormClient','readBoundedJSON','createTransport','takeSessionCapability']],
  ['formView','../form/src/view.mjs',['createFormView']],
  ['formApp','../form/src/app.mjs',['mountForm']],
  ['configurationClient','src/client.mjs',['APPLICATION_PROTOCOL','validateApplicationReply','ApplicationClient']],
  ['configurationApp','src/app.mjs',['mountApplication']],
];
let bundle = '/* Yadinassi Configuration forms. MIT license: LICENSE.txt. */\n';
for (const [name,file,exports] of modules) {
  let source = await readFile(path.join(root,file),'utf8');
  const found = [...source.matchAll(/^export (?:async )?(?:function|class|const) ([A-Za-z0-9_]+)/gm)].map(match => match[1]);
  if (JSON.stringify(found) !== JSON.stringify(exports)) throw Error('Update closed export map: '+name);
  source = source.replace(/^import \{([^}]+)\} from '([^']+)';\n/gm,(_,names,dependency) => {
    const resolved = path.resolve(root,path.dirname(file),dependency);
    const match = modules.find(([,candidate]) => path.resolve(root,candidate) === resolved);
    if (!match) throw Error('Unsupported dependency '+dependency);
    return 'const {'+names.replace(/\bas\b/g,':')+'} = __'+match[0]+';\n';
  }).replace(/^export /gm,'');
  if (/^\s*(?:import|export)\s/m.test(source)) throw Error('Unsupported syntax '+name);
  bundle += 'const __'+name+' = (() => {\n'+source+'\nreturn {'+exports.join(', ')+'};\n})();\n';
}
await writeFile(path.join(target,'app.js'),bundle);
await copyFile(path.join(root,'src/index.html'),path.join(target,'index.html'));
await writeFile(path.join(target,'style.css'),await readFile(path.join(root,'../form/src/style.css'),'utf8')+'\n'+await readFile(path.join(root,'src/style.css'),'utf8'));
await copyFile(path.join(root,'../form/LICENSE.txt'),path.join(target,'LICENSE.txt'));
const sources = {},outputs = {};
for (const name of ['package.json','build.mjs','src/index.html','src/style.css','../form/src/style.css','../form/LICENSE.txt',...modules.map(([,file])=>file)]) sources[name] = createHash('sha256').update(await readFile(path.join(root,name))).digest('hex');
for (const name of ['app.js','index.html','style.css','LICENSE.txt']) outputs[name] = createHash('sha256').update(await readFile(path.join(target,name))).digest('hex');
await writeFile(path.join(target,'build-manifest.json'),JSON.stringify({schema:'yadinassi-configuration-assets/0',dependencies:{},sources,outputs},null,2)+'\n');
