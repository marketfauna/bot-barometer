(function(root){
  'use strict';
  function pdfUnsupported(report){
    const allowed=new Set(root.ReleasePackFont.codepoints);
    const strings=root.ReleasePack.pdfSections(report).flatMap(s=>[s.title,...s.lines]);
    return [...new Set(Array.from(strings.join('')).filter(c=>!['\n','\r','\t'].includes(c)&&!allowed.has(c.codePointAt(0))))];
  }
  async function xlsxBytes(report){
    const sheets=root.ReleasePack.sheetData(report);
    for(const sheet of sheets)for(let r=0;r<sheet.data.length;r++)for(let c=0;c<sheet.data[r].length;c++){
      const value=String(sheet.data[r][c]??'');
      if(value.length>32767)throw new Error(`XLSX blocked: ${sheet.name}, row ${r+1}, column ${c+1} exceeds Excel's 32,767-character cell limit. Full data remains available in JSON; no truncated workbook is produced.`);
      if(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/.test(value))throw new Error(`XLSX blocked: ${sheet.name}, row ${r+1}, column ${c+1} contains a control/noncharacter that cannot be preserved by this workbook exporter. Full data remains available in JSON.`);
    }
    const wb=new root.ExcelJS.Workbook();wb.creator='Marketfauna';wb.subject='Supplied metadata and release filename reconciliation';
    for(const sheet of sheets){
      const ws=wb.addWorksheet(sheet.name,{views:[{state:'frozen',ySplit:1}],pageSetup:{orientation:'landscape',fitToPage:true,fitToWidth:1,fitToHeight:0}});
      sheet.data.forEach(values=>{const row=ws.addRow(values.map(v=>String(v??'')));row.eachCell(c=>{c.numFmt='@';c.font={name:'Calibri',size:11};c.alignment={vertical:'top',wrapText:true};});});
      const cols=sheet.data[0].length;
      for(let c=1;c<=cols;c++)ws.getColumn(c).width=sheet.name==='Review'?(c===1?26:95):Math.min(70,Math.max(18,...sheet.data.slice(0,300).map(r=>Math.min(65,String(r[c-1]??'').length))));
      ws.eachRow(row=>{let lines=1;row.eachCell((cell,c)=>{const needed=String(cell.value).split('\n').reduce((sum,v)=>sum+Math.max(1,Math.ceil(v.length/Math.max(10,ws.getColumn(c).width-2))),0);lines=Math.max(lines,needed);});row.height=Math.min(409,Math.max(22,lines*15+8));});
      ws.getRow(1).eachCell(c=>{c.font={name:'Calibri',size:11,bold:true,color:{argb:'FFFFFFFF'}};c.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FF173D33'}};});
      if(sheet.name!=='Review')ws.autoFilter={from:{row:1,column:1},to:{row:Math.max(1,sheet.data.length),column:cols}};
    }
    return wb.xlsx.writeBuffer();
  }
  function pdfBytes(report){
    const unsupported=pdfUnsupported(report);
    if(unsupported.length)throw new Error('Direct PDF blocked: the bundled font cannot render '+unsupported.slice(0,12).map(c=>`${c} (U+${c.codePointAt(0).toString(16).toUpperCase()})`).join(', ')+(unsupported.length>12?' and further characters.':'.')+' XLSX/JSON preserve these characters.');
    const {jsPDF}=root.jspdf;
    const doc=new jsPDF({unit:'pt',format:'a4',compress:true});
    doc.addFileToVFS('Vera.ttf',root.ReleasePackFont.base64);doc.addFont('Vera.ttf','Vera','normal');doc.setFont('Vera');
    const width=doc.internal.pageSize.getWidth(),height=doc.internal.pageSize.getHeight(),left=42,bottom=height-42;
    let y=55;
    function page(){if(doc.getNumberOfPages()>=300)throw new Error('PDF exceeds 300 pages. Reduce the review batch; no truncated PDF is exported.');doc.addPage();y=55;}
    for(const section of root.ReleasePack.pdfSections(report)){
      if(y>bottom-70)page();
      doc.setFontSize(11);doc.setTextColor(23,61,51);
      for(const line of doc.splitTextToSize(section.title,width-2*left)){if(y>bottom)page();doc.text(line,left,y);y+=15;}
      y+=4;doc.setFontSize(9);doc.setTextColor(35,40,37);
      for(const text of section.lines){
        const display=text.replace(/\t/g,'\\t').replace(/\r\n/g,'\n').replace(/\r/g,'\n');
        for(const paragraph of display.split('\n'))for(const line of doc.splitTextToSize(paragraph||' ',width-2*left)){if(y>bottom)page();doc.text(line,left,y);y+=13;}
        y+=5;
      }
      y+=13;
    }
    const pages=doc.getNumberOfPages();
    for(let p=1;p<=pages;p++){doc.setPage(p);doc.setFontSize(8);doc.setTextColor(100);doc.text('SUPPLIED METADATA | REVIEW COPY | not release approval',left,28);doc.text(`Page ${p} / ${pages}`,left,height-21);}
    doc.setProperties({title:'Release metadata - review copy',author:'Marketfauna',subject:report.scope});
    return doc.output('arraybuffer');
  }
  const api={xlsxBytes,pdfBytes,pdfUnsupported};root.ReleasePackExport=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
