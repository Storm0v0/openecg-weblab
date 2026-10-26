'use strict';
(() => {
let records=[],dataError=null;
try{const parsed=JSON.parse(document.getElementById('demo-data').textContent);if(!Array.isArray(parsed)||!parsed.length)throw Error();records=parsed;}catch{dataError='内置示例数据无法读取，请使用完整的演示文件。';}
const $ = id => document.getElementById(id);
const colors = {P:'#e88089',QRS:'#45a5d1',T:'#39b497',R:'#e6a044'};
const state = {source:'APPLEWATCH',selected:'applewatch-a',current:null,filtered:true,truth:false,flags:{P:true,QRS:true,T:true,R:true},range:[0,10],busy:false,drag:null,geometry:null,focus:null,comparisonKind:'all',issuesOnly:false};
const plot = $('plot');
const sourceNames={LUDB:'LUDB',QTDB:'QTDB',APPLEWATCH:'Apple Watch'};
const sourceTabs={LUDB:'tab-ludb',QTDB:'tab-qtdb',APPLEWATCH:'tab-applewatch'};
function isAppleWatch(d=state.current){return d?.dataset==='APPLEWATCH';}
function sourceName(source){return sourceNames[source]||source;}
function unitName(d=state.current){return isAppleWatch(d)?'相对毫伏':'毫伏';}
function inputName(d=state.current){return isAppleWatch(d)?'PDF重建信号':'原始信号';}
function sourceWindowLabel(d){const w=isAppleWatch(d)?d.pdfReconstruction.windowSec:[d.startSec,d.startSec+d.raw.length/d.fs];return `${Number(w[0])}–${Number(w[1])}`;}
function duplicateNote(d){const id=d?.pdfReconstruction?.duplicateOf;return id?`${records.find(r=>r.id===id)?.record||id} 的重复导出`:'';}
function label(d) { return d && typeof d.record==='string' ? isAppleWatch(d)?`Apple Watch 匿名记录 ${d.record}${duplicateNote(d)?'（'+duplicateNote(d)+'）':''}`:`${d.dataset==='LUDB'?'LUDB 记录':'QTDB'} ${d.record} · ${typeof d.lead==='string'?d.lead.toUpperCase():'未知'} 导联` : '本地心电演示记录'; }
function stage(n, failed=false) {
 $('progress').setAttribute('aria-valuenow',String(n)); $('progress-fill').style.width=`${n/3*100}%`;
 $('status-label').textContent = failed ? '加载失败' : n===3 ? '已展示' : n===2 ? '校验并绘制…' : n===1 ? '读取内置结果…' : '等待加载';
 [...$('steps').children].forEach((li,i)=>{li.classList.toggle('done',n>i);li.querySelector('span').textContent=n>i?'✓':String(i+1);});
}
function selectedRecord() { return records.find(d=>d?.id===state.selected); }
function populate() {
 $('record').replaceChildren(...records.filter(d=>d?.dataset===state.source).map(d=>{const option=document.createElement('option');option.value=d.id;option.textContent=label(d);return option;}));
 $('record').value=state.selected; $('lead').textContent=selectedRecord()?.lead?.toUpperCase()||'—';
 document.querySelectorAll('[data-source]').forEach(b=>{const active=b.dataset.source===state.source,count=records.filter(d=>d?.dataset===b.dataset.source).length;b.textContent=`${sourceName(b.dataset.source)} · ${count} 条`;b.setAttribute('aria-label',`${sourceName(b.dataset.source)}，${count} 条演示记录，选择后自动展示`);b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;});
 $('demo-count').textContent=`${records.length} 条演示记录`;
 $('record-panel').setAttribute('aria-labelledby',sourceTabs[state.source]);
}
function updateControls() {
 ['raw','filtered'].forEach(id=>{const on=id==='filtered'?state.filtered:!state.filtered;$(id).classList.toggle('active',on);$(id).setAttribute('aria-pressed',String(on));$(id).disabled=!state.current;});
 document.querySelectorAll('[data-wave]').forEach(b=>{const on=state.flags[b.dataset.wave];b.classList.toggle('enabled',on);b.setAttribute('aria-pressed',String(on));b.disabled=!state.current;});
 $('truth').classList.toggle('enabled',state.truth);$('truth').setAttribute('aria-pressed',String(state.truth));$('truth').disabled=!state.current?.groundTruth?.length;
 ['export-beats','export-wave','export-qrs','export-comparison','export-summary','export-svg','export-note','reset','comparison-kind','comparison-issues'].forEach(id=>$(id).disabled=!state.current||state.busy);
 $('focus-qrs').disabled=!state.current?.coursework?.qrs?.rows?.length||state.busy;
 $('focus-comparison').disabled=!state.current?.coursework?.comparison?.rows?.length||state.busy;
 $('comparison-kind').disabled=!state.current?.groundTruth?.length||state.busy;$('comparison-issues').disabled=!state.current?.groundTruth?.length||state.busy;
 $('record').disabled=state.busy;$('load').disabled=state.busy;
 document.querySelectorAll('[data-source]').forEach(b=>b.disabled=state.busy);
}
function updateInfo() {
 const d=state.current;
 $('record-title').textContent=label(d || selectedRecord());$('dataset').textContent=`心电波形 · ${sourceName(d?.dataset || state.source)}`;
 $('record-meta').textContent=d?(isAppleWatch(d)?`PDF 曲线重建 · 相对 mV · I 导联 · 原窗 ${sourceWindowLabel(d)} 秒`:`${d.fs} Hz · ${d.raw.length/d.fs} 秒 · 原记录起点 ${d.startSec} 秒`):'';
 $('lead').textContent=(d||selectedRecord())?.lead?.toUpperCase()||'—';
 $('raw').textContent=inputName(d);
 $('applewatch-methods').hidden=!isAppleWatch(d);$('public-methods').hidden=!d||isAppleWatch(d);
 $('applewatch-window-method').textContent=isAppleWatch(d)?`原窗 ${sourceWindowLabel(d)} 秒 · ${d.sourceFs} → ${d.fs} Hz · ${d.raw.length} 点`:'';
 $('statistics-scope').textContent=d?`整段 ${d.raw.length/d.fs} 秒统计`:'等待加载记录统计';
 $('badge').textContent=d?'分析结果':'待加载';
 const metricUnits={averageHr:'次/分',minHr:'次/分',maxHr:'次/分',meanRr:'秒',rPeakCount:'个'};
 for(const [key,unit] of Object.entries(metricUnits)) { const el=$(key);el.replaceChildren(); const v=d?.metrics?.[key];el.append(document.createTextNode(v==null?'—':String(v)));if(v!=null){const em=document.createElement('em');em.textContent=unit;el.append(em);} }
 $('result-info').textContent=d?`${d.model} · ${d.waves.length} 个波形区间 · ${d.rPeaks.length} 个 R 峰`:'结果尚未加载';
 $('plot-viewport').hidden=!d;$('empty').hidden=!!d;$('readout').textContent=d?'移动指针查看时间与幅值':'';
 if(!d)$('range-label').textContent='等待加载';updateMeasurements();updateControls();
}
function number(value,digits=1){return value==null?'—':Number(value).toFixed(digits);}
function percent(value){return value==null?'不可评价':number(value)+'%';}
function associationLabel(row){
 const labels={'unique':'R 峰已唯一配对','no-peak':'区间内未检测到 R 峰','multiple-peaks':'区间内有多个 R 峰','shared-peak':'同一 R 峰落入多个 QRS'};
 if(labels[row.rPeakAssociation])return labels[row.rPeakAssociation];
 if(row.rPeakSec!=null)return 'R 峰已唯一配对';
 if(!row.rPeakCountInInterval)return '区间内未检测到 R 峰';
 if(row.rPeakCountInInterval>1)return '区间内有多个 R 峰';
 return 'R 峰归属有歧义';
}
function updateMeasurements(){
 const d=state.current,c=d?.coursework;
 $('qrs-summary').textContent=c?`平均 ${number(c.qrs.summary.meanMs)} 毫秒 · 中位数 ${number(c.qrs.summary.medianMs)} 毫秒 · 范围 ${number(c.qrs.summary.minMs)}–${number(c.qrs.summary.maxMs)} 毫秒`:'加载记录后显示 QRS 时限统计';
 $('qrs-count').textContent=c?`${c.qrs.summary.totalCount} 个预测区间 · 纳入 ${c.qrs.summary.includedCount} 个 · 边缘排除 ${c.qrs.summary.edgeExcludedCount} 个`:'结果尚未加载';
 $('qrs-table').innerHTML=c?c.qrs.rows.map(r=>`<tr${state.focus?.predictionIndex===r.predictionIndex?' class="selected-row"':''}><td><button type="button" class="table-jump" data-qrs="${r.qrsNumber}" aria-label="定位第 ${r.qrsNumber} 个 QRS">${r.qrsNumber} · 定位</button></td><td>${number(r.startSec,3)}</td><td>${number(r.endSec,3)}</td><td>${number(r.rPeakSec,3)}</td><td>${number(r.durationMs)}</td><td><span class="status-chip${r.edgeClipped?' caution':''}">${r.edgeClipped?'边缘排除':'纳入时限统计'}</span><small class="association-note">${associationLabel(r)}</small></td></tr>`).join(''):'<tr><td colspan="6">等待加载</td></tr>';
 $('comparison-table').innerHTML=c?(isAppleWatch(d)&&!d.groundTruth.length?c.comparison.summaries.map(s=>`<tr><th scope="row">${s.type}</th><td>无人工标注</td><td>不可评价</td><td>不可评价</td><td>不可评价</td><td>不可评价</td><td>不可评价</td><td>${s.predictionCount}（未评分）</td></tr>`).join(''):c.comparison.summaries.map(s=>`<tr><th scope="row">${s.type}</th><td>${s.matchedCount} / ${s.referenceCount}</td><td>${percent(s.pairingRatePct)}</td><td>${number(s.onsetMaeMs)}</td><td>${number(s.offsetMaeMs)}</td><td>${number(s.durationMaeMs)}</td><td>${s.referenceCount?`${s.bothWithinCount} / ${s.referenceCount}（${percent(s.bothWithinRatePct)}）`:'不可评价'}</td><td>${s.unscoredPredictionCount}</td></tr>`).join('')):'<tr><td colspan="8">等待加载</td></tr>';
 $('comparison-kind').value=state.comparisonKind;$('comparison-issues').checked=state.issuesOnly;
 renderReferenceRows();
 $('comparison-status').textContent=c?(isAppleWatch(d)&&!d.groundTruth.length?'无人工标注 · 不可评价':`${c.comparison.rows.length} 个人工区间`):'加载记录后显示人工标注对照';
}
function renderReferenceRows(){
 const all=state.current?.coursework.comparison.rows;
 if(!all){$('comparison-details').innerHTML='<tr><td colspan="8">等待加载</td></tr>';$('comparison-filter-status').textContent='';return;}
 if(isAppleWatch()&&!all.length){$('comparison-details').innerHTML='<tr><td colspan="8">无人工标注 · 不可评价</td></tr>';$('comparison-filter-status').textContent='';return;}
 const rows=all.filter(r=>(state.comparisonKind==='all'||r.type===state.comparisonKind)&&(!state.issuesOnly||!r.bothWithinLimits));
 const hasClass=state.comparisonKind==='all'||all.some(r=>r.type===state.comparisonKind);
 $('comparison-details').innerHTML=rows.length?rows.map(r=>`<tr${state.focus?.referenceIndex===r.referenceIndex?' class="selected-row"':''}><td><button type="button" class="table-jump" data-reference="${r.referenceIndex}" aria-label="定位第 ${r.referenceIndex} 个人工 ${r.type} 区间">${r.referenceIndex} · 定位</button></td><td>${r.type}</td><td>${number(r.referenceStartSec,3)}–${number(r.referenceEndSec,3)}</td><td>${r.matched?`${number(r.predictionStartSec,3)}–${number(r.predictionEndSec,3)}`:'未配对'}</td><td>${number(r.onsetErrorMs)}</td><td>${number(r.offsetErrorMs)}</td><td>${number(r.durationErrorMs)}</td><td><span class="status-chip${r.bothWithinLimits?'':' caution'}">${r.matched?(r.bothWithinLimits?'双边界在演示阈值内':'边界超出项目展示阈值'):'未配对'}</span></td></tr>`).join(''):`<tr><td colspan="8">${hasClass?'当前筛选无条目':'无该类人工标注'}</td></tr>`;
 $('comparison-filter-status').textContent=`${rows.length} / ${all.length} 个人工区间`;
}
function hideHover(){for(const id of ['selection','crosshair','hover-dot'])if($(id))$(id).setAttribute('visibility','hidden');$('readout').textContent=state.current?'移动指针查看时间与幅值':'';}
function clearResult() {state.current=null;state.truth=false;state.drag=null;state.geometry=null;state.focus=null;state.comparisonKind='all';state.issuesOnly=false;hideHover();plot.innerHTML='';$('focus-note').textContent='';$('error').hidden=true;stage(0);updateInfo();}
function validate(d) {
 if(!d||!Number.isFinite(d.fs)||d.fs<=0||!Array.isArray(d.raw)||!Array.isArray(d.filtered)||d.raw.length<2||d.raw.length!==d.filtered.length)throw Error('示例数据格式不完整。');
 for(const a of [d.raw,d.filtered])if(!a.every(Number.isFinite))throw Error('示例中存在无效采样值。');
 if(![d.waves,d.groundTruth,d.rPeaks,d.rr].every(Array.isArray))throw Error('示例标注数据缺失。');
 const ensure=(ok,message)=>{if(!ok)throw Error(message);},finite=Number.isFinite,count=v=>Number.isInteger(v)&&v>=0,text=v=>typeof v==='string'&&v.trim().length>0;
 const total=d.raw.length/d.fs,kinds=['P','QRS','T'],interval=(a,b)=>finite(a)&&finite(b)&&a>=0&&a<b&&b<=total;
 if(isAppleWatch(d)){const w=d.pdfReconstruction?.windowSec;ensure(Array.isArray(w)&&w.length===2&&w.every(finite)&&w[0]>=0&&Math.abs(w[0]-d.startSec)<1e-9&&Math.abs(w[1]-w[0]-total)<1e-9,'PDF 曲线重建的原窗与当前片段不一致。');}
 ensure(finite(total)&&total>0&&text(d.id)&&/^[a-z0-9-]+$/.test(d.id)&&['LUDB','QTDB','APPLEWATCH'].includes(d.dataset)&&text(d.record)&&text(d.lead)&&text(d.model)&&finite(d.sourceFs)&&d.sourceFs>0&&finite(d.startSec)&&d.startSec>=0&&d.unit==='mV'&&d.mode==='precomputed','示例记录元数据不完整。');
 for(const waves of [d.waves,d.groundTruth])ensure(waves.every(w=>w&&kinds.includes(w.type)&&interval(w.start,w.end)),'示例波形区间无效或超出记录范围。');
 ensure(d.rPeaks.every((t,i)=>finite(t)&&t>=0&&t<total&&(!i||t>d.rPeaks[i-1]))&&d.rr.length===Math.max(0,d.rPeaks.length-1)&&d.rr.every(t=>finite(t)&&t>0),'示例 R 峰或 RR 间期无效。');
 const metrics=d.metrics;
 ensure(metrics&&metrics.rPeakCount===d.rPeaks.length&&['averageHr','minHr','maxHr','meanRr'].every(k=>d.rr.length?finite(metrics[k])&&metrics[k]>0:metrics[k]===null),'示例心率指标缺失或无效。');
 const c=d.coursework,p=c?.protocol,q=c?.qrs,comparison=c?.comparison;
 ensure(c?.protocolVersion==='coursework-v1'&&c.recordId===d.id&&text(c.implementationRevision)&&Array.isArray(q?.rows)&&q.summary&&Array.isArray(comparison?.rows)&&Array.isArray(comparison?.summaries),'示例测量与对照结果缺失。');
 ensure(p&&finite(p.matchCenterLimitMs)&&p.matchCenterLimitMs>0&&p.positiveOverlapRequired===true&&kinds.every(k=>finite(p.boundaryLimitsMs?.[k]?.onset)&&p.boundaryLimitsMs[k].onset>0&&finite(p.boundaryLimitsMs[k].offset)&&p.boundaryLimitsMs[k].offset>0),'示例配对协议或边界阈值缺失。');
 const waveAt=(index,waves)=>Number.isInteger(index)&&index>=1&&index<=waves.length?waves[index-1]:null;
 const qrsIndices=new Set();
 for(const [i,r] of q.rows.entries()){
  const w=r&&waveAt(r.predictionIndex,d.waves);
  ensure(r&&r.qrsNumber===i+1&&w?.type==='QRS'&&!qrsIndices.has(r.predictionIndex)&&r.startSec===w.start&&r.endSec===w.end&&finite(r.durationMs)&&r.durationMs>0&&typeof r.edgeClipped==='boolean'&&r.includedInStats===!r.edgeClipped&&count(r.rPeakCountInInterval)&&['unique','no-peak','multiple-peaks','shared-peak'].includes(r.rPeakAssociation),'示例 QRS 测量字段无效。');
  ensure(r.rPeakAssociation==='unique'?finite(r.rPeakSec)&&d.rPeaks.includes(r.rPeakSec)&&r.rPeakSec>=r.startSec-1e-8&&r.rPeakSec<=r.endSec+1e-8&&r.rPeakCountInInterval===1:r.rPeakSec===null,'示例 QRS 与 R 峰配对字段无效。');
  ensure(r.rPeakAssociation==='no-peak'?r.rPeakCountInInterval===0:r.rPeakAssociation==='multiple-peaks'?r.rPeakCountInInterval>1:r.rPeakCountInInterval===1,'示例 QRS 的 R 峰配对状态不一致。');
  qrsIndices.add(r.predictionIndex);
 }
 const qs=q.summary;
 ensure(['totalCount','includedCount','edgeExcludedCount'].every(k=>count(qs[k]))&&qs.totalCount===q.rows.length&&qs.totalCount===d.waves.filter(w=>w.type==='QRS').length&&qs.includedCount===q.rows.filter(r=>r.includedInStats).length&&qs.edgeExcludedCount+qs.includedCount===qs.totalCount&&finite(qs.sampleStepMs)&&qs.sampleStepMs>0&&['meanMs','medianMs','minMs','maxMs'].every(k=>qs.includedCount?finite(qs[k])&&qs[k]>0:qs[k]===null),'示例 QRS 汇总字段无效。');
 const references=new Set(),predictions=new Set();
 for(const r of comparison.rows){
  const ref=r&&waveAt(r.referenceIndex,d.groundTruth),pred=r&&waveAt(r.predictionIndex,d.waves);
  ensure(r&&ref&&!references.has(r.referenceIndex)&&r.type===ref.type&&r.referenceStartSec===ref.start&&r.referenceEndSec===ref.end&&finite(r.referenceDurationMs)&&r.referenceDurationMs>0&&['matched','onsetWithinLimit','offsetWithinLimit','bothWithinLimits'].every(k=>typeof r[k]==='boolean'),'示例人工对照明细字段无效。');
  const values=['predictionStartSec','predictionEndSec','predictionDurationMs','onsetErrorMs','offsetErrorMs','durationErrorMs'];
  ensure(r.matched?pred&&pred.type===ref.type&&!predictions.has(r.predictionIndex)&&r.predictionStartSec===pred.start&&r.predictionEndSec===pred.end&&values.every(k=>finite(r[k]))&&r.predictionDurationMs>0:r.predictionIndex===null&&values.every(k=>r[k]===null)&&!r.onsetWithinLimit&&!r.offsetWithinLimit&&!r.bothWithinLimits,'示例人工对照配对字段无效。');
  ensure(r.bothWithinLimits===(r.onsetWithinLimit&&r.offsetWithinLimit),'示例双边界状态无效。');
  references.add(r.referenceIndex);if(r.matched)predictions.add(r.predictionIndex);
 }
 ensure(references.size===d.groundTruth.length&&comparison.summaries.length===kinds.length&&new Set(comparison.summaries.map(s=>s?.type)).size===kinds.length,'示例人工对照条目不完整。');
 for(const s of comparison.summaries){
  const rows=comparison.rows.filter(r=>r.type===s?.type),limit=p.boundaryLimitsMs[s?.type];
  ensure(s&&kinds.includes(s.type)&&['referenceCount','predictionCount','matchedCount','unmatchedReferenceCount','unscoredPredictionCount','bothWithinCount'].every(k=>count(s[k]))&&s.referenceCount===rows.length&&s.predictionCount===d.waves.filter(w=>w.type===s.type).length&&s.matchedCount===rows.filter(r=>r.matched).length&&s.unmatchedReferenceCount===s.referenceCount-s.matchedCount&&s.unscoredPredictionCount===s.predictionCount-s.matchedCount&&s.bothWithinCount===rows.filter(r=>r.bothWithinLimits).length&&s.onsetLimitMs===limit.onset&&s.offsetLimitMs===limit.offset,'示例人工对照汇总字段无效。');
  ensure(['pairingRatePct','bothWithinRatePct'].every(k=>s.referenceCount?finite(s[k])&&s[k]>=0&&s[k]<=100:s[k]===null)&&['onsetMaeMs','offsetMaeMs','durationMaeMs','onsetBiasMs','offsetBiasMs'].every(k=>s.matchedCount?finite(s[k])&&(k.includes('Bias')||s[k]>=0):s[k]===null),'示例人工对照误差或比例无效。');
 }
 return true;
}
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
async function load() {
 if(state.busy)return;state.busy=true;clearResult();
 try { stage(1);await nextFrame();if(dataError)throw Error(dataError);const d=selectedRecord();validate(d);stage(2);state.current=d;state.range=[0,d.raw.length/d.fs];state.truth=false;state.drag=null;state.focus=null;$('focus-note').textContent='';updateInfo();draw();await nextFrame();stage(3); }
 catch(e){clearResult();stage(0,true);$('error').textContent=`${e?.message || '无法显示示例。'} 请重新加载，或切换另一条记录。`;$('error').hidden=false;}
 finally{state.busy=false;updateControls();}
}
function draw() {
 const d=state.current;if(!d)return;const values=state.filtered?d.filtered:d.raw;
 const [a,b]=state.range;const start=Math.max(0,Math.floor(a*d.fs)),end=Math.min(values.length,Math.ceil(b*d.fs)+1);
 const samples=values.slice(start,end),rawWindow=d.raw.slice(start,end),filteredWindow=d.filtered.slice(start,end);const low=Math.min(...rawWindow,...filteredWindow),high=Math.max(...rawWindow,...filteredWindow),spread=Math.max(.1,high-low),bottom=low-spread*.15,top=high+spread*.15;
 const left=66,right=938,upper=28,lower=344,width=right-left,height=lower-upper;
 const x=t=>left+(t-a)/(b-a)*width,y=v=>lower-(v-bottom)/(top-bottom)*height;
 state.geometry={left,right,upper,lower,width,height,bottom,top,x,y};const svg=[];
 svg.push('<defs><clipPath id="chart-clip"><rect x="66" y="28" width="872" height="316"/></clipPath></defs>');
 for(let i=0;i<=5;i++){const t=a+(b-a)*i/5;svg.push(`<line x1="${x(t)}" x2="${x(t)}" y1="28" y2="344" stroke="#e6eef2"/><text x="${x(t)}" y="367" text-anchor="middle" fill="#68818e" font-size="13">${t.toFixed(2)}</text>`);}
 for(let i=0;i<=4;i++){const v=bottom+(top-bottom)*i/4;svg.push(`<line x1="66" x2="938" y1="${y(v)}" y2="${y(v)}" stroke="#e6eef2"/><text x="56" y="${y(v)+4}" text-anchor="end" fill="#68818e" font-size="13">${v.toFixed(2)}</text>`);}
 svg.push('<g clip-path="url(#chart-clip)">');
 for(const w of d.waves)if(state.flags[w.type]&&w.end>=a&&w.start<=b)svg.push(`<rect x="${x(w.start)}" width="${Math.max(0,x(w.end)-x(w.start))}" y="28" height="316" fill="${colors[w.type]}" opacity=".16"/>`);
 if(state.truth)for(const w of d.groundTruth)if(state.flags[w.type]&&w.end>=a&&w.start<=b)svg.push(`<rect x="${x(w.start)}" width="${Math.max(0,x(w.end)-x(w.start))}" y="28" height="316" fill="none" stroke="${colors[w.type]}" stroke-width="1.2" stroke-dasharray="4 3"/>`);
 if(state.focus){
  const f=state.focus,p=f.predictionIndex?d.waves[f.predictionIndex-1]:null,r=f.referenceIndex?d.groundTruth[f.referenceIndex-1]:null;
  if(p&&state.flags[p.type])svg.push(`<rect data-focused="prediction" x="${x(p.start)}" width="${Math.max(0,x(p.end)-x(p.start))}" y="30" height="312" fill="none" stroke="#126078" stroke-width="2.4"/>`);
  if(r&&state.truth&&state.flags[r.type])svg.push(`<rect data-focused="reference" x="${x(r.start)}" width="${Math.max(0,x(r.end)-x(r.start))}" y="34" height="304" fill="none" stroke="#6b497e" stroke-width="2" stroke-dasharray="5 3"/>`);
 }
 svg.push(`<polyline points="${samples.map((v,i)=>`${x((start+i)/d.fs).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}" fill="none" stroke="#174d62" stroke-width="1.7" stroke-linejoin="round"/>`);
 if(state.flags.R)for(const t of d.rPeaks)if(t>=a&&t<=b){const cx=x(t),cy=y(values[Math.min(values.length-1,Math.round(t*d.fs))]);svg.push(`<path d="M${cx},${cy-5}l5,5 -5,5 -5,-5Z" fill="${colors.R}"/>`);}
 svg.push('<rect id="selection" x="66" y="28" width="0" height="316" fill="#2e9cbe" fill-opacity=".1" stroke="#2e9cbe" visibility="hidden"/><line id="crosshair" x1="66" x2="66" y1="28" y2="344" stroke="#6d9daf" stroke-dasharray="3 3" visibility="hidden"/><circle id="hover-dot" r="3" fill="#174d62" visibility="hidden"/></g><text x="502" y="393" text-anchor="middle" fill="#68818e" font-size="13">时间（秒）</text><text x="16" y="186" text-anchor="middle" transform="rotate(-90 16 186)" fill="#68818e" font-size="13">'+'幅值（'+unitName(d)+'）</text>');
 plot.innerHTML=svg.join('');hideHover();$('range-label').textContent=(a===0&&b===d.raw.length/d.fs)?`完整片段 · ${b.toFixed(0)} 秒`:`局部视图 · ${a.toFixed(2)}–${b.toFixed(2)} 秒`;
}
function timeAt(e){const r=plot.getBoundingClientRect(),g=state.geometry;if(!g||!Number.isFinite(e.clientX)||!Number.isFinite(r.width)||r.width<=0)return null;const px=(e.clientX-r.left)/r.width*960;return state.range[0]+Math.max(0,Math.min(1,(px-g.left)/g.width))*(state.range[1]-state.range[0]);}
function setRange(a,b){if(!state.current||!Number.isFinite(a)||!Number.isFinite(b))return false;if(a>b)[a,b]=[b,a];const total=state.current.raw.length/state.current.fs;const span=Math.min(total,Math.max(Math.min(.2,total),b-a));const left=Math.max(0,Math.min(total-span,a));state.range=[left,left+span];state.drag=null;draw();return true;}
function reset(){if(state.current){state.focus=null;$('focus-note').textContent='';updateMeasurements();setRange(0,state.current.raw.length/state.current.fs);}}
function focusInterval(focus,a,b,message){
 if(!state.current)return false;state.focus=focus;
 const span=Math.max(.8,(b-a)*2.5),mid=(a+b)/2;
 setRange(mid-span/2,mid+span/2);updateMeasurements();updateControls();
 $('focus-note').textContent=message;
 $('viewer-section').scrollIntoView?.({block:'start'});plot.focus({preventScroll:true});return true;
}
function focusQrs(qrsNumber){
 const d=state.current,r=d?.coursework.qrs.rows.find(row=>row.qrsNumber===qrsNumber);if(!r)return false;
 state.flags.QRS=true;state.flags.R=true;
 const pair=d.coursework.comparison.rows.find(row=>row.predictionIndex===r.predictionIndex);if(pair)state.truth=true;
 return focusInterval({predictionIndex:r.predictionIndex,referenceIndex:pair?.referenceIndex??null},Math.min(r.startSec,pair?.referenceStartSec??r.startSec),Math.max(r.endSec,pair?.referenceEndSec??r.endSec),`QRS #${r.qrsNumber} · ${number(r.startSec,3)}–${number(r.endSec,3)} 秒 · 估计时限 ${number(r.durationMs)} 毫秒${r.edgeClipped?' · 窗口边缘，未纳入时限汇总':''}`);
}
function focusReference(referenceIndex){
 const d=state.current,r=d?.coursework.comparison.rows.find(row=>row.referenceIndex===referenceIndex);if(!r)return false;
 state.flags[r.type]=true;state.truth=true;
 return focusInterval({predictionIndex:r.predictionIndex,referenceIndex:r.referenceIndex},Math.min(r.referenceStartSec,r.predictionStartSec??r.referenceStartSec),Math.max(r.referenceEndSec,r.predictionEndSec??r.referenceEndSec),`人工 ${r.type} #${r.referenceIndex}${r.matched?` · 起点误差 ${number(r.onsetErrorMs)} 毫秒，终点误差 ${number(r.offsetErrorMs)} 毫秒（预测减人工）`:' · 没有满足配对规则的预测区间'}`);
}
function focusExample(mode){
 const d=state.current;if(!d)return false;const center=d.raw.length/d.fs/2;
 const rows=mode==='qrs'?d.coursework.qrs.rows.filter(r=>r.includedInStats):d.coursework.comparison.rows.filter(r=>r.type==='QRS');
 const items=rows.length?rows:(mode==='qrs'?d.coursework.qrs.rows:d.coursework.comparison.rows);
 const pick=[...items].sort((a,b)=>Math.abs(((a.startSec??a.referenceStartSec)+(a.endSec??a.referenceEndSec))/2-center)-Math.abs(((b.startSec??b.referenceStartSec)+(b.endSec??b.referenceEndSec))/2-center))[0];
 return pick?(mode==='qrs'?focusQrs(pick.qrsNumber):focusReference(pick.referenceIndex)):false;
}
function zoom(factor,anchor){if(!state.current||!Number.isFinite(factor)||factor<=0||(anchor!=null&&!Number.isFinite(anchor)))return false;const [a,b]=state.range;const mid=Math.max(a,Math.min(b,anchor??(a+b)/2));const fraction=(mid-a)/(b-a);const span=(b-a)*factor;return setRange(mid-span*fraction,mid+span*(1-fraction));}
function hover(e){if(!state.current||!state.geometry)return;const t=timeAt(e);if(t===null)return;const d=state.current,g=state.geometry;const i=Math.min(d.raw.length-1,Math.max(0,Math.round(t*d.fs)));const v=(state.filtered?d.filtered:d.raw)[i];const x=g.x(i/d.fs);
 const line=$('crosshair'),dot=$('hover-dot');line.setAttribute('x1',x);line.setAttribute('x2',x);line.setAttribute('visibility','visible');dot.setAttribute('cx',x);dot.setAttribute('cy',g.y(v));dot.setAttribute('visibility','visible');
 const wave=d.waves.filter(w=>t>=w.start&&t<=w.end).map(w=>w.type==='QRS'?`QRS 波群 · 估计时限 ${number((w.end-w.start)*1000)} 毫秒`:w.type+' 波');$('readout').textContent=`${(i/d.fs).toFixed(3)} 秒 · ${v.toFixed(3)} ${unitName(d)}${wave.length?' · '+wave.join('、'):''}`;
 if(state.drag!=null){const selection=$('selection');const start=g.x(state.drag),end=g.x(t);selection.setAttribute('x',Math.min(start,end));selection.setAttribute('width',Math.abs(start-end));selection.setAttribute('visibility','visible');}
}
function download(rows,suffix){const d=state.current;if(!d)return;const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`openecg-${d.id}-${suffix}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function xmlText(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));}
function waveformSvg(){
 const d=state.current;if(!d)return null;
 const description=`${d.id} · ${state.filtered?'滤波后':inputName(d)} · ${state.range.map(t=>number(t,3)).join('–')} 秒 · ${unitName(d)}${isAppleWatch(d)?` · PDF曲线重建 · 原窗 ${sourceWindowLabel(d)} 秒`:''}${duplicateNote(d)?' · '+duplicateNote(d):''}`;
 const body=plot.innerHTML.replace(/<(?:rect|line|circle)\b[^>]*id="(?:selection|crosshair|hover-dot)"[^>]*\/>/g,'');
 return `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="1440" height="640" viewBox="0 -26 960 426" role="img"><title>${xmlText(description)}</title><desc>${xmlText(description)}</desc><rect x="0" y="-26" width="960" height="426" fill="#fff"/><text x="66" y="-6" fill="#174d62" font-family="sans-serif" font-size="12">${xmlText(description)}</text>${body}</svg>`;
}
function exportSvg(){const svg=waveformSvg();if(!svg)return;const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`openecg-${state.current.id}-${state.filtered?'filtered':'raw'}-${state.range.map(t=>number(t,2)).join('-')}.svg`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function summaryNote(d=state.current){
 if(!d)return null;
 const c=d.coursework,q=c.qrs.summary,p=c.protocol,total=d.raw.length/d.fs;
 const measurement=value=>value==null?'不可评价':number(value,3);
 return [
  'OpenECG 心电分析结果',
  `记录：${d.id} · ${d.dataset} ${d.record} · ${d.lead.toUpperCase()} 导联`,
  ...(duplicateNote(d)?[`来源：${duplicateNote(d)}（${d.pdfReconstruction.duplicateOf}）`]:[]),
  `原窗：${sourceWindowLabel(d)} 秒；时间轴：0–${number(total,3)} 秒；${d.raw.length} 点。`,
  `${isAppleWatch(d)?'PDF曲线重建 · 相对 mV':'幅值 mV'} · ${d.sourceFs} → ${d.fs} Hz`,
  `模型：${d.model}`,
  '预处理：重采样 → 0.5 Hz 高通 → 0.5–40 Hz 带通 → 50 Hz 陷波。',
  '',
  '心率与 RR',
  `平均 ${number(d.metrics.averageHr)}、最低 ${number(d.metrics.minHr)}、最高 ${number(d.metrics.maxHr)} 次/分；平均 RR ${number(d.metrics.meanRr,3)} 秒；估计 R 峰 ${d.metrics.rPeakCount} 个。`,
  '平均心率＝mean(60/RR)，RR 单位为秒。',
  '',
  'QRS 时限 · 模型估计',
  `${q.totalCount} 个预测区间；纳入 ${q.includedCount} 个；边缘排除 ${q.edgeExcludedCount} 个。`,
  `均值 ${number(q.meanMs,3)}、中位数 ${number(q.medianMs,3)}、最小 ${number(q.minMs,3)}、最大 ${number(q.maxMs,3)} 毫秒。`,
  `采样间隔 ${number(q.sampleStepMs,0)} 毫秒；模型边界步进约 20 毫秒。`,
  '时限＝（终点－起点）×1000 毫秒。',
  '',
  '人工标注对照',
  `配对条件：同类、时间重叠、中心距离不超过 ${number(p.matchCenterLimitMs,0)} 毫秒；按时间顺序一对一配对。`,
  '误差＝预测－人工；MAE 为配对区间的平均绝对误差。',
  ...c.comparison.summaries.map(s=>`${s.type}：人工 ${s.referenceCount}，预测 ${s.predictionCount}，配对 ${s.matchedCount}；配对率 ${percent(s.pairingRatePct)}；起点/终点/时限 MAE ${measurement(s.onsetMaeMs)}/${measurement(s.offsetMaeMs)}/${measurement(s.durationMaeMs)} 毫秒；双边界阈值内 ${s.bothWithinCount}/${s.referenceCount}（${percent(s.bothWithinRatePct)}）；起点/终点阈值 ${s.onsetLimitMs}/${s.offsetLimitMs} 毫秒。`),
 ].join('\r\n');
}
function exportNote(){const note=summaryNote();if(note===null)return;const url=URL.createObjectURL(new Blob(['\uFEFF'+note],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`openecg-${state.current.id}-evidence-note.txt`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function waveRows(d){const labels=Array(d.raw.length).fill('');for(const w of d.waves)for(let i=Math.max(0,Math.round(w.start*d.fs));i<=Math.round(w.end*d.fs)&&i<labels.length;i++)labels[i]=w.type;const peaks=new Set(d.rPeaks.map(t=>Math.round(t*d.fs)));return [isAppleWatch(d)?'时间_秒,PDF重建幅值_相对毫伏,滤波幅值_相对毫伏,模型预测波形,R峰标志':'时间_秒,原始幅值_毫伏,滤波幅值_毫伏,模型预测波形,R峰标志',...d.raw.map((v,i)=>`${(i/d.fs).toFixed(4)},${v},${d.filtered[i]},${labels[i]},${peaks.has(i)?1:0}`)];}
function beatRows(d){return ['心搏序号,R峰时间_秒,与上一R峰间隔_秒,瞬时心率_次每分,QRS起点_秒,QRS终点_秒,QRS估计时限_毫秒,QRS是否窗口边缘',...d.rPeaks.map((t,i)=>{const q=d.coursework.qrs.rows.find(r=>r.rPeakSec===t);return `${i+1},${t},${i?d.rr[i-1]??'':''},${i&&d.rr[i-1]>0?(60/d.rr[i-1]).toFixed(2):''},${q?.startSec??''},${q?.endSec??''},${q?.durationMs??''},${q?(q.edgeClipped?'是':'否'):''}`;})];}
function qrsRows(d){return ['记录,QRS序号,预测区间序号,起点_秒,终点_秒,唯一配对R峰_秒,估计时限_毫秒,区间内R峰数,R峰配对状态,窗口边缘,纳入时限统计',...d.coursework.qrs.rows.map(r=>[d.id,r.qrsNumber,r.predictionIndex,r.startSec,r.endSec,r.rPeakSec??'',r.durationMs,r.rPeakCountInInterval,associationLabel(r),r.edgeClipped?'是':'否',r.includedInStats?'是':'否'].join(','))];}
function comparisonRows(d){return ['记录,波形,人工区间序号,预测区间序号,人工起点_秒,人工终点_秒,预测起点_秒,预测终点_秒,起点误差_毫秒_预测减人工,终点误差_毫秒_预测减人工,时限误差_毫秒,是否配对,双边界是否在演示阈值内,起点阈值_毫秒,终点阈值_毫秒',...d.coursework.comparison.rows.map(r=>{const limit=d.coursework.protocol.boundaryLimitsMs[r.type];return [d.id,r.type,r.referenceIndex,r.predictionIndex??'',r.referenceStartSec,r.referenceEndSec,r.predictionStartSec??'',r.predictionEndSec??'',r.onsetErrorMs??'',r.offsetErrorMs??'',r.durationErrorMs??'',r.matched?'是':'否',r.bothWithinLimits?'是':'否',limit.onset,limit.offset].join(',');})];}
function summaryRows(d){return ['记录,波形,人工区间数,预测区间数,配对数,未配对人工区间数,未评分预测数,人工区间配对率_百分比,起点MAE_毫秒,终点MAE_毫秒,起点偏差_毫秒,终点偏差_毫秒,时限MAE_毫秒,双边界在演示阈值内数,双边界在演示阈值内比例_百分比,起点阈值_毫秒,终点阈值_毫秒,统计范围',...d.coursework.comparison.summaries.map(s=>[d.id,s.type,s.referenceCount,s.predictionCount,s.matchedCount,s.unmatchedReferenceCount,s.unscoredPredictionCount,s.pairingRatePct??'',s.onsetMaeMs??'',s.offsetMaeMs??'',s.onsetBiasMs??'',s.offsetBiasMs??'',s.durationMaeMs??'',s.bothWithinCount,s.bothWithinRatePct??'',s.onsetLimitMs,s.offsetLimitMs,isAppleWatch(d)?'PDF曲线重建_无人工标注':'人工标注区间'].join(','))];}
document.querySelectorAll('[data-source]').forEach(b=>b.addEventListener('click',()=>{if(state.busy||state.source===b.dataset.source)return;state.source=b.dataset.source;state.selected=records.find(d=>d?.dataset===state.source)?.id??'';populate();clearResult();load();}));
document.querySelector('[role="tablist"]').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=[...document.querySelectorAll('[data-source]')];const index=tabs.indexOf(document.activeElement);const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].focus();tabs[next].click();});
$('record').addEventListener('change',()=>{if(state.busy)return;state.selected=$('record').value;clearResult();load();});$('load').addEventListener('click',load);
$('raw').addEventListener('click',()=>{state.filtered=false;updateControls();draw();});$('filtered').addEventListener('click',()=>{state.filtered=true;updateControls();draw();});
document.querySelectorAll('[data-wave]').forEach(b=>b.addEventListener('click',()=>{state.flags[b.dataset.wave]=!state.flags[b.dataset.wave];updateControls();draw();}));$('truth').addEventListener('click',()=>{state.truth=!state.truth;updateControls();draw();});
$('reset').addEventListener('click',reset);plot.addEventListener('dblclick',reset);
plot.addEventListener('pointerdown',e=>{if(!state.current||e.button!==0)return;state.drag=timeAt(e);if(state.drag!==null)plot.setPointerCapture(e.pointerId);});plot.addEventListener('pointermove',hover);
plot.addEventListener('pointerup',e=>{if(state.drag==null)return;const a=state.drag,b=timeAt(e);state.drag=null;if(b!==null&&Math.abs(b-a)>.12)setRange(Math.min(a,b),Math.max(a,b));else if($('selection'))$('selection').setAttribute('visibility','hidden');if(plot.hasPointerCapture(e.pointerId))plot.releasePointerCapture(e.pointerId);});
plot.addEventListener('pointercancel',()=>{state.drag=null;hideHover();});
plot.addEventListener('pointerleave',()=>{if(state.drag==null)hideHover();});
plot.addEventListener('wheel',e=>{if(!state.current||!e.ctrlKey)return;e.preventDefault();zoom(e.deltaY<0?.8:1.25,timeAt(e));},{passive:false});
plot.addEventListener('keydown',e=>{if(!state.current)return;if(['+','=','-','0','Home','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();if(e.key==='+'||e.key==='=')zoom(.8);else if(e.key==='-')zoom(1.25);else if(e.key==='0'||e.key==='Home')reset();else{const [a,b]=state.range;const shift=(b-a)*.2*(e.key==='ArrowLeft'?-1:1);setRange(a+shift,b+shift);}}});
$('export-wave').addEventListener('click',()=>{if(state.current)download(waveRows(state.current),'waveform');});$('export-beats').addEventListener('click',()=>{if(state.current)download(beatRows(state.current),'beats');});
 $('export-qrs').addEventListener('click',()=>{if(state.current)download(qrsRows(state.current),'qrs-duration');});
 $('export-comparison').addEventListener('click',()=>{if(state.current)download(comparisonRows(state.current),'reference-comparison');});
 $('export-summary').addEventListener('click',()=>{if(state.current)download(summaryRows(state.current),'comparison-summary');});
 $('focus-qrs').addEventListener('click',()=>focusExample('qrs'));$('focus-comparison').addEventListener('click',()=>focusExample('comparison'));
 $('qrs-table').addEventListener('click',e=>{const button=e.target.closest?.('button[data-qrs]');if(button)focusQrs(Number(button.dataset.qrs));});
 $('comparison-details').addEventListener('click',e=>{const button=e.target.closest?.('button[data-reference]');if(button)focusReference(Number(button.dataset.reference));});
 $('comparison-kind').addEventListener('change',()=>{state.comparisonKind=$('comparison-kind').value;renderReferenceRows();});
 $('comparison-issues').addEventListener('change',()=>{state.issuesOnly=$('comparison-issues').checked;renderReferenceRows();});
 $('export-svg').addEventListener('click',exportSvg);
 $('export-note').addEventListener('click',exportNote);
populate();load();
})();
