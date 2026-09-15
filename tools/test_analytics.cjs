// No network: verify that operator checks never append the third-party beacon.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../analytics.js'), 'utf8');
function run({host='marketfauna.com',search='',storage=new Map(),token='public-test-token',denied=false}={}) {
  const scripts=[];
  vm.runInNewContext(code, {
    URLSearchParams, location:{hostname:host,search},
    sessionStorage:{setItem:(k,v)=>{if(denied)throw Error();storage.set(k,v);},getItem:k=>{if(denied)throw Error();return storage.get(k);}},
    document:{currentScript:{getAttribute:()=>token},createElement:()=>({setAttribute(k,v){this[k]=v;}}),head:{appendChild:s=>scripts.push(s)}}
  });
  return scripts;
}
test('ordinary production visit loads one official beacon with public token',()=>{
  const scripts=run(); assert.equal(scripts.length,1);
  assert.equal(scripts[0].src,'https://static.cloudflareinsights.com/beacon.min.js');
  assert.equal(JSON.parse(scripts[0]['data-cf-beacon']).token,'public-test-token');
});
test('operator opt-out persists for later navigation in the same session',()=>{
  const storage=new Map(); assert.equal(run({search:'?analytics=off',storage}).length,0);
  assert.equal(run({storage}).length,0);
});
test('current-page exclusion works even if session storage is denied',()=>{
  assert.equal(run({search:'?analytics=off',denied:true}).length,0);
});
test('local preview and missing-token configuration never load a beacon',()=>{
  assert.equal(run({host:'127.0.0.1'}).length,0);
  assert.equal(run({token:''}).length,0);
});
