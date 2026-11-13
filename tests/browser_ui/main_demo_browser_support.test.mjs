import test from 'node:test';import assert from 'node:assert/strict';
import {mainDemoLaunchURL,mainDemoLaunchOutputReader,mainDemoAllowedRequest} from './main_demo_browser_support.mjs';
const token='A'.repeat(43),origin='http://127.0.0.1:32123',url=origin+'/#session='+token+'&attachment=1';
test('main-demo exact launcher attachment URL and streamed output',()=>{
 assert.equal(mainDemoLaunchURL(url).href,url);const read=mainDemoLaunchOutputReader();
 assert.equal(read(Buffer.from('Starting\n'+url.slice(0,35))),null);
 assert.equal(read(Buffer.from(url.slice(35)+'\r\n')).href,url);assert.equal(read(Buffer.from(url+'\n')),null);
});
test('main-demo launcher rejects credentials, remote host, query and incorrect capability shape',()=>{
 for(const bad of [url.replace('&attachment=1',''),url+'&extra=1',url.replace('127.0.0.1','localhost'),url.replace('32123','65536'),url.replace('http:','https:'),url.replace('/#','/?x=1#'),url.replace(token,token+'A'),url.replace('127.0.0.1','user@127.0.0.1')])assert.throws(()=>mainDemoLaunchURL(bad));
});
test('main-demo output reader has bounded single-use buffer',()=>{
 const read=mainDemoLaunchOutputReader();assert.throws(()=>read(Buffer.alloc(4097)));assert.equal(read(Buffer.from(url+'\n')),null);
 assert.throws(()=>mainDemoLaunchOutputReader()('not-buffer'));
});
test('main-demo request allowlist admits exact assets and attachment only on pinned loopback origin',()=>{
 for(const p of ['/','/app.js','/catalog.js','/configuration.js','/catalog.css','/configuration.css','/style.css','/attachment','/rpc','/favicon.ico'])assert.equal(mainDemoAllowedRequest(origin+p,origin),true,p);
 for(const bad of [origin+'/attachment?x=1',origin+'/unknown.js',origin+'/catalog.js/extra',origin.replace('32123','32124')+'/rpc','https://example.com/rpc',origin.replace('127.0.0.1','user@127.0.0.1')+'/rpc'])assert.equal(mainDemoAllowedRequest(bad,origin),false,bad);
 assert.equal(mainDemoAllowedRequest('https://example.com/rpc','https://example.com'),false);
});
