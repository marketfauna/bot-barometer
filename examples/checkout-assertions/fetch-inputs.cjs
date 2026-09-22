// Download only the pinned public fixture bytes; no dependencies are installed.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
(async()=>{
 const input=JSON.parse(fs.readFileSync(path.join(__dirname,'inputs.json')));
 const root=path.join(__dirname,'sample-input');
 for(const item of input.files){
  const target=path.resolve(root,item.path);
  if(!target.startsWith(root+path.sep))throw Error('Input path outside fixture');
  const response=await fetch(item.url);
  if(!response.ok)throw Error('Input fetch failed: '+response.status);
  const bytes=Buffer.from(await response.arrayBuffer());
  if(bytes.length!==item.bytes||crypto.createHash('sha256').update(bytes).digest('hex')!==item.sha256)throw Error('Pinned input mismatch: '+item.path);
  fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,bytes);
 }
 console.log('Verified '+input.files.length+' pinned fixture files.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
