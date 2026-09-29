'use strict';
const initial=JSON.parse(document.getElementById('embeddedData').textContent);
const STORE='teyvat-armory-v2';
const $=id=>document.getElementById(id),clone=x=>JSON.parse(JSON.stringify(x));
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL=s=>{try{const u=new URL(s);return ['https:','http:'].includes(u.protocol)?u.href:'#';}catch{return '#';}};
let data=WeaponPlanner.normalize(initial),result=null,dirty=true,activeTab='allocation',editId=null,draftScores={},undoStock=null,bootWarning='';
let storedConfig=null;
try{storedConfig=localStorage.getItem(STORE);}catch{$('storageStatus').textContent='本地保存不可用，请使用“保存配置”备份';}
if(storedConfig){try{data=WeaponPlanner.normalize(JSON.parse(storedConfig));$('storageStatus').textContent='已恢复本浏览器保存的配置';}catch{bootWarning='本地配置未能恢复，已载入内置配置；可使用“导入配置”恢复备份。';}}
const theater=()=>data.planning.mode==='theater',T=()=>data.planning.theater;
function say(msg,cls=''){$('status').textContent=msg;$('status').className='status '+cls;}
function persist(){try{localStorage.setItem(STORE,JSON.stringify(data));$('storageStatus').textContent='已自动保存到本浏览器 · 导出配置可备份';}catch{$('storageStatus').textContent='本地保存不可用，请使用“保存配置”备份';}}
function readInt(el,min,max,label){const n=Number(el.value);if(!el.value.trim()||!Number.isSafeInteger(n)||n<min||n>max)throw Error(`${label}必须是${min}–${max}的整数。`);return n;}
function priority(c){return theater()?(T().priorities[c.id]??c.priority??1):(c.priority??1);}
function lock(c){return theater()?(Object.hasOwn(T().locks,c.id)?T().locks[c.id]:(T().use_account_locks?c.locked_weapon:null)):c.locked_weapon;}
function rosterMap(){return new Map(T().roster.map(r=>[r.character_id,r]));}
function markDirty(message='设置已保存。点击“重新分配”计算当前库存与名单。'){
 dirty=true;result=null;persist();say(message,'dirty');render();
}
function compute(){
 try{result=WeaponPlanner.plan(data);dirty=false;const s=result.summary;
  say(`${result.planning.name}：${s.character_count}位自有角色完成分配${s.external_count?`，另有${s.external_count}位自带装备角色`:''}。库存无冲突，当前评分最优性证书通过。${theater()&&!s.roster_count?' 请先在“参演角色”中添加本次名单。':''}`);
 }catch(e){result=null;dirty=true;say('无法完成分配：'+e.message,'error');}
 render();
}
function matches(c){const q=$('search').value.toLowerCase().trim(),t=$('typeFilter').value;return(!t||c.type===t)&&(!q||[c.name,c.character,c.role,c.notes,c.weapon,c.name_en,c.weapon_en,c.id].filter(Boolean).join(' ').toLowerCase().includes(q));}
function rosterMatches(c){const q=$('rosterSearch').value.trim().toLowerCase(),typ=$('rosterType').value;return(!q||[c.name,c.id,c.role].join(' ').toLowerCase().includes(q))&&(!typ||c.type===typ)&&(!$('selectedOnly').checked||T().roster.some(r=>r.character_id===c.id));}
function renderStats(){
 const s=result?.summary,own=theater()?T().roster.filter(r=>r.source==='own').length:data.characters.filter(c=>c.enabled!==false).length,ext=theater()?T().roster.filter(r=>r.source!=='own').length:0;
 $('nchars').textContent=s?`${s.character_count} / ${own}`:`待计算 / ${own}`;
 $('modeCount').textContent=theater()?`本次共${own+ext}位参演 · 自有${own} · 试用/助演${ext}`:`当前启用${own}位角色`;
 $('total').textContent=s?s.weighted_total.toLocaleString():'—';$('conflicts').textContent=s?'0':'—';$('gap').textContent=s?'间隙 0':'待计算';
 $('bestcount').textContent=s?`${s.first_choice_count}人达到候选首选分 · 最低${s.minimum_score??'—'}分`:'输入有变更，需要重新计算';
 $('rarities').textContent=s?`${s.five_star_count}把五星 + ${s.four_star_count}把四星`:'统计本人库存分配';
 $('csvBtn').disabled=$('resultBtn').disabled=dirty||!result;
 $('proofs').innerHTML=result?(Object.entries(result.certificates).map(([t,c])=>`${esc(t)}：费用 ${c.primal_cost} = 对偶界 ${c.dual_bound}；间隙 ${c.gap}`).join('<br>')||'当前没有需要本人库存配装的角色。'):'完成重新分配后显示证书。';
}
function setMode(mode){data.planning.mode=mode;$('search').value='';$('typeFilter').value='';persist();switchTab(mode==='theater'?'roster':'allocation');compute();}
function renderModes(){
 $('accountMode').classList.toggle('selected',!theater());$('theaterMode').classList.toggle('selected',theater());
 $('accountMode').setAttribute('aria-pressed',String(!theater()));$('theaterMode').setAttribute('aria-pressed',String(theater()));
 $('theaterSettings').classList.toggle('hidden',!theater());$('rosterTab').classList.toggle('hidden',!theater());
 $('planName').value=T().name;$('respectLocks').checked=T().use_account_locks;
 $('reserveHeader').textContent=theater()?'剧诗预留':'预留';$('clearReservations').disabled=!theater();
 const prev=$('savedPlans').value;
 $('savedPlans').innerHTML='<option value="">选择已保存的剧诗方案…</option>'+data.planning.saved_plans.map((p,i)=>`<option value="${i}">${esc(p.name)} · ${p.roster.length}人</option>`).join('');
 if([...$('savedPlans').options].some(o=>o.value===prev))$('savedPlans').value=prev;
}
function renderAllocation(){
 const rm=new Map((result?.assignment||[]).map(a=>[a.character_id,a])),em=new Map((result?.external_characters||[]).map(e=>[e.character_id,e])),roster=rosterMap();
 const rows=data.characters.filter(c=>(!theater()||roster.has(c.id))&&matches({...c,...(rm.get(c.id)||{})}));
 $('rows').innerHTML=rows.map(c=>{
  const a=rm.get(c.id),entry=roster.get(c.id),ext=theater()&&entry.source!=='own',e=em.get(c.id);
  const select=theater()?`<span class="sourcebadge">${ext?(entry.source==='trial'?'试用':'好友助演'):'自有'}</span>`:`<input type="checkbox" data-enable="${esc(c.id)}" aria-label="启用${esc(c.name)}" ${c.enabled!==false?'checked':''}>`;
  let weapon='<span class="muted">'+(c.enabled===false&&!theater()?'未启用':'待计算')+'</span>';
  if(ext)weapon=`<div>${esc(e?.weapon_label||entry.weapon_label||(entry.source==='trial'?'试用自带装备':'好友自带装备'))}</div><small class="muted">占用本人库存：0</small>`;
  else if(a)weapon=`<div class="weapon ${a.rarity===5?'gold':'purple'}">${esc(a.weapon)} <span class="copy">#${a.copy}</span></div><small class="muted">${a.rarity}★ · 精${a.refinement} · ${esc(a.type)}</small>`;
  return `<tr><td>${select}</td><td><div class="name">${esc(c.name)}</div><div class="role">${esc(c.role)}</div></td><td>${weapon}</td><td>${a?`<span class="score">${a.score}</span><div class="loss">距独立首选 ${a.regret}分</div>`:'—'}</td><td>${ext?'—':`<input class="weight" type="number" min="0" max="100" value="${priority(c)}" data-priority="${esc(c.id)}" aria-label="${esc(c.name)}优先级">`}</td><td>${ext?'<span class="muted">在参演名单编辑备注</span>':`<button class="mini" data-edit="${esc(c.id)}">${lock(c)?'已锁定 · 修改':'查看 / 编辑'}</button><div class="loss">${Object.keys(c.scores).length}个候选</div>`}</td></tr>`;
 }).join('')||`<tr><td colspan="6" class="empty">${theater()?'请在“参演角色”中添加名单，然后重新分配。':'没有匹配的角色。'}</td></tr>`;
 $('rowcount').textContent=`显示${rows.length}位 · ${theater()?'仅显示本次参演名单':'全角色工作区'}`;
 $('rows').querySelectorAll('[data-enable]').forEach(el=>el.onchange=()=>{data.characters.find(c=>c.id===el.dataset.enable).enabled=el.checked;markDirty();});
 bindPriority($('rows'));bindEditors($('rows'));
}
function bindPriority(root){root.querySelectorAll('[data-priority]').forEach(el=>el.onchange=()=>{const c=data.characters.find(c=>c.id===el.dataset.priority);try{const n=readInt(el,0,100,'优先级');if(theater())T().priorities[c.id]=n;else c.priority=n;markDirty();}catch(e){el.value=priority(c);say(e.message,'error');}});}
function bindEditors(root){root.querySelectorAll('[data-edit]').forEach(el=>el.onclick=()=>openEditor(el.dataset.edit));}
function renderRoster(){
 const rm=rosterMap(),rows=data.characters.filter(rosterMatches);
 $('rosterCount').textContent=`已选${T().roster.length}位 · 自有${T().roster.filter(r=>r.source==='own').length} · 试用${T().roster.filter(r=>r.source==='trial').length} · 好友${T().roster.filter(r=>r.source==='friend').length}。名单人数不代表已通过入场资格验证。`;
 $('rosterRows').innerHTML=rows.map(c=>{const r=rm.get(c.id),s=r?.source||'',ext=s==='trial'||s==='friend';return `<tr><td><select data-source="${esc(c.id)}" aria-label="${esc(c.name)}参演方式">${[['','未参演'],['own','自有角色'],['trial','试用角色'],['friend','好友助演']].map(([v,l])=>`<option value="${v}" ${v===s?'selected':''}>${l}</option>`).join('')}</select></td><td><div class="name">${esc(c.name)}</div><div class="role">${esc(c.role)}</div></td><td>${esc(c.type)}</td><td>${s==='own'?`<input type="number" class="weight" min="0" max="100" value="${priority(c)}" data-priority="${esc(c.id)}" aria-label="${esc(c.name)}剧诗优先级">`:'—'}</td><td>${ext?`<input class="externalnote" maxlength="300" data-external="${esc(c.id)}" aria-label="${esc(c.name)}自带装备备注" value="${esc(r.weapon_label||'')}" placeholder="可选：记录自带武器与精炼"><div class="loss">装备随角色使用 · 本人库存占用0</div>`:s==='own'?`<button class="mini" data-edit="${esc(c.id)}">${lock(c)?'剧诗锁定 · 修改':'候选与剧诗锁定'}</button>`:'<span class="muted">选择参演方式</span>'}</td></tr>`;}).join('')||'<tr><td colspan="5" class="empty">没有匹配的角色。</td></tr>';
 $('rosterRows').querySelectorAll('[data-source]').forEach(el=>el.onchange=()=>{const id=el.dataset.source,prev=rm.get(id);T().roster=T().roster.filter(r=>r.character_id!==id);if(el.value)T().roster.push({character_id:id,source:el.value,weapon_label:prev?.weapon_label||''});markDirty();});
 $('rosterRows').querySelectorAll('[data-external]').forEach(el=>el.onchange=()=>{T().roster.find(r=>r.character_id===el.dataset.external).weapon_label=el.value;markDirty();});
 bindPriority($('rosterRows'));bindEditors($('rosterRows'));
}
function bulkTargets(){const b=$('bulkScope').value;return data.weapons.filter(w=>b==='favonius'?w.name.startsWith('西风'):b==='sacrificial'?w.name.startsWith('祭礼'):b==='four'?w.rarity===4:b==='five'?w.rarity===5:matches(w));}
function renderInventory(){
 const used=result?.assignment||[],rows=data.weapons.filter(matches);
 $('inventoryRows').innerHTML=rows.map(w=>{const holders=used.filter(a=>a.weapon_id===w.id),reserved=theater()?(T().reservations[w.id]||0):0;
 return `<tr><td><div class="weapon ${w.rarity===5?'gold':'purple'}">${esc(w.name)}</div><small class="muted">${esc(w.name_en)}</small></td><td>${esc(w.type)}</td><td>${w.rarity}★ / 精${w.refinement}</td><td><input type="number" min="0" max="${WeaponAllocator.MAX_QUANTITY}" step="1" inputmode="numeric" value="${w.quantity}" class="stock" data-stock="${esc(w.id)}" aria-label="${esc(w.name)}库存"></td><td>${theater()?`<input type="number" min="0" max="${w.quantity}" step="1" inputmode="numeric" value="${reserved}" class="stock" data-reserve="${esc(w.id)}" aria-label="${esc(w.name)}剧诗预留">`:'—'}</td><td class="${reserved>w.quantity?'bad':''}">${w.quantity-reserved}</td><td>${result?holders.length:'—'}</td><td class="holders">${result?(holders.map(a=>esc(a.character)+' #'+a.copy).join('、')||'—'):'待计算'}</td></tr>`;}).join('');
 $('inventoryRows').querySelectorAll('[data-stock]').forEach(el=>el.onchange=()=>{const w=data.weapons.find(w=>w.id===el.dataset.stock);try{w.quantity=readInt(el,0,WeaponAllocator.MAX_QUANTITY,'库存');undoStock=null;markDirty();}catch(e){el.value=w.quantity;say(e.message,'error');}});
 $('inventoryRows').querySelectorAll('[data-reserve]').forEach(el=>el.onchange=()=>{const w=data.weapons.find(w=>w.id===el.dataset.reserve);try{const n=readInt(el,0,w.quantity,'预留');T().reservations[w.id]=n;markDirty();}catch(e){el.value=T().reservations[w.id]||0;say(e.message,'error');}});
 const targets=bulkTargets();$('bulkPreview').textContent=`将设置${targets.length}种武器${targets.length<=6?'：'+targets.map(w=>w.name).join('、'):''}`;
 $('undoBulk').disabled=!undoStock;
}
function renderSources(){
 $('assumptions').innerHTML=(data.assumptions||[]).map(a=>`<p>${esc(a)}</p>`).join('');
 const rated=data.characters.reduce((s,c)=>s+Object.keys(c.scores).length,0);
 $('coverage').textContent=`当前载入${data.characters.length}位角色、${data.weapons.length}种四五星武器、${rated}个候选评分。数据版本标签：${data.version||'自定义'}；资料日期：${data.as_of||'未标注'}。本次功能更新沿用原评分基线，部分配对仍待核验。`;
 $('sourcesList').innerHTML=(data.sources||[]).map(s=>`<div class="sourceitem"><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a><div class="muted">${esc(s.scope)}</div></div>`).join('');
}
function render(){renderModes();renderStats();renderAllocation();renderRoster();renderInventory();renderSources();}
function switchTab(name){activeTab=name;document.querySelectorAll('.tabpanel').forEach(e=>e.classList.toggle('hidden',e.id!==name));document.querySelectorAll('[data-tab]').forEach(e=>e.classList.toggle('active',e.dataset.tab===name));$('filters').classList.toggle('hidden',!['allocation','inventory'].includes(name));}
function download(name,text,type){const u=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function csvCell(v){let s=String(v??'');if(/^[\s]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}
function exportCSV(){if(dirty||!result)return;const rows=[['方案','角色','来源','武器','星级','精炼基线','副本','偏好分_非伤害','优先级','占用本人库存','前提备注']];
 result.assignment.forEach(a=>rows.push([result.planning.name,a.character,'自有',a.weapon,a.rarity,a.refinement,a.copy,a.score,a.priority,'是',a.notes]));
 result.external_characters.forEach(e=>rows.push([result.planning.name,e.character,e.source==='trial'?'试用':'好友助演',e.weapon_label,'','','','','','否','自带装备，不参与本人武器优化']));
 download(theater()?'genshin_theater_allocation.csv':'genshin_account_allocation.csv','\ufeff'+rows.map(r=>r.map(csvCell).join(',')).join('\r\n'),'text/csv;charset=utf-8');}
function parseRoster(text){
 const tokens=text.split(/[\n\r,，、;；\t]+/).map(s=>s.trim()).filter(Boolean);if(!tokens.length)throw Error('请先填写角色名单。');
 const chosen=new Set(),bad=[];
 for(const token of tokens){const q=token.toLowerCase();let found=data.characters.filter(c=>[c.id,c.name,c.name.replace(/（.*?）|\(.*?\)/g,'')].some(s=>s.toLowerCase()===q));
  if(!found.length)found=data.characters.filter(c=>c.name.includes(token));
  if(found.length!==1)bad.push(token+(found.length?'（匹配多名）':'（未找到）'));else chosen.add(found[0].id);
 }
 if(bad.length)throw Error('名单未导入，请修正：'+bad.join('、'));return [...chosen];
}
function applyRoster(replace){try{const ids=parseRoster($('rosterPaste').value),old=rosterMap();
 if(replace)T().roster=[];const existing=new Set(T().roster.map(r=>r.character_id));
 ids.forEach(id=>{if(!existing.has(id))T().roster.push(old.get(id)||{character_id:id,source:'own',weapon_label:''});});
 markDirty(`已${replace?'替换':'追加'}名单；共${T().roster.length}位。可逐人选择自有、试用或好友助演，然后重新分配。`);
 }catch(e){say(e.message,'error');}}
function syncDraft(){for(const el of $('candidateList').querySelectorAll('[data-score]'))draftScores[el.dataset.score]=readInt(el,0,100,'候选评分');}
function editorError(msg){$('editError').textContent=msg;$('editError').classList.remove('hidden');}
function renderCandidates(selected){const c=data.characters.find(c=>c.id===editId),wm=new Map(data.weapons.map(w=>[w.id,w]));
 $('candidateList').innerHTML=Object.entries(draftScores).map(([id,s])=>`<div class="candrow"><span class="${wm.get(id).rarity===5?'gold':'purple'}">${esc(wm.get(id).name)} <small class="muted">库存${wm.get(id).quantity}</small></span><input type="number" min="0" max="100" value="${s}" data-score="${esc(id)}" aria-label="${esc(wm.get(id).name)}评分"><button class="mini" data-remove="${esc(id)}" aria-label="移除${esc(wm.get(id).name)}">×</button></div>`).join('');
 $('candidateList').querySelectorAll('[data-remove]').forEach(el=>el.onclick=()=>{try{syncDraft();const l=$('editLock').value;delete draftScores[el.dataset.remove];renderCandidates(l);}catch(e){editorError(e.message);}});
 $('editLock').innerHTML='<option value="">自动分配（不锁定）</option>'+Object.keys(draftScores).map(id=>`<option value="${esc(id)}">${esc(wm.get(id).name)}</option>`).join('');$('editLock').value=Object.hasOwn(draftScores,selected)?selected:'';
 const available=data.weapons.filter(w=>w.type===c.type&&!Object.hasOwn(draftScores,w.id));$('addWeapon').innerHTML=available.map(w=>`<option value="${esc(w.id)}">${esc(w.name)} (${w.rarity}★)</option>`).join('');$('addCandidate').disabled=!available.length;
}
function openEditor(id){editId=id;const c=data.characters.find(c=>c.id===id);draftScores={...c.scores};$('editTitle').textContent=c.name;$('editReview').textContent=c.review||'自定义评分';$('editRole').value=c.role;$('editNote').value=c.notes||'';$('lockScope').textContent=theater()?'锁定武器（当前剧诗方案）':'锁定武器（全角色方案）';$('editError').classList.add('hidden');renderCandidates(lock(c));$('editSources').innerHTML=(c.sources||[]).map(s=>`<a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener noreferrer">参考资料</a> · ${esc(s.scope)}`).join('<br>');$('editor').showModal();}
$('addCandidate').onclick=()=>{try{syncDraft();const score=readInt($('addScore'),0,100,'新增评分'),wid=$('addWeapon').value;if(!wid)return;const l=$('editLock').value;draftScores[wid]=score;renderCandidates(l);}catch(e){editorError(e.message);}};
$('saveEdit').onclick=()=>{try{syncDraft();if(!Object.keys(draftScores).length)throw Error('至少保留一个候选。');const proposed=clone(data),c=proposed.characters.find(c=>c.id===editId);
 c.scores={...draftScores};c.role=$('editRole').value.trim()||c.role;c.notes=$('editNote').value;
 if(theater())proposed.planning.theater.locks[c.id]=$('editLock').value||null;else c.locked_weapon=$('editLock').value||null;
 // Removing a candidate which another saved plan locks would make that plan invalid.
 // Reject the edit and retain the original configuration rather than silently deleting locks.
 WeaponPlanner.validate(proposed);
 const prior=data.characters.find(x=>x.id===editId);
 if(JSON.stringify(prior.scores)!==JSON.stringify(c.scores)||prior.role!==c.role||prior.notes!==c.notes)c.review='用户编辑评分；需确认玩法与资料前提';
 data=proposed;$('editor').close();markDirty();compute();
 }catch(e){editorError(e.message+' 若其他方案锁定了被移除的候选，请先解除该锁定。');}};
['closeEditor','cancelEdit'].forEach(id=>$(id).onclick=()=>$('editor').close());
$('accountMode').onclick=()=>setMode('account');$('theaterMode').onclick=()=>setMode('theater');
$('solveBtn').onclick=()=>{compute();switchTab('allocation');};
$('search').oninput=()=>{renderAllocation();renderInventory();};$('typeFilter').onchange=()=>{renderAllocation();renderInventory();};
$('rosterSearch').oninput=renderRoster;$('rosterType').onchange=renderRoster;$('selectedOnly').onchange=renderRoster;
$('rosterReplace').onclick=()=>applyRoster(true);$('rosterAppend').onclick=()=>applyRoster(false);
$('rosterClear').onclick=()=>{if(T().roster.length&&!confirm('清空当前剧诗名单？已保存的方案仍可重新载入。'))return;T().roster=[];markDirty();};
$('rosterFiltered').onclick=()=>{const old=new Set(T().roster.map(r=>r.character_id));data.characters.filter(rosterMatches).forEach(c=>{if(!old.has(c.id))T().roster.push({character_id:c.id,source:'own',weapon_label:''});});markDirty();};
$('planName').onchange=()=>{const n=$('planName').value.trim();if(!n||n.length>120){$('planName').value=T().name;say('方案名需为1–120个字符。','error');return;}T().name=n;markDirty();};
$('respectLocks').onchange=()=>{T().use_account_locks=$('respectLocks').checked;markDirty();};
$('savePlan').onclick=()=>{try{WeaponPlanner.validate(data);const i=data.planning.saved_plans.findIndex(p=>p.name===T().name);if(i<0&&data.planning.saved_plans.length>=50)throw Error('最多保存50个方案。');if(i<0)data.planning.saved_plans.push(clone(T()));else data.planning.saved_plans[i]=clone(T());persist();renderModes();say('已保存剧诗名单、优先级、锁定与预留数量。武器总库存由所有方案共用。',dirty?'dirty':'');}catch(e){say(e.message,'error');}};
$('loadPlan').onclick=()=>{const v=$('savedPlans').value;if(v===''){say('请先选择一个已保存的剧诗方案。','error');return;}data.planning.theater=clone(data.planning.saved_plans[Number(v)]);markDirty();compute();};
$('newPlan').onclick=()=>{if(T().roster.length&&!confirm('建立空白剧诗方案？请先保存需要保留的当前名单。'))return;data.planning.theater=WeaponPlanner.blankTheater();$('rosterSearch').value='';$('selectedOnly').checked=false;markDirty();switchTab('roster');};
$('bulkScope').onchange=renderInventory;
$('applyBulk').onclick=()=>{try{const n=readInt($('bulkQuantity'),0,WeaponAllocator.MAX_QUANTITY,'批量库存'),targets=bulkTargets();if(!targets.length)throw Error('当前范围没有武器。');undoStock=Object.fromEntries(targets.map(w=>[w.id,w.quantity]));targets.forEach(w=>w.quantity=n);markDirty(`已将${targets.length}种武器各设为${n}把。请重新分配；“撤销批量”可恢复此次修改。`);}catch(e){say(e.message,'error');}};
$('undoBulk').onclick=()=>{if(!undoStock)return;for(const w of data.weapons)if(Object.hasOwn(undoStock,w.id))w.quantity=undoStock[w.id];undoStock=null;markDirty('已撤销上次批量库存修改。请重新分配。');};
$('clearReservations').onclick=()=>{if(!theater())return;T().reservations={};markDirty('已清空当前剧诗的预留数量。');};
$('configBtn').onclick=()=>download('genshin_allocator_v2_config.json',JSON.stringify(data,null,2),'application/json');
$('csvBtn').onclick=exportCSV;$('resultBtn').onclick=()=>{if(!dirty&&result)download('genshin_allocator_v2_result.json',JSON.stringify(result,null,2),'application/json');};
$('importBtn').onclick=()=>$('fileInput').click();$('fileInput').onchange=async()=>{const f=$('fileInput').files[0];if(!f)return;try{if(f.size>20*1024*1024)throw Error('配置超过20MB。');const parsed=WeaponPlanner.normalize(JSON.parse((await f.text()).replace(/^\uFEFF/,'')));data=parsed;undoStock=null;$('search').value='';$('typeFilter').value='';persist();switchTab('allocation');compute();}catch(e){say('导入失败，当前配置保留：'+e.message,'error');}finally{$('fileInput').value='';}};
document.querySelectorAll('[data-tab]').forEach(e=>e.onclick=()=>switchTab(e.dataset.tab));
window.appState=()=>({data:clone(data),result:clone(result),dirty,activeTab});
window.addEventListener('beforeunload',e=>{if(dirty&&!$('storageStatus').textContent.startsWith('已')){e.preventDefault();e.returnValue='';}});
$('theaterDetails').open=innerWidth>700;$('assumptionDetails').open=innerWidth>700;
compute();if(bootWarning)say(bootWarning,'error');
