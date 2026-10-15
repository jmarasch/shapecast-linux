/* Exercise the actual setup-page request helper without a browser or vendor code. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/setup.html'), 'utf8');
const source = html.slice(html.indexOf('async function readJSON('), html.indexOf('async function api('));
function helper(fetch) {
  const context = {fetch, URL, location:{href:'http://127.0.0.1:10000/setup'}, setTimeout:fn=>{fn();return 0;}};
  vm.createContext(context);vm.runInContext(source, context);return context.readJSON;
}
const ok = () => ({ok:true,status:200,text:async()=>'{"ready":true}'});
(async()=>{
  let calls=0;
  let read=helper(async()=>{if(++calls===1)throw Error('interrupted read');return ok();});
  assert.equal((await read('/status')).ready,true);assert.equal(calls,2);
  calls=0;read=helper(async()=>{calls++;throw Error('interrupted write');});
  await assert.rejects(read('/activate',{method:'POST'},false),/interrupted write/);assert.equal(calls,1);
  calls=0;read=helper(async()=>{calls++;return {ok:false,status:403,text:async()=>'{"detail":"Denied"}'};});
  await assert.rejects(read('/status'),/Denied/);assert.equal(calls,1);
  calls=0;read=helper(async()=>++calls===1?{ok:true,text:async()=>'{"partial":'}:ok());
  assert.equal((await read('/status')).ready,true);assert.equal(calls,2);
  console.log('Setup read retries, incomplete JSON and non-repeated writes passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
