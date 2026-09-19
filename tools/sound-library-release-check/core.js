(function(root) {
  'use strict';
  const LIMITS = {characters: 5000000, rows: 10000, files: 20000, columns: 100};
  function parseDelimited(input, delimiter=',') {
    const out = {headers: [], rows: [], errors: [], delimiter};
    if (typeof input !== 'string' || input.length > LIMITS.characters) {out.errors.push('Input must be text of at most 5 million characters.'); return out;}
    if (![',','\t'].includes(delimiter)) {out.errors.push('Choose comma or tab explicitly.'); return out;}
    const text = input.startsWith('\ufeff') ? input.slice(1) : input;
    let field='', values=[], quoted=false, closed=false, line=1, startLine=1, touched=false;
    const records=[];
    function finish() { values.push(field); records.push({line:startLine, values}); values=[]; field=''; closed=false; touched=false; startLine=line; }
    for (let i=0;i<text.length;i++) {
      const c=text[i]; touched=true;
      if (quoted) {
        if (c==='"') {if(text[i+1]==='"'){field+='"';i++;} else {quoted=false;closed=true;}}
        else {field+=c;if(c==='\n'||(c==='\r'&&text[i+1]!=='\n'))line++;}
      } else if (c===delimiter) {values.push(field);field='';closed=false;}
      else if (c==='\r'||c==='\n') {if(c==='\r'&&text[i+1]==='\n')i++;line++;finish();}
      else if (c==='"' && field==='' && !closed) quoted=true;
      else if (closed || c==='"') {out.errors.push(`Malformed quote at physical line ${line}. No partial export was created.`);return out;}
      else field+=c;
      if(records.length > LIMITS.rows + 1) {out.errors.push('More than 10,000 metadata rows.');return out;}
    }
    if (quoted) {out.errors.push(`Unclosed quoted field beginning at or after line ${startLine}. No partial export was created.`);return out;}
    if(touched || field!=='' || values.length) finish();
    if(!records.length){out.errors.push('The metadata input is empty.');return out;}
    out.headers=records.shift().values;
    if(out.headers.length > LIMITS.columns) out.errors.push('More than 100 columns.');
    if(out.headers.some(h=>h.trim()==='')) out.errors.push('Every header must have a non-empty name.');
    if(new Set(out.headers).size!==out.headers.length) out.errors.push('Duplicate headers are ambiguous. Rename them in a copy before importing.');
    out.rows=records.map((r,i)=>({record:i+1,line:r.line,values:r.values}));
    for(const row of out.rows) if(row.values.length!==out.headers.length) out.errors.push(`Record ${row.record}, line ${row.line}: ${row.values.length} fields; expected ${out.headers.length}. No partial export was created.`);
    if(out.rows.length>LIMITS.rows)out.errors.push('More than 10,000 metadata rows.');
    return out;
  }
  function basename(path){return path.split('/').pop();}
  function invalidPath(p){return !p || /^[\\/]/.test(p) || /^[A-Za-z]:/.test(p) || p.includes('\\') || p.split('/').some(x=>x==='..'||x==='.'||x==='') || /[\u0000-\u001f\u007f]/.test(p);}
  function group(items, key) {const map=new Map();items.forEach(item=>{const k=key(item);if(!map.has(k))map.set(k,[]);map.get(k).push(item);});return map;}
  function reconcile(parsed, paths, columnIndex, mode='exact-relative') {
    if(parsed.errors.length) throw new Error(parsed.errors.join('\n'));
    if(!Number.isInteger(columnIndex)||columnIndex<0||columnIndex>=parsed.headers.length)throw new Error('Choose a filename column.');
    if(!['exact-relative','unique-basename'].includes(mode))throw new Error('Unknown matching mode.');
    if(!Array.isArray(paths)||!paths.length||paths.length>LIMITS.files)throw new Error('Supply 1 to 20,000 release paths.');
    const files=paths.map((v,i)=>({id:i+1,path:typeof v==='string'?v:v.path,issueCodes:[],referencedBy:[],matchedBy:[]}));
    if(files.some(f=>typeof f.path!=='string'))throw new Error('Every inventory path must be text.');
    const rows=parsed.rows.map(r=>({...r,filename:r.values[columnIndex],status:'hold',matchedPath:null,candidates:[],issueCodes:[]}));
    const issues=[];
    function issue(code,message,rowIds=[],fileIds=[]) {const id=issues.length+1;issues.push({id,code,message,rowIds,fileIds});rowIds.forEach(id=>rows[id-1].issueCodes.push(code));fileIds.forEach(id=>files[id-1].issueCodes.push(code));}
    files.forEach(f=>{if(invalidPath(f.path))issue('invalid_inventory_path','Use a non-empty relative path with / separators; no absolute paths, control characters or . / .. segments.',[],[f.id]);if(f.path!==f.path.trim())issue('path_edge_whitespace','Path has leading/trailing whitespace; identity preserved, review required.',[],[f.id]);});
    const exactFiles=group(files,f=>f.path);
    for(const entries of exactFiles.values())if(entries.length>1)issue('duplicate_inventory_path','The inventory contains this exact path more than once.',[],entries.map(f=>f.id));
    for(const [code, key] of [['case_collision',p=>p.toLowerCase()],['unicode_collision',p=>p.normalize('NFC')]]){
      for(const entries of group(files,f=>key(f.path)).values())if(new Set(entries.map(f=>f.path)).size>1)issue(code,'Distinct inventory paths collide under '+(code==='case_collision'?'case-insensitive comparison.':'Unicode NFC comparison.')+' They are not automatically merged.',[],entries.map(f=>f.id));
    }
    const rowKeys=group(rows,r=>r.filename);
    for(const [key,entries] of rowKeys)if(key && entries.length>1)issue('duplicate_metadata_key','Multiple metadata records have the same selected filename value.',entries.map(r=>r.record));
    const baseFiles=group(files,f=>basename(f.path));
    for(const row of rows){
      if(!row.filename){issue('blank_filename','The selected filename field is blank.',[row.record]);continue;}
      if(invalidPath(row.filename)){issue('invalid_metadata_path','Selected filename is not a valid relative path; no path normalization was applied.',[row.record]);continue;}
      if(row.filename!==row.filename.trim())issue('metadata_edge_whitespace','Filename has leading/trailing whitespace; no trimming was applied.',[row.record]);
      const key=mode==='unique-basename'?basename(row.filename):row.filename;
      const candidates=(mode==='unique-basename'?baseFiles:exactFiles).get(key)||[];
      row.candidates=candidates.map(f=>f.path);candidates.forEach(f=>f.referencedBy.push(row.record));
      if(candidates.length===0){
        const variants=files.filter(f=> (mode==='unique-basename'?basename(f.path):f.path).normalize('NFC').toLowerCase()===key.normalize('NFC').toLowerCase());
        issue(variants.length?'identity_variant':'metadata_without_file',variants.length?'Only case/Unicode variants were found. No automatic match was made.':'No file in the supplied inventory matches this metadata record.',[row.record],variants.map(f=>f.id));
      } else if(candidates.length>1)issue('ambiguous_file_match','More than one inventory entry can match this row. Use an unambiguous relative path.',[row.record],candidates.map(f=>f.id));
      else {row.matchedPath=candidates[0].path;candidates[0].matchedBy.push(row.record);if(candidates[0].issueCodes.length)issue('inventory_identity_hold','The matched inventory entry has identity issues; review it before release.',[row.record]);}
    }
    for(const file of files){
      if(file.matchedBy.length>1)issue('multiple_rows_for_file','More than one metadata record resolves to this file.',file.matchedBy,[file.id]);
      if(!file.referencedBy.length)issue('file_without_metadata','No metadata row exactly references this inventory entry in the selected mode.',[],[file.id]);
      file.status=file.issueCodes.length?'review':file.matchedBy.length===1?'matched':'unresolved';
    }
    for(const row of rows)if(row.matchedPath && !row.issueCodes.includes('inventory_identity_hold') && files.some(f=>f.path===row.matchedPath&&f.issueCodes.length))issue('inventory_identity_hold','The matched inventory entry has identity issues; review it before release.',[row.record]);
    rows.forEach(r=>r.status=r.matchedPath && !r.issueCodes.length?'matched':'hold');
    return {schema:1,mode,columnIndex,columnName:parsed.headers[columnIndex],headers:parsed.headers.slice(),rows,files,issues,counts:{metadataRows:rows.length,inventoryEntries:files.length,matchedRows:rows.filter(r=>r.status==='matched').length,heldRows:rows.filter(r=>r.status==='hold').length,issues:issues.length},scope:'Supplied metadata and filename inventory only. Not embedded metadata, sound quality, rights, UCS correctness, ZIP contents or marketplace acceptance.',createdAt:new Date().toISOString()};
  }
  function sheetData(report){
    return [
      {name:'Review',data:[['Sound Library Release Check','REVIEW COPY - supplied metadata only'],['Matching mode',report.mode],['Filename column',report.columnName],['Metadata rows',String(report.counts.metadataRows)],['Inventory entries',String(report.counts.inventoryEntries)],['Held rows',String(report.counts.heldRows)],['Issues',String(report.counts.issues)],['Scope',report.scope],['Privacy','Original source fields are retained below, including any private paths. Review before sharing.']]},
      {name:'Metadata',data:[report.headers,...report.rows.map(r=>r.values)]},
      {name:'Row review',data:[['Record','Source line','Filename','Status','Matched path','Candidate paths','Issues'],...report.rows.map(r=>[String(r.record),String(r.line),r.filename,r.status,r.matchedPath||'',r.candidates.join('\n'),r.issueCodes.join('; ')])]},
      {name:'Files',data:[['Entry','Original relative path','Status','Referenced by records','Matched by records','Issues'],...report.files.map(f=>[String(f.id),f.path,f.status,f.referencedBy.join(', '),f.matchedBy.join(', '),f.issueCodes.join('; ')])]},
      {name:'Issues',data:[['Issue','Code','Explanation','Records','Inventory entries'],...report.issues.map(i=>[String(i.id),i.code,i.message,i.rowIds.join(', '),i.fileIds.join(', ')])]}
    ];
  }
  function pdfSections(report){return [
    {title:'Release metadata - review copy',lines:[`Records: ${report.counts.metadataRows}; inventory entries: ${report.counts.inventoryEntries}; held rows: ${report.counts.heldRows}; issues: ${report.counts.issues}.`,`Matching: ${report.mode}; column: ${report.columnName}.`,report.scope,'All source columns are reproduced per record below. This document includes unresolved records; it is not a release approval. Review private fields before sharing.']},
    ...report.issues.map(i=>({title:`Issue ${i.id}: ${i.code}`,lines:[i.message,`Records: ${i.rowIds.join(', ')||'none'}; inventory entries: ${i.fileIds.join(', ')||'none'}.`]})),
    ...report.rows.map(r=>({title:`Record ${r.record} | ${r.status.toUpperCase()} | source line ${r.line}`,lines:[`Matched path: ${r.matchedPath||'unresolved'}`,`Issues: ${r.issueCodes.join(', ')||'none'}`,...report.headers.map((h,i)=>`${h}: ${r.values[i]}`)]})),
    {title:'Inventory accounting',lines:report.files.map(f=>`${f.id}. ${f.path} | ${f.status} | ${f.issueCodes.join(', ')||'no identity issue recorded'}`)}
  ];}
  const api={LIMITS,parseDelimited,reconcile,sheetData,pdfSections};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ReleasePack=api;
})(globalThis);
