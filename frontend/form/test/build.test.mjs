import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root = new URL('../', import.meta.url), target = new URL('../../yadinassi/ui/assets/form/', root);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

test('packaged form assets match every authored source and output hash', async () => {
  const manifest = JSON.parse(await readFile(new URL('build-manifest.json', target), 'utf8'));
  assert.equal(manifest.schema, 'yadinassi-form-assets/0'); assert.deepEqual(manifest.dependencies, {});
  for (const [name, expected] of Object.entries(manifest.sources)) assert.equal(sha(await readFile(new URL(name, root))), expected, name);
  for (const [name, expected] of Object.entries(manifest.outputs)) assert.equal(sha(await readFile(new URL(name, target))), expected, name);
});

test('bundle is self-contained and package has only the five closed static assets', async () => {
  assert.deepEqual((await readdir(target)).sort(), ['LICENSE.txt', 'app.js', 'build-manifest.json', 'index.html', 'style.css'].sort());
  const bundle = await readFile(new URL('app.js', target), 'utf8');
  assert.equal(/^\s*(?:import|export)\s/m.test(bundle), false);
  assert.equal(/(?:localStorage|sessionStorage|innerHTML|eval\(|new Function)/.test(bundle), false);
  const html = await readFile(new URL('index.html', target), 'utf8');
  assert.ok(html.includes('type="module" src="/app.js"')); assert.equal(/https?:\/\//.test(html), false);
});
