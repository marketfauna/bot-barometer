// Adapted from the assigned startup-proof.cjs: ephemeral 127.0.0.1 server,
// installed headless Edge, isolated context, all non-local requests blocked.
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
async function start(variant){
 const root=path.join(__dirname,'sample-input'),blocked=[],patches=[];
 const server=http.createServer((req,res)=>{
  let target=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(!target.startsWith(root+path.sep)&&target!==root){res.writeHead(403);res.end();return;}
  if(!fs.existsSync(target)||fs.statSync(target).isDirectory())target=path.join(root,'index.html');
  let bytes=fs.readFileSync(target);
  if(path.basename(target)==='index-D3OxT1jE.js'&&variant!=='clean'){
   const before=bytes.toString('utf8');let from,to;
   if(variant==='wrong-total'){from='i=(n+parseFloat(r)).toFixed(2)';to='i=(n+parseFloat(r)+1).toFixed(2)';}
   else if(variant==='tax10'){from='let r=(n*.08).toFixed(2)';to='let r=(n*.10).toFixed(2)';}
   else {res.writeHead(500);res.end('Unknown variant');return;}
   if(before.split(from).length!==2){res.writeHead(500);res.end('Pinned mutation anchor mismatch');return;}
   bytes=Buffer.from(before.replace(from,to));patches.push({variant,local_only:true,file:path.relative(root,target),from,to,original_sha256:sha(before),served_sha256:sha(bytes)});
  }
  res.setHeader('Content-Type',target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html');
  res.setHeader('Cache-Control','no-store');res.end(bytes);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 let browser,ctx;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  ctx=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await ctx.route('**/*',route=>{if(new URL(route.request().url()).origin===base)return route.continue();blocked.push(route.request().url());return route.abort();});
  const page=await ctx.newPage();page.setDefaultTimeout(6000);
  return {page,ctx,base,blocked,patches,async close(){await ctx.close();await browser.close();await new Promise(r=>server.close(r));return {context_closed:true,browser_closed:true,server_closed:!server.listening};}};
 }catch(e){if(ctx)await ctx.close();if(browser)await browser.close();await new Promise(r=>server.close(r));throw e;}
}
module.exports={start,sha};
