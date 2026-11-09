/** Dependency-free, deliberately closed module bundler for these three authored files. */
import {mkdir, readFile, writeFile, copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(root, '../../yadinassi/ui/assets/form');
await mkdir(target, {recursive: true});
const modules = [
  ['client', ['PROTOCOL', 'LIMITS', 'ERROR_MESSAGES', 'FormError', 'decimalText', 'validateScalar',
    'validateSnapshot', 'scalarText', 'editable', 'tableCell', 'typedInput', 'scalarEqual', 'FormClient',
    'readBoundedJSON', 'createTransport', 'takeSessionCapability']],
  ['view', ['createFormView']], ['app', ['mountForm']],
];
let bundle = '/* Yadinassi optional form renderer. MIT license: LICENSE.txt. Built from frontend/form. */\n';
for (const [name, exports] of modules) {
  let source = await readFile(path.join(root, 'src', name + '.mjs'), 'utf8');
  const found = [...source.matchAll(/^export (?:async )?(?:function|class|const) ([A-Za-z0-9_]+)/gm)].map(match => match[1]);
  if (JSON.stringify(found) !== JSON.stringify(exports)) throw Error('Update the closed export map for ' + name);
  source = source.replace(/^import \{([^}]+)\} from '\.\/(client|view)\.mjs';\n/gm,
    (_, names, dependency) => 'const {' + names + '} = __' + dependency + ';\n');
  source = source.replace(/^export /gm, '');
  if (/^\s*(?:import|export)\s/m.test(source)) throw Error('Unsupported module syntax in ' + name);
  bundle += 'const __' + name + ' = (() => {\n' + source + '\nreturn {' + exports.join(', ') + '};\n})();\n';
}
await writeFile(path.join(target, 'app.js'), bundle);
for (const name of ['index.html', 'style.css']) await copyFile(path.join(root, 'src', name), path.join(target, name));
await copyFile(path.join(root, 'LICENSE.txt'), path.join(target, 'LICENSE.txt'));
const sources = {}, outputs = {};
for (const name of ['package.json', 'build.mjs', 'LICENSE.txt', 'src/client.mjs', 'src/view.mjs', 'src/app.mjs', 'src/index.html', 'src/style.css'])
  sources[name] = createHash('sha256').update(await readFile(path.join(root, name))).digest('hex');
for (const name of ['app.js', 'index.html', 'style.css', 'LICENSE.txt'])
  outputs[name] = createHash('sha256').update(await readFile(path.join(target, name))).digest('hex');
await writeFile(path.join(target, 'build-manifest.json'), JSON.stringify({schema: 'yadinassi-form-assets/0', dependencies: {}, sources, outputs}, null, 2) + '\n');
