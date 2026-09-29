/* Exact rectangular assignment with an independent primal/dual certificate.
   No dependencies, networking, account access, or combat simulation. */
'use strict';
const WeaponAllocator = (() => {
 const TYPES=['单手剑','双手剑','长柄武器','法器','弓'];
 const MAX_QUANTITY=1000000,MAX_CELLS=2000000;
 function integer(x,min,max,label) {if(!Number.isSafeInteger(x)||x<min||x>max)throw Error(`${label}必须为${min}–${max}整数。`);}
 function validate(d) {
  if(!d||!Array.isArray(d.characters)||!Array.isArray(d.weapons))throw Error('配置必须包含characters与weapons数组。');
  if(d.characters.length>1000||d.weapons.length>2000)throw Error('当前限制1000个角色、2000种武器。');
  const wm=new Map();
  d.weapons.forEach(w=>{if(typeof w.id!=='string'||!w.id||wm.has(w.id))throw Error('武器ID为空或重复。');
   if(!TYPES.includes(w.type)||![4,5].includes(w.rarity))throw Error(`${w.id}武器类型或星级非法。`);
   integer(w.quantity,0,MAX_QUANTITY,w.id+'库存'); integer(w.refinement,1,5,w.id+'精炼'); wm.set(w.id,w);});
  const seen=new Set();
  d.characters.forEach(c=>{if(typeof c.id!=='string'||!c.id||seen.has(c.id))throw Error('角色ID为空或重复。');seen.add(c.id);
   if(!TYPES.includes(c.type))throw Error(c.id+'武器类型非法。');
   integer(c.priority??1,0,100,c.id+'优先级');if(c.enabled!==undefined&&typeof c.enabled!=='boolean')throw Error('enabled必须是布尔值。');
   if(!c.scores||Array.isArray(c.scores)||typeof c.scores!=='object'||!Object.keys(c.scores).length)throw Error(c.id+'必须至少有一个候选评分。');
   Object.entries(c.scores).forEach(([wid,s])=>{if(!wm.has(wid)||wm.get(wid).type!==c.type)throw Error(c.id+'/'+wid+'类型不匹配或不存在。');integer(s,0,100,c.id+'/'+wid+'评分');});
   if(c.locked_weapon!=null&&!Object.hasOwn(c.scores,c.locked_weapon))throw Error(c.id+'锁定武器尚未评分。');
  });
 }
 function hungarian(cost) {
  const n=cost.length;if(!n)return {cols:[],u:[],v:[]};const m=cost[0].length;
  if(m<n||cost.some(r=>r.length!==m))throw Error('武器副本不足或矩阵不规则。');
  const u=Array(n+1).fill(0),v=Array(m+1).fill(0),owner=Array(m+1).fill(0),parent=Array(m+1).fill(0);
  for(let r=1;r<=n;r++){
   owner[0]=r;let col=0;const dist=Array(m+1).fill(Infinity),seen=Array(m+1).fill(false);
   do{seen[col]=true;const row=owner[col];let delta=Infinity,next=0;
    for(let j=1;j<=m;j++)if(!seen[j]){const rc=cost[row-1][j-1]-u[row]-v[j];if(rc<dist[j]){dist[j]=rc;parent[j]=col;}if(dist[j]<delta){delta=dist[j];next=j;}}
    if(!next)throw Error('无法找到增广路径。');
    for(let j=0;j<=m;j++){if(seen[j]){u[owner[j]]+=delta;v[j]-=delta;}else dist[j]-=delta;}
    col=next;
   }while(owner[col]!==0);
   do{const prev=parent[col];owner[col]=owner[prev];col=prev;}while(col);
  }
  const cols=Array(n).fill(-1);for(let j=1;j<=m;j++)if(owner[j])cols[owner[j]-1]=j-1;
  return {cols,u:u.slice(1),v:v.slice(1)};
 }
 function verify(cost,{cols,u,v}){
  const n=cost.length,m=n?cost[0].length:v.length;
  if(cols.length!==n||u.length!==n||v.length!==m||new Set(cols).size!==n||cols.some(j=>j<0||j>=m))throw Error('分配证书维度/副本不合法。');
  if(v.some(x=>x>0))throw Error('列势能非法。');
  for(let i=0;i<n;i++)for(let j=0;j<m;j++)if(u[i]+v[j]>cost[i][j])throw Error('对偶可行性校验失败。');
  for(let i=0;i<n;i++)if(u[i]+v[cols[i]]!==cost[i][cols[i]])throw Error('匹配边不满足紧约束。');
  const chosen=new Set(cols);for(let j=0;j<m;j++)if(!chosen.has(j)&&v[j]!==0)throw Error('未使用列势能校验失败。');
  const primal=cols.reduce((s,j,i)=>s+cost[i][j],0),dual=u.reduce((a,b)=>a+b,0)+v.reduce((a,b)=>a+b,0);
  if(primal!==dual)throw Error('最优性间隙不为零。');return {verified:true,primal_cost:primal,dual_bound:dual,gap:0,u,v,assigned_columns:cols};
 }
 function solve(d,bans=new Set()){
  validate(d);const assignment=[],certificates={};
  for(const type of TYPES){const chars=d.characters.filter(c=>c.enabled!==false&&c.type===type),copies=[];
   // A weapon can serve at most as many characters as have a permitted edge.
   // Surplus identical copies are omitted without changing the feasible assignments.
   d.weapons.filter(w=>w.type===type).forEach(w=>{
    const eligible=chars.filter(c=>Object.hasOwn(c.scores,w.id)&&(!c.locked_weapon||c.locked_weapon===w.id)&&!bans.has(c.id+'|'+w.id)).length;
    for(let j=1;j<=Math.min(w.quantity,eligible);j++)copies.push({w,num:j});
   });
   if(chars.length*copies.length>MAX_CELLS)throw Error('评分矩阵超过浏览器安全规模，请减少候选或参演角色。');
   if(chars.length>copies.length)throw Error(`${type}：${chars.length}位角色，但仅${copies.length}个副本。`);if(!chars.length)continue;
   const base=chars.map(c=>Math.max(...Object.values(c.scores)));
   const maxcost=Math.max(...chars.map((c,i)=>(base[i]-Math.min(...Object.values(c.scores)))*(c.priority??1)));
   const blocked=chars.length*maxcost+1,allowed=[];
   const cost=chars.map((c,i)=>copies.map(({w})=>{
    const ok=Object.hasOwn(c.scores,w.id)&&(!c.locked_weapon||c.locked_weapon===w.id)&&!bans.has(c.id+'|'+w.id);
    (allowed[i]??=[]).push(ok);return ok?(base[i]-c.scores[w.id])*(c.priority??1):blocked;
   }));
   chars.forEach((c,i)=>{if(!allowed[i].some(Boolean))throw Error(c.name+'没有可用的已评分候选。请检查库存和锁定。');});
   const h=hungarian(cost);const bad=chars.filter((c,i)=>!allowed[i][h.cols[i]]);
   if(bad.length)throw Error(`${type}候选争抢导致无解：${bad.map(c=>c.name).join('、')}。请增加合法候选或取消冲突锁定。`);
   const cert=verify(cost,h);cert.row_ids=chars.map(c=>c.id);cert.column_ids=copies.map(({w,num})=>w.id+'#'+num);certificates[type]=cert;
   chars.forEach((c,i)=>{const {w,num}=copies[h.cols[i]],score=c.scores[w.id];assignment.push({character_id:c.id,character:c.name,type,role:c.role,weapon_id:w.id,weapon:w.name,weapon_en:w.name_en||'',copy:num,physical_id:w.id+'#'+num,rarity:w.rarity,refinement:w.refinement,score,priority:c.priority??1,weighted_score:score*(c.priority??1),individual_best:base[i],regret:base[i]-score,notes:c.notes||'',review:c.review||'自定义评分',sources:c.sources||[]});});
  }
  const usage={};assignment.forEach(a=>usage[a.weapon_id]=(usage[a.weapon_id]||0)+1);
  if(new Set(assignment.map(a=>a.physical_id)).size!==assignment.length)throw Error('内部错误：重复分配副本。');
  const inventory=d.weapons.map(w=>({...w,used:usage[w.id]||0,remaining:w.quantity-(usage[w.id]||0)}));
  if(inventory.some(w=>w.remaining<0))throw Error('内部错误：超过库存。');
  const summary={character_count:assignment.length,weapon_kinds_in_inventory:d.weapons.length,physical_copies:d.weapons.reduce((s,w)=>s+w.quantity,0),scored_pairs:d.characters.filter(c=>c.enabled!==false).reduce((s,c)=>s+Object.keys(c.scores).length,0),total_score:assignment.reduce((s,a)=>s+a.score,0),weighted_total:assignment.reduce((s,a)=>s+a.weighted_score,0),weighted_regret:assignment.reduce((s,a)=>s+a.regret*a.priority,0),first_choice_count:assignment.filter(a=>a.regret===0).length,minimum_score:assignment.length?Math.min(...assignment.map(a=>a.score)):null,five_star_count:assignment.filter(a=>a.rarity===5).length,four_star_count:assignment.filter(a=>a.rarity===4).length,used_weapon_kinds:Object.keys(usage).length,inventory_violation_count:0,certificate_verified:true};
  return {schema_version:1,version:d.version,as_of:d.as_of,warning:'只证明当前启发式评分候选池的精确最优；不是实战伤害证明。',summary,assignment,inventory,certificates};
 }
 return {TYPES,MAX_QUANTITY,MAX_CELLS,validate,hungarian,verify,solve};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=WeaponAllocator;
