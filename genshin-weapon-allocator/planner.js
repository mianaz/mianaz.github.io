/* Scenario planning: shared inventory; independent theater roster and reservations.
   External trial/friend equipment never consumes or expands account inventory. */
'use strict';
const WeaponPlanner=(()=>{
 const A=typeof WeaponAllocator!=='undefined'?WeaponAllocator:require('./allocator.js');
 const clone=x=>JSON.parse(JSON.stringify(x));
 const blankTheater=()=>({name:'我的剧诗方案',roster:[],reservations:{},priorities:{},locks:{},use_account_locks:false});
 const dict=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
 function int(x,min,max,label){if(!Number.isSafeInteger(x)||x<min||x>max)throw Error(`${label}必须为${min}–${max}整数。`);}
 function normalize(input){
  const d=clone(input);A.validate(d);
  if(d.planning===undefined)d.planning={mode:'account',theater:blankTheater(),saved_plans:[]};
  if(!dict(d.planning))throw Error('planning必须是对象。');
  if(d.planning.saved_plans===undefined)d.planning.saved_plans=[];
  if(Array.isArray(d.assumptions))d.assumptions=d.assumptions.map(s=>typeof s==='string'?s.replace('可在库存中改为0/1/2。','库存现可自定义为0或正整数。'):s);
  d.schema_version=2;d.tool_version='2.0.0';validate(d);return d;
 }
 function validateTheater(t,d){
  if(!dict(t)||typeof t.name!=='string'||!t.name.trim()||t.name.length>120)throw Error('剧诗方案名需为1–120个字符。');
  if(!Array.isArray(t.roster))throw Error('剧诗roster必须是列表。');
  const cm=new Map(d.characters.map(c=>[c.id,c])),wm=new Map(d.weapons.map(w=>[w.id,w]));
  const seen=new Set();
  for(const r of t.roster){
   if(!dict(r)||!cm.has(r.character_id)||seen.has(r.character_id))throw Error('剧诗名单包含未知或重复角色。');
   seen.add(r.character_id);
   if(!['own','trial','friend'].includes(r.source))throw Error('角色来源必须是自有、试用或好友助演。');
   if(r.weapon_label!==undefined&&(typeof r.weapon_label!=='string'||r.weapon_label.length>300))throw Error('外部装备备注需为300字符以内的文字。');
  }
  if(typeof t.use_account_locks!=='boolean')throw Error('use_account_locks必须是布尔值。');
  for(const key of ['reservations','priorities','locks'])if(!dict(t[key]))throw Error(`剧诗${key}必须是对象。`);
  for(const [wid,q] of Object.entries(t.reservations)){if(!wm.has(wid))throw Error('预留了未知武器：'+wid);int(q,0,A.MAX_QUANTITY,'预留数量');}
  for(const [cid,q] of Object.entries(t.priorities)){if(!cm.has(cid))throw Error('优先级包含未知角色：'+cid);int(q,0,100,'剧诗优先级');}
  for(const [cid,wid] of Object.entries(t.locks)){
   if(!cm.has(cid)||(wid!==null&&!Object.hasOwn(cm.get(cid).scores,wid)))throw Error('剧诗锁定了未知角色或未评分武器。');
  }
 }
 function validate(d){
  A.validate(d);const p=d.planning;
  if(!dict(p)||!['account','theater'].includes(p.mode))throw Error('分配模式必须为account或theater。');
  validateTheater(p.theater,d);
  if(!Array.isArray(p.saved_plans)||p.saved_plans.length>50)throw Error('最多保存50个剧诗方案。');
  for(const t of p.saved_plans)validateTheater(t,d);
 }
 function prepare(d){
  validate(d);const effective=clone(d),p=d.planning,t=p.theater,external=[];
  if(p.mode==='theater'){
   const own=new Set(t.roster.filter(r=>r.source==='own').map(r=>r.character_id));
   const cm=new Map(d.characters.map(c=>[c.id,c]));
   for(const r of t.roster)if(r.source!=='own'){
    const c=cm.get(r.character_id);
    external.push({character_id:c.id,character:c.name,type:c.type,source:r.source,
      weapon_label:r.weapon_label||(r.source==='trial'?'试用自带装备':'好友自带装备'),consumes_inventory:false});
   }
   for(const c of effective.characters){
    c.enabled=own.has(c.id);
    if(Object.hasOwn(t.priorities,c.id))c.priority=t.priorities[c.id];
    c.locked_weapon=Object.hasOwn(t.locks,c.id)?t.locks[c.id]:(t.use_account_locks?c.locked_weapon:null);
   }
   for(const w of effective.weapons){
    const reserved=t.reservations[w.id]||0;
    if(reserved>w.quantity)throw Error(`${w.name}预留${reserved}把，超过实际库存${w.quantity}把。`);
    w.quantity-=reserved;
   }
  }
  delete effective.planning;
  const ownCount=effective.characters.filter(c=>c.enabled!==false).length;
  return {effective,external,context:{mode:p.mode,name:p.mode==='theater'?t.name:'全角色方案',
   roster_count:ownCount+external.length,own_count:ownCount,external_count:external.length,
   use_account_locks:p.mode==='account'||t.use_account_locks,
   reservations:p.mode==='theater'?clone(t.reservations):{},
   scope:'开演前为整份参演名单一次性配装；未验证当期入场资格，未优化每幕配队、活力或祝福。'}};
 }
 function plan(d){
  const {effective,external,context}=prepare(d),r=A.solve(effective);
  const total=new Map(d.weapons.map(w=>[w.id,w]));
  r.inventory=r.inventory.map(w=>{const original=total.get(w.id),reserved=context.reservations[w.id]||0;
   return {...w,quantity:original.quantity,reserved,available:original.quantity-reserved,remaining:original.quantity-reserved-w.used};});
  r.planning=context;r.external_characters=external;r.schema_version=2;r.tool_version='2.0.0';
  r.summary.roster_count=context.roster_count;r.summary.external_count=external.length;
  r.summary.total_physical_copies=d.weapons.reduce((s,w)=>s+w.quantity,0);
  r.summary.reserved_copies=r.inventory.reduce((s,w)=>s+w.reserved,0);
  return r;
 }
 return {blankTheater,normalize,validateTheater,validate,prepare,plan};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=WeaponPlanner;
