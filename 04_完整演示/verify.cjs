'use strict';
// Local, simulated-DOM acceptance only. No browser, server, network or inference.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const local=__dirname,root=path.dirname(local),read=name=>fs.readFileSync(path.join(local,name),'utf8');
const html=read('OpenECG_Demo.html');
const embedded=text=>JSON.parse(text.match(/<script type="application\/json" id="demo-data">([\s\S]*?)<\/script>/)[1]);
const data=embedded(html),publicData=embedded(fs.readFileSync(path.join(root,'01_离线演示/OpenECG_Demo.html'),'utf8'));
const privateData=JSON.parse(read('data/anonymous_records.json'));
const sha256=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function checkHasWindow(text,d,label){
 const end=d.startSec+d.raw.length/d.fs;
 const windows=[...text.matchAll(/(\d+(?:\.\d+)?)\s*[–—−-]\s*(\d+(?:\.\d+)?)\s*秒/g)];
 assert(windows.some(m=>Number(m[1])===d.startSec&&Number(m[2])===end),label+' shows actual source window '+d.startSec+'–'+end);
}
function reconstructedWindow(record,startSample,endSample){
 const values=new Map();
 for(const segment of record.segments){
  assert(Number.isInteger(segment.startSample));assert.equal(segment.signal.length,segment.sampleCount);
  for(let i=0;i<segment.signal.length;i++){
   const index=segment.startSample+i;
   if(index>=startSample&&index<endSample){assert(!values.has(index),'source sample occurs once');values.set(index,segment.signal[i]);}
  }
 }
 const samples=[];
 for(let index=startSample;index<endSample;index++){assert(values.has(index),'complete continuous reconstructed sample '+index);const value=values.get(index);assert(Number.isFinite(value));samples.push(value);}
 assert.equal(values.size,samples.length);return samples;
}
function float64LeSha256(samples){const buffer=Buffer.alloc(samples.length*8);samples.forEach((value,i)=>buffer.writeDoubleLE(value,i*8));return sha256(buffer);}
const sources=['LUDB','QTDB','APPLEWATCH'],counts={LUDB:10,QTDB:10,APPLEWATCH:5};
assert.equal(data.length,25);assert.equal(new Set(data.map(d=>d.id)).size,25);
for(const source of sources)assert.equal(data.filter(d=>d.dataset===source).length,counts[source],source+' count');
assert.deepStrictEqual(data.filter(d=>d.dataset!=='APPLEWATCH'),publicData,'20 public payloads unchanged');
for(const frozen of privateData)assert.deepStrictEqual(data.find(d=>d.id===frozen.id),frozen,frozen.id+' frozen model result unchanged');
assert.deepStrictEqual(privateData.map(d=>d.id),['anonymous-a','anonymous-b','anonymous-c','anonymous-d','anonymous-e']);
const catalog=JSON.parse(read('data/catalog.json'));
assert.equal(catalog.anonymousSelectableEntries,5);assert.equal(catalog.uniqueMeasurements,5);
assert.deepStrictEqual(catalog.records.map(d=>d.id),privateData.map(d=>d.id));
assert(html.includes('本地')&&html.includes('PDF')&&html.includes('重建'));
assert(!/<(?:script|link|img|iframe|audio|video|source|object|embed)\b[^>]*(?:src|href|data)=["'](?:https?:)?\/\//i.test(html),'no automatic remote resources');
assert(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon\s*\(|\bimport\s*\(/.test(html),'no network APIs');
assert(!/type=["']file["']|%PDF-|data:application\/pdf|<iframe\b|<object\b|<embed\b/i.test(html),'no PDF embedding or upload');
assert(!/姓名\s*[:：]|出生日期\s*[:：]|测量(?:日期|时间)\s*[:：]|患者(?:姓名|编号)|病历号|报告编号|性别\s*[:：]|年龄\s*[:：]|(?:19|20)\d{2}[-/年]\d{1,2}[-/月]\d{1,2}/.test(html),'no personal report identity or dates');
const allowedPrivateKeys=['id','dataset','record','lead','label','fs','sourceFs','startSec','unit','mode','model','raw','filtered','waves','groundTruth','rPeaks','rr','metrics','pdfReconstruction','coursework'];
for(const d of privateData){
 assert.deepStrictEqual(Object.keys(d).sort(),allowedPrivateKeys.slice().sort(),'private record metadata whitelist');
 assert.equal(d.fs,250);assert.equal(d.sourceFs,512);assert(Number.isFinite(d.startSec)&&d.startSec>=0);assert.equal(d.lead,'I');
 assert.deepStrictEqual(d.pdfReconstruction.windowSec,[d.startSec,d.startSec+d.raw.length/d.fs],'PDF window matches actual record metadata');
 if(d.id==='anonymous-b')assert.equal(d.startSec,10,'B original window unchanged');
 assert.equal(d.raw.length,2500);assert.equal(d.filtered.length,2500);assert(d.raw.every(Number.isFinite)&&d.filtered.every(Number.isFinite));
 assert(d.model.includes('openecg 0.11.0')&&d.model.includes('PDF'));assert(d.waves.length>0&&d.rPeaks.length>1);
 assert.equal(d.groundTruth.length,0);assert.equal(d.coursework.comparison.rows.length,0);
 assert.equal(d.pdfReconstruction.kind,'pdf-vector-reconstruction');assert.equal(d.pdfReconstruction.hasManualGroundTruth,false);
 assert(/relative/i.test(d.pdfReconstruction.amplitude));
 for(const s of d.coursework.comparison.summaries){
  assert.equal(s.referenceCount,0);assert.equal(s.matchedCount,0);assert.equal(s.unscoredPredictionCount,s.predictionCount);
  for(const key of ['pairingRatePct','onsetMaeMs','offsetMaeMs','onsetBiasMs','offsetBiasMs','durationMaeMs','bothWithinRatePct'])assert.equal(s[key],null,d.id+' unavailable '+key);
 }
}
const provenance=JSON.parse(read('data/provenance.json'));
assert.equal(provenance.recordCount,5);assert.equal(provenance.uniqueMeasurements,5);
assert.equal(sha256(Buffer.from(read('data/anonymous_records.json'))),provenance.frozenResultsSha256);
assert(provenance.model.files.some(f=>f.sha256==='2e130ed795491764ffa4f7eff5decc06a4531ac69e1cab51bfbffa714bc0b3fb'));
for(const entry of provenance.records){
 const source=JSON.parse(read(entry.inputPath)),d=privateData.find(r=>r.id===entry.id);
 assert(d);assert.equal(sha256(Buffer.from(read(entry.inputPath))),entry.inputSha256);
 assert.equal(source.fs,512);assert.equal(source.signal.length,5120);assert(source.signal.every(Number.isFinite));
 assert.equal(source.id,d.id);assert.deepStrictEqual(source.windowSec,d.pdfReconstruction.windowSec);
 assert.equal(float64LeSha256(source.signal),entry.inputFloat64LeSha256);
 assert.equal(d.pdfReconstruction.duplicateOf,undefined);
}
assert.equal(new Set(provenance.records.map(r=>r.inputFloat64LeSha256)).size,5);
assert(/<h1>[^<]+<\/h1><p class="github-link"><a href="https:\/\/github.com\/storm0699\/openecg-weblab"/.test(html),'GitHub link immediately below heading');
class Element{
 constructor(id=''){this.id=id;this.children=[];this.attrs={};this.dataset={};this.handlers={};this.style={};this.hidden=false;this.disabled=false;this.value='';this.checked=false;this.classList={toggle:()=>{}};this._html='';this.textContent='';}
 setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k];}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}querySelector(){return this.children[0];}
 addEventListener(k,cb){this.handlers[k]=cb;}click(){if(!this.disabled)this.handlers.click?.({});}focus(){document.activeElement=this;}remove(){}
 getBoundingClientRect(){return {left:0,width:960};}setPointerCapture(){}hasPointerCapture(){return true;}releasePointerCapture(){}
 set innerHTML(v){this._html=v;}get innerHTML(){return this._html;}
}
const ids=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element(m[1])]));
for(const name of ['crosshair','hover-dot','selection'])ids.set(name,new Element(name));
ids.get('steps').children=Array.from({length:3},()=>{const el=new Element();el.children=[new Element()];return el;});
ids.get('demo-data').textContent=JSON.stringify(data);
const tabs=sources.map(source=>{const el=ids.get('tab-'+source.toLowerCase());assert(el,source+' tab');el.dataset.source=source;return el;});
const waves=['P','QRS','T','R'].map(type=>{const el=new Element();el.dataset.wave=type;return el;});
const tablist=new Element(),document={getElementById:id=>ids.get(id),querySelectorAll:s=>s==='[data-source]'?tabs:s==='[data-wave]'?waves:[],querySelector:()=>tablist,createElement:()=>new Element(),createTextNode:s=>({textContent:s}),body:new Element(),activeElement:tabs[0]};
const downloads=[],downloadURL={createObjectURL:blob=>{downloads.push(blob);return 'blob:test-'+downloads.length;},revokeObjectURL:()=>{}};
const context={document,console,Blob,URL:downloadURL,setTimeout:cb=>cb(),requestAnimationFrame:cb=>setImmediate(cb)};context.globalThis=context;vm.createContext(context);
let code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const initialization=/populate\(\);\s*load\(\);/;
assert(initialization.test(code),'local app initialization hook');
code=code.replace(initialization,'globalThis.api={records,state,load,draw,validate,waveRows,beatRows,qrsRows,comparisonRows,summaryRows,summaryNote,zoom,reset,setRange,clearResult,focusQrs,focusReference,focusExample,waveformSvg};populate();load();');
vm.runInContext(code,context);const api=context.api,tick=()=>new Promise(r=>setImmediate(r));
async function idle(){for(let i=0;i<30&&api.state.busy;i++)await tick();assert(!api.state.busy,'load completed');}
const plain=value=>JSON.parse(JSON.stringify(value));
function assertSourceOptions(source){
 assert.equal(ids.get('record').children.map(o=>o.value).join(','),data.filter(d=>d.dataset===source).map(d=>d.id).join(','));
 for(const [i,name] of sources.entries()){assert(tabs[i].textContent.includes(String(counts[name])));assert.equal(tabs[i].attrs['aria-selected'],String(source===name));}
}
function assertCleared(){
 assert.equal(api.state.current,null);assert(api.state.busy);assert.equal(ids.get('plot').innerHTML,'');assert(ids.get('plot-viewport').hidden);
 for(const id of ['export-wave','export-beats','export-qrs','export-summary','export-comparison','export-note','export-svg'])assert(ids.get(id).disabled,id+' disabled during load');
}
async function choose(d){
 if(api.state.source!==d.dataset){tabs[sources.indexOf(d.dataset)].click();assertCleared();await idle();assert.equal(api.state.current.dataset,d.dataset);}
 assertSourceOptions(d.dataset);ids.get('record').value=d.id;ids.get('record').handlers.change();assertCleared();await idle();
 assert.equal(api.state.current.id,d.id);assert.equal(ids.get('error').hidden,true);assert.equal(ids.get('record').disabled,false);assert.equal(ids.get('record').value,d.id);assert(ids.get('plot').innerHTML.includes('<polyline'));
}
function assertUnavailable(d){
 assert.equal(d.groundTruth.length,0);assert(ids.get('truth').disabled);assert(ids.get('focus-comparison').disabled);assert.equal(api.focusExample('comparison'),false);
 const table=ids.get('comparison-table').innerHTML,rows=[...table.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(m=>m[1]);
 assert.equal(rows.length,3);assert(!table.includes('0.0%')&&!table.includes('100.0%'),'no false accuracy on absent labels');
 for(const row of rows){const cells=[...row.matchAll(/<td>([\s\S]*?)<\/td>/g)].map(m=>m[1]);assert.equal(cells.length,7);for(const column of [1,2,3,4,5])assert(cells[column].includes('不可评价'),'unavailable rate/MAE cells explicitly labelled');}
 assert(ids.get('comparison-status').textContent.includes('人工'));
}
(async()=>{
 await idle();assert.equal(api.state.current.id,'ludb-16');assert.equal(api.state.source,'LUDB');assertSourceOptions('LUDB');
 assert(ids.get('record-title').textContent.includes('16'));assert.equal(ids.get('record').value,'ludb-16');assert.equal(api.state.range.join(','),'0,10');
 const fullRange=api.state.range.join(',');let ordinaryPrevented=false,ctrlPrevented=false;
 ids.get('plot').handlers.wheel({deltaY:-100,clientX:500,ctrlKey:false,preventDefault(){ordinaryPrevented=true;}});assert.equal(ordinaryPrevented,false);assert.equal(api.state.range.join(','),fullRange);
 ids.get('plot').handlers.wheel({deltaY:-100,clientX:500,ctrlKey:true,preventDefault(){ctrlPrevented=true;}});assert(ctrlPrevented);assert(api.state.range[1]-api.state.range[0]<10);api.reset();
 for(const d of data){
  await choose(d);api.validate(d);let shared=null;
  for(const filtered of [true,false]){api.state.filtered=filtered;api.draw();const limits=[api.state.geometry.bottom,api.state.geometry.top];if(shared)assert.deepStrictEqual(limits,shared,d.id+' full shared Y');shared=limits;assert(limits[0]<=Math.min(...d.raw,...d.filtered)&&limits[1]>=Math.max(...d.raw,...d.filtered));assert(!/NaN|Infinity|undefined/.test(ids.get('plot').innerHTML));}
  api.setRange(2,4);ids.get('filtered').click();const common=[api.state.geometry.bottom,api.state.geometry.top];ids.get('raw').click();assert.deepStrictEqual([api.state.geometry.bottom,api.state.geometry.top],common,d.id+' local shared Y');api.reset();
  if(d.dataset==='APPLEWATCH'){
   assertUnavailable(d);assert(/相对/.test(ids.get('record-meta').textContent));assert(/PDF/.test(ids.get('record-meta').textContent));
   checkHasWindow(ids.get('record-meta').textContent,d,'metadata '+d.id);
   checkHasWindow(ids.get('applewatch-window-method').textContent,d,'window method '+d.id);
   assert(/重建/.test(ids.get('raw').textContent),'private raw button identifies reconstruction');
   if(d.id==='anonymous-c')assert(!ids.get('record-title').textContent.includes('重复'),'new C title has no stale duplicate marker');
  }
  const allRows=[['export-wave',api.waveRows(d)],['export-beats',api.beatRows(d)],['export-qrs',api.qrsRows(d)],['export-comparison',api.comparisonRows(d)],['export-summary',api.summaryRows(d)]];
  for(const [id,rows] of allRows){assert(!/NaN|undefined|Infinity/.test(rows.join('\n')));const width=rows[0].split(',').length;assert(rows.every(r=>r.split(',').length===width));const before=downloads.length;ids.get(id).click();assert.equal(downloads.length,before+1);assert.equal((await downloads.at(-1).text()).replace(/^\uFEFF/,''),rows.join('\r\n'));}
  assert.equal(api.waveRows(d).length,2501);assert.equal(api.beatRows(d).length,d.rPeaks.length+1);assert.equal(api.comparisonRows(d).length,d.groundTruth.length+1);
  if(d.coursework.qrs.rows.length){assert(api.focusExample('qrs'));assert(ids.get('plot').innerHTML.includes('data-focused="prediction"'));}
  if(d.groundTruth.length){assert(api.focusExample('comparison'));assert(api.state.truth);assert(ids.get('plot').innerHTML.includes('data-focused="reference"'));}else assertUnavailable(d);
  const svg=api.waveformSvg();assert(svg.includes(d.id));assert(!/<script\b|NaN|undefined|Infinity/.test(svg));const svgCount=downloads.length;ids.get('export-svg').click();assert.equal(downloads.length,svgCount+1);assert.equal(await downloads.at(-1).text(),svg);
  if(d.dataset==='APPLEWATCH')checkHasWindow(svg,d,'SVG '+d.id);
  if(d.id==='anonymous-c')assert(!svg.includes('重复导出'),'new C SVG has no stale duplicate marker');
  const note=api.summaryNote();assert(note.includes(d.id)&&note.includes(d.model));assert(note.includes('QRS 时限')&&note.includes('模型边界步进约 20 毫秒'));
  if(d.dataset==='APPLEWATCH'){assert(/PDF/.test(note)&&/重建/.test(note)&&/相对/.test(note));checkHasWindow(note,d,'TXT '+d.id);}
  if(d.id==='anonymous-c')assert(!note.includes('重复关系'),'new C TXT has no stale duplicate marker');
  const count=downloads.length;ids.get('export-note').click();assert.equal(downloads.length,count+1);assert.equal((await downloads.at(-1).text()).replace(/^\uFEFF/,''),note);
  api.setRange(1,2);ids.get('comparison-kind').value='T';ids.get('comparison-kind').handlers.change();ids.get('comparison-issues').checked=true;ids.get('comparison-issues').handlers.change();assert.equal(api.summaryNote(),note,'export scope unaffected by zoom/filter');
  api.reset();const range=api.state.range.join(',');assert.equal(api.setRange(NaN,3),false);assert.equal(api.state.range.join(','),range);assert.equal(api.zoom(0,3),false);
  console.log(d.id,'auto-load, frozen model, shared Y, controls and CSV/SVG/TXT passed');
 }
 // Re-entering the personal source picks A, and choosing B starts loading itself.
 tabs[0].click();await idle();tabs[2].click();assertCleared();await idle();assert.equal(api.state.current.id,'anonymous-a');
 await choose(data.find(d=>d.id==='anonymous-b'));assertUnavailable(api.state.current);
 // Keyboard navigation reaches every source, including the third tab.
 tabs[2].focus();tablist.handlers.keydown({key:'ArrowRight',preventDefault(){}});await idle();assert.equal(api.state.source,'LUDB');
 tablist.handlers.keydown({key:'End',preventDefault(){}});await idle();assert.equal(api.state.source,'APPLEWATCH');assert.equal(api.state.current.id,'anonymous-a');
 const original=api.records.find(d=>d.id==='anonymous-a'),index=api.records.indexOf(original),broken=plain(original);broken.coursework.comparison.summaries[0].pairingRatePct=100;
 assert.throws(()=>api.validate(broken));api.records[index]=broken;api.state.selected=broken.id;await api.load();assert.equal(api.state.current,null);assert.equal(ids.get('error').hidden,false);assert(ids.get('export-note').disabled);api.records[index]=original;
 await choose(data.find(d=>d.id==='anonymous-b'));assertUnavailable(api.state.current);
 console.log('PASS: 25 local records; 20 public and 5 Apple Watch frozen results; source inputs, GitHub link, controls, CSV/SVG/TXT, no-GT metrics and recovery.');
 console.log('Scope: simulated DOM/data/package checks only; no browser visual QA, model rerun, upload or cloud publication.');
})().catch(error=>{console.error(error);process.exitCode=1;});
