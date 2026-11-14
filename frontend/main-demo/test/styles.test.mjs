import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';
import {scopedStyles} from '../scoped-styles.mjs';
const read=p=>readFileSync(new URL(p,import.meta.url),'utf8');
test('closed scopes remap document palette and body to renderer root',()=>{
 const css=scopedStyles(':root{color:red}:root[data-theme="light"]{color:black}body{margin:0}@media(max-width:1px){body{padding:1px}}','.main-demo-catalog');
 assert.match(css,/^@scope \(\.main-demo-catalog\)/);assert.match(css,/:scope\[data-theme="light"\]/);assert.doesNotMatch(css,/:root|\bbody\b/);
 assert.throws(()=>scopedStyles('button{}','.other'));
});
test('global CSS registration and resources fail closed instead of leaking',()=>{
 for(const css of ['@import "other.css";','@font-face{font-family:X}','@keyframes spin{}','@property --x{}','@page{}','a{background:url(x)}',':host{color:red}',':global(button){}'])assert.throws(()=>scopedStyles(css,'.main-demo-documents'));
});
test('unsupported document selector combinations are rejected',()=>{
 for(const css of ['html body{margin:0}','body > main{padding:0}','html.dark{color:red}',':root body{color:red}'])assert.throws(()=>scopedStyles(css,'.main-demo-catalog'));
 assert.match(scopedStyles('html{font:inherit}body{margin:0}','.main-demo-documents'),/:scope\{font/);
});
test('main-demo contains only scoped renderer sheets and binds every source byte',()=>{
 const html=read('../src/index.html');assert.doesNotMatch(html,/href="\/(catalog|configuration)\.css"/);
 const manifest=JSON.parse(read('../../../yadinassi/ui/assets/main-demo/build-manifest.json'));
 for(const name of ['../catalog/src/style.css','../form/src/style.css','../configuration/src/style.css','scoped-styles.mjs']){
  const bytes=readFileSync(new URL('../'+name,import.meta.url));
  assert.equal(manifest.sources[name],createHash('sha256').update(bytes).digest('hex'));
 }
 const css=read('../../../yadinassi/ui/assets/main-demo/style.css');
 assert.match(css,/@scope \(\.main-demo-catalog\)/);assert.match(css,/@scope \(\.main-demo-documents\)/);
 assert.equal(Object.keys(manifest.outputs).length,4);
});
test('unsupported scope browser refuses before attachment or database activation',()=>{
 const app=read('../src/app.mjs');
 assert.ok(app.indexOf("typeof environment.CSSScopeRule!=='function'")<app.indexOf('const host=createBrowserHost'));
 assert.match(app,/unsupported:true,ready:Promise.resolve\(false\)/);
 assert.match(app,/content.className='main-demo-surface '\+\(client.state.surface/);
 assert.match(app,/mountedEpoch===client.state.epoch\)\{await mount.resume\(\);return;/);
});
test('embedded theme stays local and responsive rules do not depend on wrapper depth',()=>{
 const catalog=read('../../catalog/src/app.jsx'),css=read('../src/style.css');
 assert.match(catalog,/const themeTarget=exchange\?root:document.documentElement/);
 assert.match(catalog,/themeTarget.dataset.theme=resolvedTheme/);assert.doesNotMatch(catalog,/document.documentElement.dataset/);
 assert.doesNotMatch(css,/#main-demo-app>main/);assert.doesNotMatch(css,/overflow:clip/);assert.match(css,/@container demo-form/);
 assert.match(css,/\.main-demo-navigation\{display:flex;flex-wrap:wrap/);
 assert.match(css,/white-space:normal/);assert.match(css,/\.configuration-reports table\{min-width:850px\}/);
});
test('main demo owns one theme selector and service recovery without hiding errors',()=>{
 const shell=read('../src/app.mjs'),css=read('../src/style.css'),catalog=read('../../catalog/src/app.jsx');
 assert.match(shell,/services.append\(summary,themeLabel,retry\)/);
 assert.match(shell,/exchange.theme=\{get:\(\)=>theme,subscribe:/);
 assert.match(shell,/systemTheme.removeEventListener\('change',paintTheme\)/);
 assert.match(catalog,/exchange\?\.theme\?\.subscribe\(setTheme\)/);
 assert.match(css,/browser-ownership\[data-healthy="true"\]/);
 assert.doesNotMatch(css,/browser-ownership\s*\{display:none/);
});

test('dark table cells and readonly rows use the shared palette with matching specificity',()=>{
 const css=read('../src/style.css');
 assert.match(css,/\.cell-input:not\(\[type=checkbox\]\),\.cell-input\[readonly\]\{background:var\(--paper\);color:var\(--ink\)/);
 assert.match(css,/\.data-table thead th,\.table-toolbar,\.table-help\{background:var\(--paper\);color:var\(--muted\)/);
 assert.match(css,/\.data-table tbody tr:nth-child\(even\)\{background:var\(--canvas\)/);
 assert.match(css,/\.data-table tbody tr.current-row\{background:var\(--accent\)/);
});
