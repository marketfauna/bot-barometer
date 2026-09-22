// Hand-authored ordinary Playwright, not recorded codegen. The normal parameter
// file is an independent business oracle; results never become expectations.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {start,sha}=require('./local-runtime.cjs');
const money=text=>Math.round(Number(text.match(/\$([0-9]+(?:\.[0-9]+)?)/)[1])*100);
async function run({label='baseline-clean',user='standard_user',variant='clean',oracleFile='oracle.original.json',implementation='ordinary-playwright'}){
 const raw=fs.readFileSync(path.resolve(__dirname,oracleFile));const oracle=JSON.parse(raw);
 const outdir=path.join(__dirname,'results');fs.mkdirSync(outdir,{recursive:true});
 const out={label,implementation,user,variant,at:new Date().toISOString(),oracle:oracleFile,oracle_sha256:sha(raw),ruleId:oracle.ruleId,
  assertions:[],actions:[],screenshots:[],scope:'Local MIT demo only; no WooCommerce, real payment, backend order, shipping, email or fulfillment.'};
 let runtime,traceStarted=false;
 function check(name,actual,expected){let pass=true;try{assert.deepStrictEqual(actual,expected);}catch{pass=false;}out.assertions.push({name,expected,actual,pass});return pass;}
 const action=async(name,fn)=>{await fn();out.actions.push(name);};
 try{
  runtime=await start(variant);const {page:p,ctx,base}=runtime;
  await ctx.tracing.start({screenshots:true,snapshots:true,sources:true});traceStarted=true;
  const d=id=>p.locator(`[data-test="${id}"]`);
  const shot=async(stage)=>{const name=label+'-'+stage+'.png';await p.screenshot({path:path.join(outdir,name),fullPage:true});out.screenshots.push(name);};
  await action('open-local-login',()=>p.goto(base));
  await action('fill-sample-user',()=>d('username').fill(user));
  await action('fill-public-demo-password',()=>d('password').fill('secret_sauce'));
  await action('login',()=>d('login-button').click());
  await d('inventory-container').waitFor();
  const item=d('inventory-item').filter({has:d('inventory-item-name').filter({hasText:new RegExp('^'+oracle.product+'$')})});
  check('inventory.product',await item.locator('[data-test="inventory-item-name"]').innerText(),oracle.product);
  check('inventory.priceCents',money(await item.locator('[data-test="inventory-item-price"]').innerText()),oracle.itemCents);
  await action('add-selected-product',()=>item.getByRole('button',{name:'Add to cart',exact:true}).click());
  await action('open-cart',()=>d('shopping-cart-link').click());
  const cart=d('inventory-item');await cart.waitFor();
  check('cart.lineCount',await cart.count(),1);
  check('cart.product',await cart.locator('[data-test="inventory-item-name"]').innerText(),oracle.product);
  check('cart.quantity',Number(await cart.locator('[data-test="item-quantity"]').innerText()),oracle.quantity);
  check('cart.itemCents',money(await cart.locator('[data-test="inventory-item-price"]').innerText()),oracle.itemCents);
  await action('checkout',()=>d('checkout').click());
  for(const key of ['firstName','lastName','postalCode'])await action('fill-'+key,()=>d(key).fill(oracle.customer[key]));
  let fieldsGood=true;
  for(const key of ['firstName','lastName','postalCode'])fieldsGood=check('customer.'+key,await d(key).inputValue(),oracle.customer[key])&&fieldsGood;
  await shot('customer');await action('continue-checkout',()=>d('continue').click());
  if(!fieldsGood){out.upstream_error=await d('error').innerText();await shot('field-error');out.finalConfirmationReached=false;}
  else{
   await d('checkout-summary-container').waitFor();
   check('overview.lineCount',await d('inventory-item').count(),1);
   check('overview.product',await d('inventory-item-name').innerText(),oracle.product);
   check('overview.quantity',Number(await d('item-quantity').innerText()),oracle.quantity);
   check('overview.itemCents',money(await d('inventory-item-price').innerText()),oracle.itemCents);
   check('overview.subtotalCents',money(await d('subtotal-label').innerText()),oracle.subtotalCents);
   check('overview.taxCents',money(await d('tax-label').innerText()),oracle.taxCents);
   check('overview.totalCents',money(await d('total-label').innerText()),oracle.totalCents);
   await shot('overview');
   // Soft recorded assertions allow demonstration that a wrong business result
   // can still reach confirmation. The final process status remains a failure.
   await action('finish-local-demo',()=>d('finish').click());await d('complete-header').waitFor();
   check('confirmation.text',await d('complete-header').innerText(),oracle.confirmation);
   check('confirmation.cartBadgeCount',await d('shopping-cart-badge').count(),0);
   out.finalConfirmationReached=true;await shot('confirmation');
  }
 }catch(e){out.runtimeError={name:e.name,message:e.message};}
 finally{
  if(runtime){out.blocked_external_requests=runtime.blocked;out.local_mutations=runtime.patches;
   if(traceStarted){out.trace=label+'.trace.zip';await runtime.ctx.tracing.stop({path:path.join(outdir,out.trace)});}
   out.cleanup=await runtime.close();}
  out.passed=!out.runtimeError&&out.assertions.length>0&&out.assertions.every(a=>a.pass)&&out.finalConfirmationReached===true;
  out.failedAssertions=out.assertions.filter(a=>!a.pass);
  fs.writeFileSync(path.join(outdir,label+'.json'),JSON.stringify(out,null,2)+'\n');
 }
 return out;
}
module.exports={run};
if(require.main===module){run({label:process.argv[2]||'baseline-clean',variant:process.argv[3]||'clean',user:process.argv[4]||'standard_user',oracleFile:process.argv[5]||'oracle.original.json'}).then(r=>{console.log(JSON.stringify({label:r.label,passed:r.passed,failed:r.failedAssertions,runtimeError:r.runtimeError}));process.exitCode=r.passed?0:2;}).catch(e=>{console.error(e);process.exitCode=1;});}
