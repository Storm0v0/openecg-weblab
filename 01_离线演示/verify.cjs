const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=__dirname,builtHtml=fs.readFileSync(root+'/OpenECG_Demo.html','utf8');
const embedded=builtHtml.match(/<script type="application\/json" id="demo-data">([\s\S]*?)<\/script>/)[1];
// --source checks edited template/app in memory without overwriting release artifacts.
const html=process.argv.includes('--source')?fs.readFileSync(root+'/template.html','utf8').replace('/*__BASE_CSS__*/',fs.readFileSync(root+'/base.css','utf8')).replace('/*__DEMO_DATA__*/',embedded).replace('/*__APP_JS__*/',()=>fs.readFileSync(root+'/app.js','utf8')):builtHtml;
const data=JSON.parse(embedded);
const sources=['LUDB','QTDB'],sourceCounts=Object.fromEntries(sources.map(source=>[source,data.filter(d=>d.dataset===source).length]));
const expectedCount=process.argv.find(arg=>arg.startsWith('--expected-per-source='))?.split('=')[1];
assert.equal(new Set(data.map(d=>d.id)).size,data.length,'record ids must be unique');
assert.equal(Object.values(sourceCounts).reduce((sum,n)=>sum+n,0),data.length);
assert(sources.every(source=>sourceCounts[source]>=2),'both databases must provide multiple records');
if(expectedCount!==undefined){assert(Number.isInteger(Number(expectedCount))&&Number(expectedCount)>0);for(const source of sources)assert.equal(sourceCounts[source],Number(expectedCount),source+' record count');}
const exportMenu=html.match(/<details[^>]*id="data-exports"[^>]*>([\s\S]*?)<\/details>/);
assert(exportMenu,'one native disclosure groups the six data exports');
for(const id of ['export-beats','export-wave','export-qrs','export-summary','export-comparison','export-note']){assert(exportMenu[1].includes(`id="${id}"`),id+' inside export disclosure');assert.equal([...html.matchAll(new RegExp(`id="${id}"`,'g'))].length,1,id+' occurs once');}
assert(!/<details[^>]*id="(?:data-exports|fixed-settings)"[^>]*\bopen(?:[\s=>])/.test(html),'fixed controls and exports start collapsed');
assert(html.includes('最低瞬时心率')&&html.includes('最高瞬时心率')&&html.includes('60/RR'));
assert(html.includes('双边界在演示阈值内')&&html.includes('预训练模型'));
assert(!/type=["']file["']/.test(html));assert(!/<script[^>]+src=|<link[^>]+href=|@import|fetch\(/.test(html));
class Element{
 constructor(id=''){this.id=id;this.children=[];this.attrs={};this.dataset={};this.handlers={};this.style={};this.hidden=false;this.disabled=false;this.value='';this.classList={toggle:()=>{}};this._html='';this.textContent='';}
 setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k];}
 append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}querySelector(){return this.children[0];}
 addEventListener(k,cb){this.handlers[k]=cb;}click(){if(!this.disabled)this.handlers.click?.({});}focus(){document.activeElement=this;}remove(){}
 getBoundingClientRect(){return {left:0,width:960};}setPointerCapture(){}hasPointerCapture(){return true;}releasePointerCapture(){}
 set innerHTML(v){this._html=v;}get innerHTML(){return this._html;}
}
const ids=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element(m[1])]));
ids.set('crosshair',new Element());ids.set('hover-dot',new Element());ids.set('selection',new Element());
ids.get('steps').children=Array.from({length:3},()=>{const el=new Element();el.children=[new Element()];return el;});ids.get('demo-data').textContent=JSON.stringify(data);
const tabs=['LUDB','QTDB'].map(s=>{const el=ids.get('tab-'+s.toLowerCase());el.dataset.source=s;return el;});
const waves=['P','QRS','T','R'].map(s=>{const el=new Element();el.dataset.wave=s;return el;});
const tablist=new Element(),document={getElementById:id=>ids.get(id),querySelectorAll:s=>s==='[data-source]'?tabs:s==='[data-wave]'?waves:[],querySelector:()=>tablist,createElement:()=>new Element(),createTextNode:s=>({textContent:s}),body:new Element(),activeElement:tabs[0]};
const downloads=[];
const downloadURL={createObjectURL:blob=>{downloads.push(blob);return 'blob:test-'+downloads.length;},revokeObjectURL:()=>{}};
const context={document,console,Blob,URL:downloadURL,setTimeout:cb=>cb(),requestAnimationFrame:cb=>setImmediate(cb)};context.globalThis=context;vm.createContext(context);
let code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
code=code.replace('populate();load();','globalThis.api={records,state,load,draw,validate,waveRows,beatRows,qrsRows,comparisonRows,summaryRows,summaryNote,zoom,reset,setRange,clearResult,focusQrs,focusReference,focusExample,waveformSvg};populate();load();');
vm.runInContext(code,context);const api=context.api;const tick=()=>new Promise(r=>setImmediate(r));
async function idle(active=api){for(let i=0;i<20&&active.state.busy;i++)await tick();assert(!active.state.busy);}
function assertClearedDuringLoad(){
 assert.equal(api.state.current,null);assert(api.state.busy);assert(ids.get('plot-viewport').hidden);assert.equal(ids.get('plot').innerHTML,'');assert.equal(api.state.geometry,null);assert.equal(api.state.focus,null);
 assert.equal(api.state.comparisonKind,'all');assert.equal(api.state.issuesOnly,false);assert.equal(api.state.truth,false);assert.equal(ids.get('focus-note').textContent,'');
 for(const id of ['export-wave','export-beats','export-qrs','export-comparison','export-summary','export-svg','export-note','focus-qrs','focus-comparison'])assert(ids.get(id).disabled,id+' while auto-loading');
 assert(ids.get('qrs-table').innerHTML.includes('等待加载'));assert(ids.get('comparison-table').innerHTML.includes('等待加载'));assert.equal(ids.get('progress').attrs['aria-valuenow'],'1');
}
function assertSourceOptions(source){
 assert.equal(ids.get('record').children.map(option=>option.value).join(','),data.filter(d=>d.dataset===source).map(d=>d.id).join(','));
 for(const [index,name] of sources.entries()){assert.equal(tabs[index].textContent,`${name} · ${sourceCounts[name]} 条`);assert.equal(tabs[index].attrs['aria-selected'],String(source===name));}
}
async function chooseRecord(d){
 if(api.state.source!==d.dataset){tabs[sources.indexOf(d.dataset)].click();assertClearedDuringLoad();await idle();assert.equal(api.state.current.dataset,d.dataset);}
 assertSourceOptions(d.dataset);
 ids.get('record').value=d.id;ids.get('record').handlers.change();assertClearedDuringLoad();
 // No click on the reload button: the real record change handler starts loading.
 await idle();assert.equal(api.state.current.id,d.id);assert.equal(ids.get('record').value,d.id);assert.equal(ids.get('lead').textContent,d.lead.toUpperCase());
 assert.equal(ids.get('record-title').textContent,d.dataset==='LUDB'?`LUDB 记录 ${d.record} · ${d.lead.toUpperCase()} 导联`:`QTDB ${d.record} · ${d.lead.toUpperCase()} 导联`);
 assert(!ids.get('plot-viewport').hidden);assert.equal(ids.get('error').hidden,true);assert.equal(ids.get('progress').attrs['aria-valuenow'],'3');
 assert.equal(ids.get('export-note').disabled,false);assert(ids.get('plot').innerHTML.includes('<polyline'));assert.equal(api.state.range.join(','),`0,${d.raw.length/d.fs}`);
}
function assertVisibleReferences(d,kind='all',issuesOnly=false){
 const expected=d.coursework.comparison.rows.filter(row=>(kind==='all'||row.type===kind)&&(!issuesOnly||!row.bothWithinLimits));
 const rendered=[...ids.get('comparison-details').innerHTML.matchAll(/data-reference="(\d+)"/g)].map(match=>Number(match[1]));
 assert.equal(rendered.join(','),expected.map(row=>row.referenceIndex).join(','));
 assert.equal(ids.get('comparison-details').innerHTML.includes('当前筛选无条目'),expected.length===0);
 assert(ids.get('comparison-filter-status').textContent.includes(`显示 ${expected.length} / ${d.coursework.comparison.rows.length}`));
 for(const row of expected){const status=row.matched?(row.bothWithinLimits?'双边界在演示阈值内':'边界超出项目展示阈值'):'未配对';assert(ids.get('comparison-details').innerHTML.includes(status));}
}
(async()=>{
 await idle();assert.equal(api.state.current.id,'ludb-16');
 assert.equal(ids.get('demo-count').textContent,`${data.length} 条公开记录 · LUDB ${sourceCounts.LUDB} 条 / QTDB ${sourceCounts.QTDB} 条 · 切换即展示`);
 assert.equal(ids.get('status-label').textContent,'已展示 · 预计算结果');
 const initialRange=api.state.range.join(',');let ordinaryPrevented=false,ctrlPrevented=false;
 ids.get('plot').handlers.wheel({deltaY:-100,clientX:500,ctrlKey:false,preventDefault(){ordinaryPrevented=true;}});
 assert.equal(ordinaryPrevented,false,'ordinary wheel must keep page scrolling');assert.equal(api.state.range.join(','),initialRange,'ordinary wheel must not zoom');
 ids.get('plot').handlers.wheel({deltaY:-100,clientX:500,ctrlKey:true,preventDefault(){ctrlPrevented=true;}});
 assert.equal(ctrlPrevented,true,'Ctrl+wheel owns the zoom gesture');assert(api.state.range[1]-api.state.range[0]<10,'Ctrl+wheel zooms the signal');api.reset();assert.equal(ids.get('record').value,'ludb-16');assertSourceOptions('LUDB');assert.equal(ids.get('progress').attrs['aria-valuenow'],'3');assert(ids.get('plot').innerHTML.includes('<polyline'));assert.equal(ids.get('export-note').disabled,false);
 for(const d of data){await chooseRecord(d);let sharedLimits=null;for(const filtered of [true,false]){api.state.filtered=filtered;api.state.truth=true;api.draw();const svg=ids.get('plot').innerHTML;assert(svg.includes('<polyline'));assert(!/NaN|Infinity|undefined/.test(svg));assert.equal(svg.includes('stroke-dasharray="4 3"'),d.groundTruth.length>0);
   const limits=[api.state.geometry.bottom,api.state.geometry.top];if(sharedLimits)assert.deepStrictEqual(limits,sharedLimits,d.id+' full-window raw/filtered share the Y axis');sharedLimits=limits;
   assert(limits[0]<=Math.min(...d.raw,...d.filtered)&&limits[1]>=Math.max(...d.raw,...d.filtered),d.id+' common limits contain both signals');
  }
  api.setRange(2,4);ids.get('filtered').click();const localLimits=[api.state.geometry.bottom,api.state.geometry.top];ids.get('raw').click();assert.deepStrictEqual([api.state.geometry.bottom,api.state.geometry.top],localLimits,d.id+' zoomed raw/filtered share the Y axis');
  assert(localLimits[0]<=Math.min(...d.raw.slice(500,1001),...d.filtered.slice(500,1001))&&localLimits[1]>=Math.max(...d.raw.slice(500,1001),...d.filtered.slice(500,1001)),d.id+' local common limits contain both signals');api.reset();
  const rows=api.waveRows(d),beats=api.beatRows(d);assert.equal(rows.length,d.raw.length+1);assert.equal(beats.length,d.rPeaks.length+1);assert.equal(rows.slice(1).filter(r=>r.endsWith(',1')).length,new Set(d.rPeaks.map(t=>Math.round(t*d.fs))).size);
  assert.equal(api.qrsRows(d).length,d.coursework.qrs.rows.length+1);
  assert.equal(api.comparisonRows(d).length,d.groundTruth.length+1);
  assert.equal(api.summaryRows(d).length,4);
  for(const exportRows of [beats,api.qrsRows(d),api.comparisonRows(d),api.summaryRows(d)]){
   const columns=exportRows[0].split(',').length;assert(exportRows.every(row=>row.split(',').length===columns));assert(!exportRows.join('\n').match(/NaN|undefined|Infinity/));
  }
  assert(ids.get('qrs-summary').textContent.includes(d.coursework.qrs.summary.meanMs==null?'—':d.coursework.qrs.summary.meanMs.toFixed(1)));assert(ids.get('qrs-count').textContent.includes('模型边界步进约 20 毫秒'));assert(ids.get('statistics-scope').textContent.includes('未逐峰人工核验'));
  assert.equal((ids.get('qrs-table').innerHTML.match(/data-qrs=/g)||[]).length,d.coursework.qrs.rows.length);
  assert(ids.get('comparison-details').innerHTML.includes('<tr>'));assertVisibleReferences(d);
  assert(!/NaN|undefined|Infinity/.test(ids.get('comparison-table').innerHTML));
  assert.equal(ids.get('comparison-table').innerHTML.includes('不可评价'),d.coursework.comparison.summaries.some(summary=>summary.referenceCount===0));
  for(const [id,expected] of [['export-qrs',api.qrsRows(d)],['export-comparison',api.comparisonRows(d)],['export-summary',api.summaryRows(d)],['export-beats',beats]]){
   const count=downloads.length;ids.get(id).click();assert.equal(downloads.length,count+1);
   const csv=(await downloads.at(-1).text()).replace(/^\uFEFF/,'');assert.equal(csv,expected.join('\r\n'));
  }
  if(d.coursework.qrs.rows.length){
   assert(api.focusExample('qrs'));assert(api.state.range[1]-api.state.range[0]<1.1);
   assert(ids.get('focus-note').textContent.includes('估计时限'));
   assert(ids.get('plot').innerHTML.includes('data-focused="prediction"'));
  }else{assert(ids.get('focus-qrs').disabled);assert.equal(api.focusExample('qrs'),false);}
  const first=d.coursework.comparison.rows[0];
  if(first){
   ids.get('comparison-details').handlers.click({target:{closest:()=>({dataset:{reference:String(first.referenceIndex)}})}});
   assert.equal(api.state.focus.referenceIndex,first.referenceIndex);assert(api.state.truth);
   assert(ids.get('plot').innerHTML.includes('data-focused="reference"'));
   assert(ids.get('comparison-details').innerHTML.includes('selected-row'));
   assert(api.state.range[0]<=first.referenceStartSec&&api.state.range[1]>=first.referenceEndSec);
  }else{assert(ids.get('focus-comparison').disabled);assert.equal(api.focusExample('comparison'),false);assert(ids.get('comparison-table').innerHTML.includes('不可评价'));}
  const lastQrs=d.coursework.qrs.rows.at(-1);
  if(lastQrs){ids.get('qrs-table').handlers.click({target:{closest:()=>({dataset:{qrs:String(lastQrs.qrsNumber)}})}});assert.equal(api.state.focus.predictionIndex,lastQrs.predictionIndex);}
  assert(api.state.range[0]>=0&&api.state.range[1]<=10);
  assert.equal(api.focusQrs(-1),false);assert.equal(api.focusReference(-1),false);
  ids.get('comparison-kind').value='QRS';ids.get('comparison-kind').handlers.change();
  assertVisibleReferences(d,'QRS');
  const fullExport=api.comparisonRows(d).join('\n');
  ids.get('comparison-issues').checked=true;ids.get('comparison-issues').handlers.change();
  assertVisibleReferences(d,'QRS',true);
  assert.equal(api.comparisonRows(d).join('\n'),fullExport);
  ids.get('comparison-kind').value='T';ids.get('comparison-kind').handlers.change();
  assertVisibleReferences(d,'T',true);
  ids.get('comparison-kind').value='all';ids.get('comparison-kind').handlers.change();
  ids.get('comparison-issues').checked=false;ids.get('comparison-issues').handlers.change();
  assertVisibleReferences(d);
  const svg=api.waveformSvg();assert(svg.startsWith('<?xml'));assert(svg.includes('xmlns="http://www.w3.org/2000/svg"'));
  assert(svg.includes(d.id)&&svg.includes('预计算演示'));assert(!/id="(?:selection|crosshair|hover-dot)"|<script\b|NaN|undefined|Infinity/.test(svg));
  const downloadCount=downloads.length;ids.get('export-svg').click();assert.equal(downloads.length,downloadCount+1);
  assert.equal(downloads.at(-1).type,'image/svg+xml;charset=utf-8');assert.equal(await downloads.at(-1).text(),svg);
  const note=api.summaryNote();assert(note.includes(d.id)&&note.includes(d.model)&&note.includes('不计算准确率')&&note.includes('预计算静态演示'));
  assert(note.includes(`原采样率 ${d.sourceFs}`)&&note.includes(`展示采样率 ${d.fs}`)&&note.includes(`QRS：人工 ${d.coursework.comparison.summaries[1].referenceCount}`));
  assert(note.includes('60/RR')&&note.includes('模型边界步进约 20 毫秒')&&note.includes('未逐峰人工核验')&&note.includes('双边界在演示阈值内'));assert(!/NaN|undefined|Infinity/.test(note));
  const noteCount=downloads.length;ids.get('export-note').click();assert.equal(downloads.length,noteCount+1);assert.equal(downloads.at(-1).type,'text/plain;charset=utf-8');assert.equal((await downloads.at(-1).text()).replace(/^\uFEFF/,''),note);
  api.setRange(1,2);ids.get('comparison-kind').value='QRS';ids.get('comparison-kind').handlers.change();ids.get('comparison-issues').checked=true;ids.get('comparison-issues').handlers.change();assert.equal(api.summaryNote(),note);
  api.reset();assert.equal(api.state.focus,null);assert.equal(ids.get('focus-note').textContent,'');
  api.zoom(.1,5);assert(api.state.range[1]-api.state.range[0]<1.01);api.setRange(-10,-9);assert(api.state.range[0]>=0);api.setRange(99,110);assert(api.state.range[1]<=d.raw.length/d.fs);
  api.setRange(4,2);assert.equal(api.state.range.join(','),'2,4');const validRange=api.state.range.join(',');
  for(const limits of [[NaN,5],[0,Infinity],[undefined,1],['2',4]]){assert.equal(api.setRange(...limits),false);assert.equal(api.state.range.join(','),validRange);}
  for(const [factor,anchor] of [[0,3],[-1,3],[Infinity,3],[.8,NaN]]){assert.equal(api.zoom(factor,anchor),false);assert.equal(api.state.range.join(','),validRange);}
  ids.get('plot').handlers.pointermove({clientX:500});assert.equal(ids.get('crosshair').attrs.visibility,'visible');assert(ids.get('readout').textContent.includes('毫伏'));
  ids.get('raw').click();assert.equal(ids.get('crosshair').attrs.visibility,'hidden');assert.equal(ids.get('hover-dot').attrs.visibility,'hidden');assert.equal(ids.get('readout').textContent,'移动指针查看时间与幅值');
  ids.get('plot').handlers.pointermove({clientX:500});ids.get('plot').handlers.pointercancel();assert.equal(ids.get('crosshair').attrs.visibility,'hidden');
  api.reset();assert.equal(api.state.range[1],10);console.log(d.id,'waveforms with shared Y limits, table-to-plot focus, filters, CSV/SVG/TXT export, valid ranges and stale-hover cleanup passed');
 }
 if(api.state.source!=='LUDB'){tabs[0].click();assertClearedDuringLoad();await idle();}
 tabs[1].click();assertClearedDuringLoad();
 await idle();assert(api.state.current.id.startsWith('qtdb-'));assert.equal(api.state.focus,null);assert.equal(api.state.comparisonKind,'all');assert.equal(api.state.issuesOnly,false);
 ids.get('record').value='qtdb-sel103';ids.get('record').handlers.change();await idle();assert.equal(api.state.current.id,'qtdb-sel103');
 waves[0].click();assert.equal(api.state.flags.P,false);ids.get('truth').click();assert.equal(api.state.truth,true);ids.get('raw').click();assert.equal(api.state.filtered,false);
 const before=api.state.range[1]-api.state.range[0];ids.get('plot').handlers.keydown({key:'+',preventDefault(){}});assert(api.state.range[1]-api.state.range[0]<before);
 assert.throws(()=>api.validate({...data[0],raw:[NaN]}));
 const mutations=[
  ['missing comparison rows',r=>delete r.coursework.comparison.rows],
  ['missing QRS summary',r=>delete r.coursework.qrs.summary],
  ['invalid lead',r=>r.lead=null],
  ['invalid record label',r=>r.record={}],
  ['invalid source rate',r=>r.sourceFs=0],
  ['missing metrics',r=>delete r.metrics],
  ['invalid RR',r=>r.rr[0]=-1],
  ['null interval',r=>r.waves[0]=null],
  ['reversed interval',r=>r.waves[0].end=r.waves[0].start],
  ['out-of-window reference',r=>r.groundTruth[0].end=11],
  ['duplicate R peaks',r=>r.rPeaks[1]=r.rPeaks[0]],
  ['missing thresholds',r=>delete r.coursework.protocol.boundaryLimitsMs.QRS],
  ['invalid measurement',r=>r.coursework.qrs.rows[0].durationMs='broken'],
  ['invalid QRS index',r=>r.coursework.qrs.rows[0].predictionIndex=999],
  ['invalid reference index',r=>r.coursework.comparison.rows[0].referenceIndex=999],
  ['invalid pairing flag',r=>r.coursework.comparison.rows[0].matched='true'],
  ['invalid comparison summary',r=>r.coursework.comparison.summaries[0].onsetMaeMs=null],
 ];
 const preserved=api.records[0];
 for(const [name,mutate] of mutations){
  const broken=JSON.parse(JSON.stringify(data[0]));mutate(broken);assert.throws(()=>api.validate(broken),undefined,name);
  api.records[0]=broken;api.state.selected=broken.id;await api.load();
  assert.equal(api.state.current,null,name);assert.equal(api.state.busy,false,name);assert.equal(ids.get('error').hidden,false,name);assert(ids.get('error').textContent.includes('切换另一条记录'),name);
  assert.equal(ids.get('status-label').textContent,'加载失败');assert.equal(ids.get('plot').innerHTML,'');assert.equal(api.state.geometry,null);assert.equal(api.state.focus,null);assert.equal(ids.get('readout').textContent,'');assert(ids.get('plot-viewport').hidden);
  for(const id of ['export-wave','export-beats','export-qrs','export-comparison','export-summary','export-svg','export-note','focus-qrs','focus-comparison'])assert(ids.get(id).disabled,id+' after '+name);
  const count=downloads.length;ids.get('export-note').click();assert.equal(downloads.length,count);assert.equal(api.summaryNote(),null);
  api.state.selected=data[1].id;await api.load();assert.equal(api.state.current.id,data[1].id,'next record recovery after '+name);assert.equal(ids.get('error').hidden,true);assert.equal(ids.get('export-note').disabled,false);
 }
 api.records[0]=null;api.state.selected=preserved.id;await api.load();assert.equal(ids.get('error').hidden,false);assert.equal(api.state.busy,false);
 api.records[0]=preserved;api.state.selected='missing-record';await api.load();assert.equal(ids.get('error').hidden,false);assert.equal(ids.get('record-title').textContent,'心电演示记录');
 api.state.selected=data[0].id;await api.load();assert.equal(api.state.current.id,data[0].id);assert.equal(ids.get('record').disabled,false);assert.equal(ids.get('load').disabled,false);
 // A render failure must use the same recovery path, without trying to render corrupt data again.
 const qrsSummary=ids.get('qrs-summary');let summaryText=qrsSummary.textContent,failOnce=true;
 Object.defineProperty(qrsSummary,'textContent',{configurable:true,get:()=>summaryText,set:value=>{if(failOnce&&value.startsWith('平均')){failOnce=false;throw Error('Injected renderer failure');}summaryText=value;}});
 await api.load();assert.equal(api.state.current,null);assert(ids.get('error').textContent.includes('Injected renderer failure'));assert.equal(api.state.busy,false);
 await api.load();assert.equal(api.state.current.id,data[0].id);assert.equal(ids.get('error').hidden,true);
 const originalCurrent=api.state.current;api.state.current={...originalCurrent,raw:originalCurrent.raw.slice(0,10),filtered:originalCurrent.filtered.slice(0,10)};
 api.setRange(0,1);assert.equal(api.state.range[1],10/originalCurrent.fs);assert(api.state.range[0]>=0);assert(!/NaN|Infinity/.test(ids.get('plot').innerHTML));api.state.current=originalCurrent;api.reset();
 console.log(mutations.length,'corrupt-record load paths, unknown selection, renderer failure and next-record recovery passed');
 for(const malformed of ['{broken','null','{}','[]']){
  ids.get('demo-data').textContent=malformed;
  const fresh={document,console,Blob,URL:downloadURL,setTimeout:cb=>cb(),requestAnimationFrame:cb=>setImmediate(cb)};fresh.globalThis=fresh;vm.createContext(fresh);vm.runInContext(code,fresh);await idle(fresh.api);
  assert.equal(fresh.api.state.current,null);assert.equal(ids.get('error').hidden,false);assert(ids.get('error').textContent.includes('内置示例数据无法读取'));assert(ids.get('export-note').disabled);
 }
 console.log('malformed embedded JSON, non-array/empty data and sub-minimum window guards passed');
 console.log('selection clears stale result; controls, keyboard zoom and invalid-data guards passed');
 console.log(data.length,'records auto-displayed through actual record change events without clicking reload;',JSON.stringify(sourceCounts));
 console.log('single-file offline packaging passed; browser visual QA not performed');
})().catch(err=>{console.error(err);process.exitCode=1;});
