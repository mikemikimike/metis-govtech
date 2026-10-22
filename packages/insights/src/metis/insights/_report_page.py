"""Render the target evaluation report as one self-contained HTML page."""

from __future__ import annotations

import json
from typing import Any

from ._report_styles import REPORT_CSS

DATA_TOKEN = "__METIS_REPORT__"

REPORT_BODY = """\
<main class="report-shell">
  <header class="report-head">
    <div><h1 id="report-title"></h1><p id="executive-summary" class="executive-summary"></p></div>
  </header>

  <section class="summary" aria-label="Run summary">
    <article class="summary-card" id="grader-summary"></article>
    <article class="summary-card" id="trial-summary"></article>
  </section>

  <section class="investigation" aria-labelledby="result-view-title">
    <div class="section-head view-head">
      <div>
        <div class="view-tabs" role="tablist" aria-label="Result view">
          <button id="tree-tab" type="button" role="tab" aria-controls="tree-view" aria-selected="true">Experiment tree</button>
          <button id="table-tab" type="button" role="tab" aria-controls="table-view" aria-selected="false">Results table</button>
        </div>
        <h2 id="result-view-title">Experiment result tree</h2>
        <p id="result-view-description" class="section-description">A criterion pools its grader runs. Each higher level averages its evaluated children.</p>
      </div>
      <div class="tree-tools">
        <label class="search"><span>Search</span><input id="tree-search" type="search" placeholder="Feature, behaviour, criterion, grader"></label>
        <button id="fail-only" class="quiet-button" type="button" aria-pressed="false">Fail only</button>
        <button id="expand-all" class="quiet-button" type="button">Expand all</button>
      </div>
    </div>
    <div id="tree-view" role="tabpanel" aria-labelledby="tree-tab">
      <div class="investigation-grid">
        <div class="tree-wrap"><div class="tree-pan-cue">Swipe to grader →</div><div id="tree-canvas" class="tree-canvas"></div></div>
        <aside id="selection-panel" class="selection-panel" aria-live="polite"></aside>
      </div>
      <div class="status-key" aria-label="Status key">
        <span><i class="key-pass"></i>No failed runs</span><span><i class="key-fail"></i>Has failed runs</span>
        <span><i class="key-none"></i>Not evaluated</span><span><i class="key-error"></i>Grader error</span><span><i class="key-error"></i>Data error</span>
        <span>Criterion rate = passed / evaluated runs. Higher levels average their children.</span>
      </div>
    </div>
    <div id="table-view" role="tabpanel" aria-labelledby="table-tab" hidden>
      <div class="table-tools">
        <label class="search"><span>Search</span><input id="table-search" type="search" placeholder="Persona or scenario"></label>
        <button id="table-fail-only" class="quiet-button" type="button" aria-pressed="false">Fail only</button>
        <span id="table-count" class="section-count"></span>
      </div>
      <div class="table-status-key" aria-label="Grader aggregation notes"><span>Grader cells pool the runs of all trials in the test case</span><span>Skipped and errored runs are excluded from rates</span></div>
      <div id="results-table" class="results-table-wrap"></div>
    </div>
  </section>

  <section id="unmapped-results" class="outcomes" aria-labelledby="unmapped-title" hidden></section>

  <section class="outcomes" aria-labelledby="outcome-title">
    <div class="section-head"><h2 id="outcome-title">Eval errors</h2><p class="section-count" id="outcome-count"></p></div>
    <div id="outcome-bar" class="outcome-bar"></div>
    <div id="outcome-tabs" class="outcome-tabs"></div>
    <div id="outcome-detail" class="outcome-detail"></div>
  </section>

  <footer>Values come from the target specification, grader results, and trial records.</footer>
</main>
<div id="tree-tip" class="tree-tip" role="tooltip"></div>
"""

REPORT_SCRIPT = r"""
const V=__METIS_REPORT__;
const B=V.behaviours||{}, C=V.criteria||{};
const LABELS={pass:"No failed runs",fail:"Has failed runs",notEvaluated:"Not evaluated",dataError:"Data error",error:"Grader error",skip:"Skipped"};
const RESULT_LABELS={pass:"Passed",fail:"Failed",skip:"Skipped",error:"Grader error"};
const esc=value=>String(value??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const clip=(value,max)=>String(value??"").length>max?String(value).slice(0,max-1)+"…":String(value??"");
const statusOf=item=>item?.status||"notEvaluated";
const runCounts=c=>`${c.pass||0} pass · ${c.fail||0} fail · ${c.skip||0} skip · ${c.error||0} error`;
const rateText=rate=>rate==null?"—":rate+"%";
const meanText=mean=>mean==null?"No mean score":`Mean score ${mean.toFixed(2)}`;
const allFeatures=V.features||[];
let selected=null,failOnly=false,query="",resultFilters={persona:null,scenario:null},openResultFilter="";
let tableQuery="",tableFailOnly=false,expandedTrial="";
const shutFeatures=new Set(allFeatures.map(feature=>feature.id));
const shutBehaviours=new Set(Object.keys(B));
let filterSnapshot=null;
const replaceSet=(target,source)=>{target.clear();for(const value of source)target.add(value)};
const filtersActive=()=>failOnly||Boolean(query);
function applyFilterView(wasActive){
 const active=filtersActive();
 if(!wasActive&&active)filterSnapshot={features:new Set(shutFeatures),behaviours:new Set(shutBehaviours)};
 if(active){shutFeatures.clear();shutBehaviours.clear()}
 else if(wasActive&&filterSnapshot){replaceSet(shutFeatures,filterSnapshot.features);replaceSet(shutBehaviours,filterSnapshot.behaviours);filterSnapshot=null}
}
function syncExpandControl(){
 const button=document.getElementById("expand-all"),allExpanded=allFeatures.length>0&&!shutFeatures.size&&!shutBehaviours.size;
 button.textContent=allExpanded?"Collapse all":"Expand all";
 button.setAttribute("aria-pressed",String(allExpanded));
}

document.getElementById("report-title").textContent=V.target;


function setResultView(view){
 const tree=view==="tree";
 document.getElementById("tree-view").hidden=!tree;
 document.getElementById("table-view").hidden=tree;
 document.querySelector(".tree-tools").hidden=!tree;
 document.getElementById("tree-tab").setAttribute("aria-selected",String(tree));
 document.getElementById("table-tab").setAttribute("aria-selected",String(!tree));
 document.getElementById("result-view-title").textContent=tree?"Experiment result tree":"Results table";
 document.getElementById("result-view-description").textContent=tree?"A criterion pools its grader runs. Each higher level averages its evaluated children.":"Each row is one test case. Expand a row to see each trial.";
 if(!tree)renderResultsTable();
}
document.getElementById("tree-tab").onclick=()=>setResultView("tree");
document.getElementById("table-tab").onclick=()=>setResultView("table");

const summaryCard=(label,rate,detail)=>`<div class="summary-label">${esc(label)}</div><div class="summary-value">${rateText(rate)}</div><div class="score-rail"><i style="width:${rate??0}%"></i></div><div class="summary-detail">${esc(detail)}</div>`;
const trials=V.trials||{attempted:0,successful:0,rate:null,items:[]};
const trialScore=V.scores?.trialSuccess||{rate:null,successful:0,attempted:0};
const graderScore=V.scores?.graderPassRate||{rate:null,mean_score:null,pass:0,ran:0,skip:0,error:0};
const scoredFeatures=allFeatures.filter(feature=>feature.rate!=null);
if(!scoredFeatures.length)document.getElementById("executive-summary").textContent="No feature has evaluated runs.";
else{const lowest=scoredFeatures.reduce((a,b)=>a.rate<b.rate?a:b);document.getElementById("executive-summary").textContent=`${scoredFeatures.length} feature${scoredFeatures.length===1?" has":"s have"} evaluated runs. The lowest feature pass rate is ${lowest.rate}% for ${lowest.name}.`}
document.getElementById("trial-summary").innerHTML=summaryCard("Trial success",trialScore.rate,`${trialScore.successful} of ${trialScore.attempted} trials succeeded`);
document.getElementById("grader-summary").innerHTML=summaryCard("Evaluated grader pass rate",graderScore.rate,`Mean of feature rates. ${meanText(graderScore.mean_score)}. ${graderScore.ran} evaluated runs; ${runCounts(graderScore)}`);

const tip=document.getElementById("tree-tip");
const showTip=(event,html)=>{tip.innerHTML=html;tip.classList.add("on");const r=tip.getBoundingClientRect();tip.style.left=Math.min(event.clientX+12,innerWidth-r.width-12)+"px";tip.style.top=Math.max(12,event.clientY-r.height-12)+"px"};
const hideTip=()=>tip.classList.remove("on");

function leafMatches(feature,behaviour,cid){
 const criterion=C[cid]||{};
 if(failOnly&&statusOf(criterion)!=="fail")return false;
 if(!query)return true;
 return [feature.name,feature.id,behaviour.label,behaviour.statement,cid,criterion.grader_name,criterion.description].join(" ").toLowerCase().includes(query);
}

function renderTree(){
 const rows=[],featureGroups=[];
 for(const feature of allFeatures){
  const featureStart=rows.length,behaviourGroups=[];
  if(shutFeatures.has(feature.id))rows.push({feature,closedFeature:true});
  else for(const bid of feature.behaviours){
   const behaviour=B[bid],behaviourStart=rows.length;
   const matching=(behaviour?.criteria||[]).filter(cid=>leafMatches(feature,behaviour,cid));
   if(!matching.length)continue;
   if(shutBehaviours.has(bid))rows.push({feature,behaviour,bid,closedBehaviour:true});
   else matching.forEach(cid=>rows.push({feature,behaviour,bid,cid,criterion:C[cid]}));
   behaviourGroups.push({bid,behaviour,start:behaviourStart,end:rows.length-1});
  }
  if(rows.length>featureStart)featureGroups.push({feature,start:featureStart,end:rows.length-1,behaviourGroups});
 }
 const host=document.getElementById("tree-canvas");
 if(!rows.length){host.innerHTML='<div class="tree-empty">No result matches this view.</div>';syncExpandControl();return}
 const ROW_PITCH=88,TREE_TOP=48,TREE_BOTTOM=16;
 const H=Math.max(360,TREE_TOP+(rows.length-1)*ROW_PITCH+33+TREE_BOTTOM),W=1250,rowY=i=>TREE_TOP+i*ROW_PITCH;
 const X={target:14,feature:210,behaviour:472,criterion:734,grader:996};
 const widths={target:160,feature:230,behaviour:230,criterion:230,grader:240};
 const centre=(start,end)=>(rowY(start)+rowY(end))/2;
 const link=(x1,y1,x2,y2,active=false,status="")=>{const mid=Math.round((x1+x2)/2);return `<path d="M${x1} ${y1} H${mid} V${y2} H${x2}" class="tree-link${active?' active':''}${status?' state-'+status:''}"/>`};
 let svg=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-label="Target result tree">`;
 const targetY=centre(0,rows.length-1);
 for(const group of featureGroups){const featureY=centre(group.start,group.end);svg+=link(X.target+widths.target,targetY,X.feature,featureY);for(const bg of group.behaviourGroups){const by=centre(bg.start,bg.end);svg+=link(X.feature+widths.feature,featureY,X.behaviour,by);for(let i=bg.start;i<=bg.end;i++){const row=rows[i],y=rowY(i),active=selected?.id===row.cid,st=row.criterion?statusOf(row.criterion):"";svg+=link(X.behaviour+widths.behaviour,by,X.criterion,y,active,st);if(row.cid)svg+=link(X.criterion+widths.criterion,y,X.grader,y,active,st)}}}
 const box=(x,y,w,h,status,kind,id,title,score,code,note,selectable=false,expanded=null)=>{
  const active=selectable&&selected?.id===id;
  const classes=["tree-node",`state-${status}`,`kind-${kind}`,active?"selected":"",selectable?"selectable":""].filter(Boolean).join(" ");
  const interactive=selectable||kind==="feature"||kind==="behaviour",aria=expanded==null?"":` aria-expanded="${expanded}"`;
  let out=`<g class="${classes}" data-kind="${kind}" data-id="${esc(id)}"${interactive?` tabindex="0" role="button"${aria}`:""}><title>${esc(title)}</title><rect x="${x}" y="${y-h/2}" width="${w}" height="${h}" rx="8"/>`;
  out+=`<circle class="state-dot" cx="${x+12}" cy="${y-h/2+15}" r="3.5"/>`;
  out+=`<text x="${x+23}" y="${y-h/2+19}" class="node-title">${esc(clip(title,Math.floor((w-76)/7)))}</text>`;
  out+=`<text x="${x+w-12}" y="${y-h/2+19}" text-anchor="end" class="node-score">${esc(score)}</text>`;
  out+=`<text x="${x+12}" y="${y+h/2-10}" class="node-id">${esc(code)}</text>`;
  out+=`<text x="${x+w-12}" y="${y+h/2-10}" text-anchor="end" class="node-note">${esc(note)}</text>`;
  if(expanded!=null){const ex=x+w+10;out+=`<g class="tree-expander" aria-hidden="true"><circle class="expander-hit" cx="${ex}" cy="${y}" r="12"/><circle class="expander-ring" cx="${ex}" cy="${y}" r="7"/><path class="expander-mark" d="M${ex-3} ${y}H${ex+3}${expanded?'':`M${ex} ${y-3}V${y+3}`}"/></g>`}
  return out+`</g>`;
 };
 const dataErrors=(V.unresolved||[]).length;
 svg+=box(X.target,targetY,widths.target,66,dataErrors?"dataError":"neutral","target","target",V.target,"","Target",dataErrors?`${dataErrors} data errors`:"",false);
 for(const group of featureGroups){const feature=group.feature,y=centre(group.start,group.end),closed=shutFeatures.has(feature.id);svg+=box(X.feature,y,widths.feature,62,statusOf(feature),"feature",feature.id,feature.name,rateText(feature.rate),runCounts(feature),"",false,!closed);
  for(const bg of group.behaviourGroups){const b=bg.behaviour,yb=centre(bg.start,bg.end),closedB=shutBehaviours.has(bg.bid);svg+=box(X.behaviour,yb,widths.behaviour,62,statusOf(b),"behaviour",bg.bid,b.label,rateText(b.rate),runCounts(b),"",false,!closedB)}
 }
 rows.forEach((row,i)=>{if(!row.cid)return;const c=row.criterion,y=rowY(i),st=statusOf(c),graderName=c.grader_name||(c.grader_fqn||"").split(".").pop()||"No grader";svg+=box(X.criterion,y,widths.criterion,58,st,"criterion",row.cid,row.cid,rateText(c.rate),runCounts(c),"",true);svg+=box(X.grader,y,widths.grader,58,st,"grader",row.cid,graderName,rateText(c.rate),runCounts(c),"",true)});
 host.innerHTML=svg+"</svg>";
 syncExpandControl();
 host.querySelectorAll('.tree-node[role="button"]').forEach(node=>{
  const activate=()=>{hideTip();const kind=node.dataset.kind,id=node.dataset.id;if(kind==="feature"){shutFeatures.has(id)?shutFeatures.delete(id):shutFeatures.add(id);renderTree();return}if(kind==="behaviour"){shutBehaviours.has(id)?shutBehaviours.delete(id):shutBehaviours.add(id);renderTree();return}if(kind==="criterion"||kind==="grader"){if(selected?.id!==id)resultFilters={persona:null,scenario:null};selected={type:kind,id};renderTree();renderSelection();if(innerWidth<=1000)document.getElementById("selection-panel").scrollIntoView({behavior:"auto",block:"start"})}};
  node.addEventListener("click",activate);node.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();activate()}});
  node.addEventListener("mousemove",e=>{const kind=node.dataset.kind;if(kind==="criterion"||kind==="grader"){const c=C[node.dataset.id];showTip(e,`<strong>${esc(kind==="grader"?(c.grader_name||"No grader"):node.dataset.id)}</strong><span>${esc(LABELS[statusOf(c)])} · ${rateText(c.rate)} · ${esc(meanText(c.mean_score))}</span>`)}else if(kind==="feature"){showTip(e,`Feature rate = mean of its evaluated behaviour rates. ${meanText(allFeatures.find(f=>f.id===node.dataset.id)?.mean_score)}.`)}else if(kind==="behaviour"){showTip(e,`Behaviour rate = mean of its evaluated criterion rates. ${meanText(B[node.dataset.id]?.mean_score)}.`)}});node.addEventListener("mouseleave",hideTip);
 });
}

const statPill=st=>`<span class="status-pill ${st}"><i></i>${esc(LABELS[st])}</span>`;
const resultRail=c=>{const st=statusOf(c),settings=[...new Set((c.evidence||[]).map(item=>item.grader_args?.threshold).filter(value=>value!=null))];return `<div class="leaf-score"><div><strong class="${st}">${rateText(c.rate)}</strong>${statPill(st)}</div><div class="score-rail"><i style="width:${c.rate??0}%" class="${st}"></i></div><div class="threshold-line">Runs: ${esc(runCounts(c))}</div><div class="threshold-line">${esc(meanText(c.mean_score))}</div><div class="threshold-line">${(c.judge_models||[]).length?`Judge model: ${c.judge_models.map(esc).join(", ")}`:"No judge model recorded"}</div><div class="threshold-line">${settings.length?`Recorded run threshold: ${settings.map(esc).join(", ")}`:"No scored run threshold recorded"}</div></div>`};
const resultCounts=items=>({pass:items.filter(item=>item.status==="pass").length,fail:items.filter(item=>item.status==="fail").length,skip:items.filter(item=>item.status==="skip").length,error:items.filter(item=>item.status==="error").length});
const evidenceCounts=items=>{const counts=resultCounts(items);return `<div class="evidence-counts" aria-label="Raw result counts"><div class="pass"><strong>${counts.pass}</strong><span>Pass</span></div><div class="fail"><strong>${counts.fail}</strong><span>Fail</span></div><div class="skip"><strong>${counts.skip}</strong><span>Skip</span></div><div class="error"><strong>${counts.error}</strong><span>Grader error</span></div></div>`};
function filterOptions(c,key){
 const values=[...new Set((c.evidence||[]).map(item=>item[key]).filter(Boolean))];
 return values.map(value=>{const items=c.evidence.filter(item=>item[key]===value),counts=resultCounts(items),evaluated=counts.pass+counts.fail;return {value,fail:counts.fail,evaluated,skip:counts.skip,error:counts.error,rate:evaluated?counts.fail/evaluated:0}})
  .sort((a,b)=>b.fail-a.fail||b.rate-a.rate||b.evaluated-a.evaluated||a.value.localeCompare(b.value));
}
const filterMeta=row=>`${row.fail} of ${row.evaluated} scored raw results failed${row.skip?` · ${row.skip} skipped`:""}${row.error?` · ${row.error} errored`:""}`;
function resultFilter(c,key,label){
 const options=filterOptions(c,key),current=resultFilters[key],allSelected=current===null,currentValues=allSelected?options.map(option=>option.value):current;
 const allLabel=`All ${label.toLowerCase()}s`,emptyLabel=`No ${label.toLowerCase()}s`,currentLabel=allSelected?allLabel:current.length===0?emptyLabel:current.length===1?current[0]:`${current.length} ${label.toLowerCase()}s`;
 return `<div class="result-filter"><span class="filter-label">${label}</span><details class="filter-dropdown" data-filter-dropdown="${key}"${openResultFilter===key?" open":""}><summary aria-label="${esc(label)}: ${esc(currentLabel)}"><span>${esc(currentLabel)}</span></summary><div class="filter-menu"><div class="filter-actions"><button type="button" data-filter-action="all" data-filter-key="${key}">Select all</button><button type="button" data-filter-action="clear" data-filter-key="${key}">Clear</button></div>${options.map(option=>{const checked=currentValues.includes(option.value);return `<button type="button" class="filter-option" role="checkbox" data-result-filter="${key}" data-filter-value="${esc(option.value)}" aria-checked="${checked}"><i aria-hidden="true"></i><span><b>${esc(option.value)}</b><small>${esc(filterMeta(option))}</small></span></button>`}).join("")}</div></details></div>`;
}
const filterIncludes=(key,value)=>resultFilters[key]===null||resultFilters[key].includes(value);
function filteredEvidence(c){return (c.evidence||[]).filter(item=>filterIncludes("persona",item.persona)&&filterIncludes("scenario",item.scenario))}
function evidenceList(c,evidence){
 if(!(c.evidence||[]).length)return `<div class="blank-note">${esc(c.blank?.note||"No grader result was recorded.")}</div>`;
 if(!evidence.length)return '<div class="blank-note filter-empty">No results match these filters.<button type="button" data-clear-result-filters>Clear filters</button></div>';
 return `<div class="evidence-list">${evidence.map(item=>`<article class="evidence-item ${esc(item.status)}"><div class="evidence-head"><span class="evidence-status">${esc(RESULT_LABELS[item.status]||item.status)}</span><span>${esc(item.persona||"No persona")} · ${esc(item.scenario||"No scenario")}</span></div><p>${esc(item.message||"No message recorded")}</p><div class="evidence-meta"><span>${esc(item.task_id)} trial ${esc(item.trial_index)}</span><span>Session ${esc(item.session)}</span><span>Result ${esc(item.result_number)}${item.score==null?"":` · Score ${esc(item.score)}`}</span><span>Run: ${esc(item.run_outcome)}${item.run_score==null?"":` · Mean ${esc(item.run_score)} · Threshold ${esc(item.run_threshold)}`}</span></div><details class="grader-settings"><summary>Recorded grader settings</summary><p>${esc(item.grader_fqn)}</p><pre>${esc(JSON.stringify(item.grader_args||{},null,2))}</pre></details></article>`).join("")}</div>`;
}
function unmappedEvidence(group){return (group.records||[]).flatMap(record=>record.results.map((result,index)=>({task_id:record.task_id,trial_index:record.trial_index,session:record.session_id,scenario:record.scenario_id,persona:"",criterion_id:record.criterion_id,grader_fqn:record.grader_fqn,grader_args:record.grader_args,result_number:index+1,score:result.score,message:result.reason,outcome:result.outcome,status:{passed:"pass",failed:"fail",skipped:"skip",errored:"error"}[result.outcome],run_outcome:"not matched"})))}
function unmappedResults(groups){
 if(!groups.length)return "";
 return `<h2 id="unmapped-title">Results without a matching criterion</h2><p>These results could not be matched to a Task and Criterion in the specification. They are excluded from the target pass rate.</p>${groups.map(group=>{const evidence=unmappedEvidence(group);return `<section class="individual-results"><h3>${esc(group.criterion_id)} / ${esc(group.grader_fqn)}</h3><p>${esc(group.why)}</p>${evidenceCounts(evidence)}${evidenceList({evidence},evidence)}</section>`}).join("")}`;
}
function individualResults(c){const allEvidence=c.evidence||[];if(!allEvidence.length)return `<section class="individual-results"><h4>Raw results</h4>${evidenceList(c,[])}</section>`;const evidence=filteredEvidence(c);return `<section class="individual-results"><h4>Raw results</h4><div class="result-filters">${resultFilter(c,"persona","Persona")}${resultFilter(c,"scenario","Scenario")}</div>${evidenceCounts(evidence)}${evidenceList(c,evidence)}</section>`}
function bindResultFilters(c,panel){
 panel.querySelectorAll("[data-result-filter]").forEach(button=>button.onclick=event=>{event.stopPropagation();const key=button.dataset.resultFilter,allValues=filterOptions(c,key).map(option=>option.value),current=resultFilters[key]===null?allValues:resultFilters[key],next=new Set(current),value=button.dataset.filterValue;next.has(value)?next.delete(value):next.add(value);resultFilters={...resultFilters,[key]:next.size===allValues.length?null:[...next]};openResultFilter=key;renderSelection()});
 panel.querySelectorAll("[data-filter-action]").forEach(button=>button.onclick=event=>{event.stopPropagation();const key=button.dataset.filterKey;resultFilters={...resultFilters,[key]:button.dataset.filterAction==="all"?null:[]};openResultFilter=key;renderSelection()});
 panel.querySelectorAll("[data-filter-dropdown]").forEach(dropdown=>dropdown.ontoggle=()=>{if(dropdown.open)openResultFilter=dropdown.dataset.filterDropdown;else if(openResultFilter===dropdown.dataset.filterDropdown)openResultFilter=""});
 const clear=panel.querySelector("[data-clear-result-filters]");if(clear)clear.onclick=()=>{resultFilters={persona:null,scenario:null};openResultFilter="";renderSelection()};
}
function renderSelection(){
 const panel=document.getElementById("selection-panel");
 if(!selected){panel.innerHTML=`<div class="empty-selection"><div class="path-visual"><i></i><i></i><i></i><i></i></div><h3>Select a criterion or grader</h3><p>Feature → Behaviour → Criterion → Grader</p></div>`;return}
 const c=C[selected.id],graderName=c.grader_name||(c.grader_fqn||"").split(".").pop()||"No grader";
 panel.innerHTML=`<div class="selected-title"><h3>${esc(selected.id)}</h3></div>${resultRail(c)}
  <p class="assessment-description">${esc(c.description)}</p>
  <div class="grader-field"><span>Grader</span><strong>${esc(graderName)}</strong><small>${esc(c.grader_fqn||"")}</small></div>
  ${individualResults(c)}`;
 bindResultFilters(c,panel);
}

document.getElementById("tree-search").addEventListener("input",event=>{const wasActive=filtersActive();query=event.target.value.trim().toLowerCase();applyFilterView(wasActive);renderTree()});
document.getElementById("fail-only").onclick=event=>{const wasActive=filtersActive();failOnly=!failOnly;event.currentTarget.setAttribute("aria-pressed",String(failOnly));event.currentTarget.classList.toggle("active",failOnly);applyFilterView(wasActive);renderTree()};
document.getElementById("expand-all").onclick=()=>{const collapse=!shutFeatures.size&&!shutBehaviours.size;if(collapse){allFeatures.forEach(feature=>shutFeatures.add(feature.id));Object.keys(B).forEach(id=>shutBehaviours.add(id))}else{shutFeatures.clear();shutBehaviours.clear()}renderTree()};

const tableData=V.resultTable||{features:[],rows:[]};
const tableColumns=tableData.features.flatMap(feature=>feature.columns||[]);
const outcomeLabel={succeeded:"Succeeded",abandoned:"Abandoned",timedOut:"Timed out",error:"Error"};
const tableCases=[];
const tableCaseByKey=new Map();
const activeTrialByCase=new Map();
for(const row of tableData.rows||[]){const testCase={id:`case-${tableCases.length+1}`,taskId:row.task_id,persona:row.persona||"",scenario:row.scenario||"",results:row.results||{},trials:row.trials||[]};tableCaseByKey.set(row.task_id,testCase);tableCases.push(testCase)}
const trialSquares=(testCase,stateOf,labelOf)=>`<span class="trial-statuses">${testCase.trials.map((trial,index)=>{const state=stateOf(trial);return `<i class="trial-mark ${state}" title="Trial ${trial.trial_index}: ${esc(labelOf(trial,state))}" aria-label="Trial ${trial.trial_index}: ${esc(labelOf(trial,state))}"></i>`}).join("")}</span>`;
const resultCell=result=>{const value=result||{},detail=`Runs: ${value.pass||0} pass; ${value.fail||0} fail; ${value.skip||0} skip; ${value.error||0} error`;if(value.rate==null){const state=value.error?"error":"notEvaluated";return `<span class="table-score ${state}" title="${esc(detail)}" aria-label="${esc(detail)}">—<small>${esc(detail)}</small></span>`}const state=value.status||"pass",mean=value.mean_score==null?"":` · mean ${value.mean_score.toFixed(2)}`;return `<span class="table-score ${state}" title="${esc(detail+mean)}" aria-label="${value.rate}%. ${esc(detail+mean)}">${value.rate}%<small>${esc(detail+mean)}</small></span>`};
const graderCell=(testCase,column)=>resultCell(testCase.results[column.criterion]);
const trialResults=trial=>tableColumns.length?`<table class="trial-results"><thead><tr>${tableColumns.map(column=>`<th title="${esc(column.grader_fqn)}">${esc(column.criterion)}</th>`).join("")}</tr></thead><tbody><tr>${tableColumns.map(column=>`<td>${resultCell((trial.results||{})[column.criterion])}</td>`).join("")}</tr></tbody></table>`:"";
const outcomeCell=testCase=>trialSquares(testCase,trial=>trial.category||"abandoned",(trial,state)=>outcomeLabel[state]||state);
const trialTrace=row=>{const turns=row.conversation||[],category=row.category||"abandoned";return `<section class="trial-trace"><div class="trial-trace-head"><div><strong>Trial ${row.trial_index}</strong><span>${esc(row.id)}</span>${row.attempt>1?'<span class="trial-retried">retried · attempt '+row.attempt+'</span>':""}</div><span class="outcome-state ${category}"><i></i>${esc(outcomeLabel[category]||category)}</span><span class="trial-turns">${row.total_turns==null?"Turns unavailable":`${row.total_turns} recorded turns`}${row.turnCountNote?`<span class="trial-turn-note">${esc(row.turnCountNote)}</span>`:""}</span></div>${trialResults(row)}${turns.length?turns.map(turn=>`<article class="conversation-turn"><span class="turn-number">Turn ${turn.turn}</span><div><b>User agent</b><p>${esc(turn.user||"No user message recorded")}</p></div><div><b>Target</b><p>${esc(turn.target||"No target response recorded")}</p>${(turn.errors||[]).map(error=>`<p class="turn-error">${esc(error)}</p>`).join("")}</div></article>`).join(""):`<div class="conversation-empty">No conversation was recorded for this trial.${row.conversationProblem?`<span class="conversation-problem">${esc(row.conversationProblem)}</span>`:""}</div>`}</section>`};
const testCaseTraces=testCase=>{const active=Math.min(activeTrialByCase.get(testCase.id)??0,testCase.trials.length-1),trial=testCase.trials[active];return `<div class="test-case-detail"><div class="trial-tabs" role="tablist" aria-label="Trials">${testCase.trials.map((item,index)=>{const category=item.category||"abandoned",selected=index===active;return `<button type="button" role="tab" id="${testCase.id}-trial-${index}-tab" aria-controls="${testCase.id}-trial-panel" aria-selected="${selected}" data-trial-tab data-test-case="${testCase.id}" data-trial-index="${index}"><i class="${category}"></i>Trial ${item.trial_index}</button>`}).join("")}</div><div id="${testCase.id}-trial-panel" role="tabpanel" aria-labelledby="${testCase.id}-trial-${active}-tab">${trialTrace(trial)}</div></div>`};
function bindTrialTabs(){document.querySelectorAll("[data-trial-tab]").forEach(button=>button.onclick=()=>{const testCase=tableCases.find(item=>item.id===button.dataset.testCase),detail=button.closest(".test-case-detail");if(!testCase||!detail)return;activeTrialByCase.set(testCase.id,Number(button.dataset.trialIndex));detail.outerHTML=testCaseTraces(testCase);bindTrialTabs()})}
function renderResultsTable(){
 const rows=tableCases.filter(testCase=>{
  const matches=!tableQuery||[testCase.taskId,testCase.persona,testCase.scenario,...testCase.trials.map(trial=>trial.id)].join(" ").toLowerCase().includes(tableQuery);
  const hasFail=Object.values(testCase.results).some(result=>result.status==="fail");
  return matches&&(!tableFailOnly||hasFail);
 });
 const visibleTrials=rows.reduce((total,testCase)=>total+testCase.trials.length,0),allTrials=tableCases.reduce((total,testCase)=>total+testCase.trials.length,0);
 document.getElementById("table-count").textContent=`${rows.length} of ${tableCases.length} test cases · ${visibleTrials} of ${allTrials} trials`;
 const groupHead=tableData.features.map(feature=>`<th class="feature-group" colspan="${Math.max(1,(feature.columns||[]).length)}">${esc(feature.name)}</th>`).join("");
 const graderHead=tableData.features.flatMap(feature=>(feature.columns||[]).map(column=>`<th class="grader-heading" title="${esc(column.grader_fqn)}"><strong>${esc(clip(column.grader_name||"No grader",24))}</strong><span>${esc(column.criterion)}</span></th>`)).join("");
 const columnCount=4+tableColumns.length;
 const body=rows.map(testCase=>{const expanded=expandedTrial===testCase.id;return `<tr class="result-table-row"><td class="expand-cell"><button type="button" data-expand-trial="${testCase.id}" aria-expanded="${expanded}" aria-label="${expanded?"Hide":"Show"} trials for ${esc(testCase.persona)} and ${esc(testCase.scenario)}"><i></i></button></td><td class="persona-cell"><strong>${esc(testCase.persona||"No persona")}</strong><span>${esc(testCase.taskId)} · ${testCase.trials.length} trial${testCase.trials.length===1?"":"s"}</span></td><td>${esc(testCase.scenario||"No scenario")}</td><td>${outcomeCell(testCase)}</td>${tableColumns.map(column=>`<td class="grader-result-cell">${graderCell(testCase,column)}</td>`).join("")}</tr>${expanded?`<tr class="conversation-row"><td colspan="${columnCount}">${testCaseTraces(testCase)}</td></tr>`:""}`}).join("");
 document.getElementById("results-table").innerHTML=rows.length?`<table class="results-table"><thead><tr><th class="sticky-meta expand-cell" rowspan="2"></th><th class="sticky-meta persona-cell" rowspan="2">Persona</th><th class="sticky-meta scenario-cell" rowspan="2">Scenario</th><th class="sticky-meta outcome-cell" rowspan="2">Trial outcomes</th>${groupHead}</tr><tr>${graderHead}</tr></thead><tbody>${body}</tbody></table>`:'<div class="blank-note">No test cases match this view.</div>';
 document.querySelectorAll("[data-expand-trial]").forEach(button=>button.onclick=()=>{expandedTrial=expandedTrial===button.dataset.expandTrial?"":button.dataset.expandTrial;renderResultsTable()});
 bindTrialTabs();
}
document.getElementById("table-search").addEventListener("input",event=>{tableQuery=event.target.value.trim().toLowerCase();renderResultsTable()});
document.getElementById("table-fail-only").onclick=event=>{tableFailOnly=!tableFailOnly;event.currentTarget.setAttribute("aria-pressed",String(tableFailOnly));event.currentTarget.classList.toggle("active",tableFailOnly);renderResultsTable()};

const outcomeConfig=[{key:"succeeded",label:"Succeeded"},{key:"abandoned",label:"Abandoned"},{key:"timedOut",label:"Timed out"},{key:"error",label:"Errors"}];
let activeOutcome="error";
const outcomeItems=trials.items||[];
document.getElementById("outcome-count").textContent=`${trials.attempted} attempted`;
const failureSourceLabel=source=>source==="target"?(V.target||"Target"):source==="userAgent"?"User agent":source==="evaluationRunner"?"Evaluation runner":source==="outcome"?"No error":"Not recorded";
const recordedOutcomeMessage=item=>{const message=item.message||item.stopReason||"unknown";if(item.category==="succeeded")return "No error";if(item.category==="abandoned"&&message===item.stopReason)return "No error message recorded";return message};
let openOutcomeGroup="";
function renderOutcomes(){
 const counts=Object.fromEntries(outcomeConfig.map(c=>[c.key,outcomeItems.filter(item=>item.category===c.key).length]));
 document.getElementById("outcome-bar").innerHTML=outcomeConfig.map(c=>counts[c.key]?`<button type="button" class="segment ${c.key}" data-key="${c.key}" style="width:${100*counts[c.key]/Math.max(1,trials.attempted)}%" title="${c.label}: ${counts[c.key]}"><span>${counts[c.key]}</span></button>`:"").join("");
 document.getElementById("outcome-tabs").innerHTML=[{key:"all",label:"All",count:trials.attempted},...outcomeConfig.map(c=>({...c,count:counts[c.key]}))].map(c=>`<button type="button" data-key="${c.key}" class="${activeOutcome===c.key?'active':''}">${esc(c.label)} <b>${c.count}</b></button>`).join("");
 document.querySelectorAll("#outcome-bar button,#outcome-tabs button").forEach(button=>button.onclick=()=>{activeOutcome=button.dataset.key;openOutcomeGroup="";renderOutcomes()});
 const filtered=activeOutcome==="all"?outcomeItems:outcomeItems.filter(item=>item.category===activeOutcome);
 const groups=new Map();for(const item of filtered){const features=(item.features||[]).join(" · ")||"Not mapped",source=item.failureSource||"",message=recordedOutcomeMessage(item);const key=JSON.stringify([features,item.scenario||"",item.persona||"",source,item.category||"",message]);if(!groups.has(key))groups.set(key,{key,features,scenario:item.scenario||"",persona:item.persona||"",source,message,items:[]});groups.get(key).items.push(item)}
 const rows=[...groups.values()].sort((a,b)=>b.items.length-a.items.length||a.features.localeCompare(b.features)||a.scenario.localeCompare(b.scenario)||a.persona.localeCompare(b.persona));
 document.getElementById("outcome-detail").innerHTML=rows.length?`<div class="outcome-table-wrap"><table class="outcome-table"><thead><tr><th>Feature</th><th>Scenario</th><th>Persona</th><th>Error source</th><th>Message</th><th>Trials</th></tr></thead><tbody>${rows.map((group,index)=>{const open=openOutcomeGroup===group.key,source=failureSourceLabel(group.source);return `<tr class="outcome-row"><td><button type="button" data-outcome-group="${index}" aria-expanded="${open}"><i></i><span>${esc(group.features)}</span></button></td><td>${esc(group.scenario||"—")}</td><td>${esc(group.persona||"—")}</td><td>${esc(source)}</td><td class="outcome-message-cell">${esc(group.message)}</td><td class="eval-count">${group.items.length}</td></tr><tr class="outcome-detail-row"${open?"":" hidden"}><td colspan="6"><div class="trial-list">${group.items.map(item=>`<div><strong>${esc(item.id)}</strong><span>${esc(item.persona)} · ${esc(item.scenario)}</span><span>${item.total_turns} turns${item.duration==null?"":` · ${Math.round(item.duration)}s`}${item.attempt>1?" · retried":""}</span></div>`).join("")}</div></td></tr>`}).join("")}</tbody></table></div>`:'<div class="blank-note">No trials in this group.</div>';
 document.querySelectorAll("[data-outcome-group]").forEach(button=>button.onclick=()=>{const group=rows[Number(button.dataset.outcomeGroup)];openOutcomeGroup=openOutcomeGroup===group.key?"":group.key;renderOutcomes()});
}
const unmappedPanel=document.getElementById("unmapped-results");
unmappedPanel.innerHTML=unmappedResults(V.unmapped||[]);
unmappedPanel.hidden=!(V.unmapped||[]).length;
renderOutcomes();renderSelection();renderTree();
document.addEventListener("click",event=>{document.querySelectorAll(".filter-dropdown[open]").forEach(dropdown=>{if(!dropdown.contains(event.target)){dropdown.open=false;openResultFilter=""}})});
let redrawTimer;addEventListener("resize",()=>{clearTimeout(redrawTimer);redrawTimer=setTimeout(renderTree,100)});addEventListener("scroll",hideTip,true);
"""


def render_report_page(
    report: dict[str, Any], *, title: str = "Target evaluation"
) -> str:
    """Build one offline HTML document from a report dictionary."""
    data = json.dumps(report, separators=(",", ":"), default=str).replace("</", "<\\/")
    script = REPORT_SCRIPT.replace(DATA_TOKEN, data)
    safe_title = (
        str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{safe_title}</title>\n<style>{REPORT_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{REPORT_BODY}\n<script>\n(function(){{\n{script}\n}})();\n</script>\n"
        "</body>\n</html>\n"
    )
