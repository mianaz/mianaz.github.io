#!/usr/bin/env python3
"""Exact weapon allocation for a USER-SUPPLIED, sparse utility matrix.

No third-party dependencies. Scores in data.json are heuristic preferences, NOT
DPS percentages. A dual certificate proves only optimization of that matrix.
Usage: python allocator.py [--data data.json] [--out results] [--sensitivity]
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

TYPES = ('单手剑', '双手剑', '长柄武器', '法器', '弓')
MAX_QUANTITY = 1_000_000
MAX_CELLS = 2_000_000

class AllocationError(ValueError):
    """Invalid input or an infeasible complete allocation."""


def hungarian(cost: list[list[int]]) -> tuple[list[int], list[int], list[int]]:
    """Min-cost full ROW matching, n <= m. Returns columns and dual potentials.

    Successive augmentations maintain reduced costs c[i][j]-u[i]-v[j].
    Runtime O(n^2*m), memory O(n*m) including the caller's matrix.
    """
    n = len(cost)
    if n == 0:
        return [], [], []
    m = len(cost[0])
    if m < n or any(len(row) != m for row in cost):
        raise AllocationError('需要矩形矩阵且武器副本数不少于角色数。')
    # Index zero is a sentinel; real rows/columns start at one.
    u, v, owner, parent = [0]*(n+1), [0]*(m+1), [0]*(m+1), [0]*(m+1)
    infinity = 1 + sum(max(abs(x) for x in row) for row in cost) * (n+m+2)
    for row in range(1, n+1):
        owner[0] = row
        col = 0
        distance = [infinity]*(m+1)
        visited = [False]*(m+1)
        while True:
            visited[col] = True
            current_row = owner[col]
            step, next_col = infinity, 0
            for j in range(1, m+1):
                if visited[j]:
                    continue
                reduced = cost[current_row-1][j-1] - u[current_row] - v[j]
                if reduced < distance[j]:
                    distance[j], parent[j] = reduced, col
                if distance[j] < step:
                    step, next_col = distance[j], j
            if next_col == 0:
                raise AllocationError('没有可扩展的武器副本。')
            for j in range(m+1):
                if visited[j]:
                    u[owner[j]] += step
                    v[j] -= step
                else:
                    distance[j] -= step
            col = next_col
            if owner[col] == 0:
                break
        while col:
            previous = parent[col]
            owner[col] = owner[previous]
            col = previous
    assigned = [-1]*n
    for j in range(1, m+1):
        if owner[j]:
            assigned[owner[j]-1] = j-1
    return assigned, u[1:], v[1:]


def verify_certificate(cost: list[list[int]], cols: list[int],
                       u: list[int], v: list[int]) -> dict[str, Any]:
    """Independent primal/dual feasibility and equality checks with exact ints."""
    n = len(cost)
    m = len(cost[0]) if n else len(v)
    if len(cols) != n or len(u) != n or len(v) != m:
        raise AllocationError('证书维度不匹配。')
    if len(set(cols)) != n or any(j < 0 or j >= m for j in cols):
        raise AllocationError('证书包含重复或缺失的物理副本。')
    if any(x > 0 for x in v):
        raise AllocationError('矩形指派证书要求列势能不大于0。')
    if any(u[i]+v[j] > cost[i][j] for i in range(n) for j in range(m)):
        raise AllocationError('对偶不可行。')
    if any(u[i]+v[j] != cost[i][j] for i, j in enumerate(cols)):
        raise AllocationError('已匹配边不满足紧约束。')
    chosen = set(cols)
    if any(v[j] != 0 for j in range(m) if j not in chosen):
        raise AllocationError('未使用列不满足互补松弛。')
    primal = sum(cost[i][j] for i, j in enumerate(cols))
    dual = sum(u)+sum(v)
    if primal != dual:
        raise AllocationError('原始值与对偶值不相等。')
    return {'verified': True, 'primal_cost': primal, 'dual_bound': dual, 'gap': 0,
            'u': u, 'v': v, 'assigned_columns': cols}


def require_int(x: Any, lo: int, hi: int, label: str) -> None:
    if isinstance(x, bool) or not isinstance(x, int) or not lo <= x <= hi:
        raise AllocationError(f'{label}必须是{lo}到{hi}之间的整数。')


def validate(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or not isinstance(data.get('weapons'), list) or not isinstance(data.get('characters'), list):
        raise AllocationError('JSON必须含weapons与characters数组。')
    if len(data['characters']) > 1000 or len(data['weapons']) > 2000:
        raise AllocationError('当前实现限制1000角色、2000武器种类。')
    wm: dict[str, Any] = {}
    for w in data['weapons']:
        wid = w.get('id')
        if not isinstance(wid, str) or not wid or wid in wm:
            raise AllocationError('武器ID为空或重复。')
        if w.get('type') not in TYPES or w.get('rarity') not in (4,5):
            raise AllocationError(f'{wid}的类型/稀有度不合法；当前库存模型只支持四五星。')
        require_int(w.get('quantity'), 0, MAX_QUANTITY, f'{wid}数量')
        require_int(w.get('refinement'), 1, 5, f'{wid}精炼')
        wm[wid] = w
    ids = set()
    for c in data['characters']:
        cid = c.get('id')
        if not isinstance(cid,str) or not cid or cid in ids:
            raise AllocationError('角色ID为空或重复。')
        ids.add(cid)
        if c.get('type') not in TYPES:
            raise AllocationError(f'{cid}武器类型不合法。')
        require_int(c.get('priority',1), 0, 100, f'{cid}优先级')
        if not isinstance(c.get('enabled',True),bool):
            raise AllocationError(f'{cid} enabled必须是布尔值。')
        if not isinstance(c.get('scores'),dict) or not c['scores']:
            raise AllocationError(f'{cid}需要至少一个明确评分。')
        for wid, score in c['scores'].items():
            if wid not in wm or wm[wid]['type'] != c['type']:
                raise AllocationError(f'{cid}的候选{wid}不存在或武器类型不匹配。')
            require_int(score,0,100,f'{cid}/{wid}评分')
        lock = c.get('locked_weapon')
        if lock is not None and lock not in c['scores']:
            raise AllocationError(f'{cid}锁定了未评分武器；先添加明确评分。')


def build_problem(data: dict[str,Any], typ: str,
                  forbidden_pairs: set[tuple[str,str]] | None = None) -> dict[str,Any]:
    chars = [c for c in data['characters'] if c.get('enabled',True) and c['type']==typ]
    bans = forbidden_pairs or set()
    copies = []
    for w in data['weapons']:
        if w['type'] != typ:
            continue
        eligible = sum(w['id'] in c['scores'] and
                       (not c.get('locked_weapon') or c['locked_weapon'] == w['id']) and
                       (c['id'], w['id']) not in bans for c in chars)
        # Excess identical copies cannot be used and need not enter the matrix.
        copies.extend((w, j) for j in range(1, min(w['quantity'], eligible) + 1))
    if len(chars) * len(copies) > MAX_CELLS:
        raise AllocationError('评分矩阵超过安全规模，请减少候选或参演角色。')
    if len(chars) > len(copies):
        raise AllocationError(f'{typ}：{len(chars)}个角色，但只有{len(copies)}个可用副本。')
    base = [max(c['scores'].values()) for c in chars]
    maxcost = max((max(c['scores'].values())-min(c['scores'].values()))*c.get('priority',1) for c in chars) if chars else 0
    # Any feasible full matching costs <= n*maxcost. One forbidden edge must
    # be strictly more expensive than EVERY feasible full matching.
    blocked = len(chars)*maxcost+1
    bans = forbidden_pairs or set()
    allowed=[]
    cost=[]
    for i,c in enumerate(chars):
        row=[]
        flags=[]
        for w,j in copies:
            ok=(w['id'] in c['scores'] and (not c.get('locked_weapon') or c['locked_weapon']==w['id'])
                and (c['id'],w['id']) not in bans)
            flags.append(ok)
            row.append((base[i]-c['scores'][w['id']])*c.get('priority',1) if ok else blocked)
        if not any(flags):
            raise AllocationError(f"{c['name']}没有可用的已评分候选；请检查库存、锁定与评分。")
        cost.append(row)
        allowed.append(flags)
    return dict(characters=chars,copies=copies,cost=cost,allowed=allowed,blocked=blocked,base=base)


def solve(data: dict[str,Any], *, forbidden_pairs: set[tuple[str,str]] | None=None,
          certificates: bool=True) -> dict[str,Any]:
    validate(data)
    assignment=[]
    certs={}
    for typ in TYPES:
        prob=build_problem(data,typ,forbidden_pairs)
        chars,copies,cost=prob['characters'],prob['copies'],prob['cost']
        if not chars:
            continue
        cols,u,v=hungarian(cost)
        bad=[chars[i]['name'] for i,j in enumerate(cols) if not prob['allowed'][i][j]]
        if bad:
            raise AllocationError(f"{typ}候选库存冲突，无法让所有角色持有已评分武器。涉及：{'、'.join(bad)}。可补充候选评分或减少锁定，不能凭空复制武器。")
        cert=verify_certificate(cost,cols,u,v)
        if certificates:
            cert.update(row_ids=[c['id'] for c in chars],column_ids=[f"{w['id']}#{j}" for w,j in copies])
            certs[typ]=cert
        for i,j in enumerate(cols):
            c=chars[i]; w,num=copies[j]; s=c['scores'][w['id']]
            assignment.append(dict(character_id=c['id'],character=c['name'],type=typ,role=c['role'],
                weapon_id=w['id'],weapon=w['name'],weapon_en=w.get('name_en',''),copy=num,
                physical_id=f"{w['id']}#{num}",rarity=w['rarity'],refinement=w['refinement'],
                score=s,priority=c.get('priority',1),weighted_score=s*c.get('priority',1),
                individual_best=prob['base'][i],regret=prob['base'][i]-s,
                notes=c.get('notes',''),review=c.get('review','自定义评分'),sources=c.get('sources',[])))
    physical=[a['physical_id'] for a in assignment]
    if len(physical)!=len(set(physical)):
        raise AllocationError('内部错误：发生物理副本重复。')
    wm={w['id']:w for w in data['weapons']}
    usage=Counter(a['weapon_id'] for a in assignment)
    if any(n>wm[wid]['quantity'] for wid,n in usage.items()):
        raise AllocationError('内部错误：超过库存。')
    digest=hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(schema_version=1,version=data.get('version'),as_of=data.get('as_of'),
        warning='这是当前启发式评分候选池的精确最优解，不是真实伤害全局最优证明。',
        input_sha256=digest,assignment=assignment,certificates=certs,
        summary=dict(character_count=len(assignment),weapon_kinds_in_inventory=len(wm),
            physical_copies=sum(w['quantity'] for w in wm.values()),
            scored_pairs=sum(len(c['scores']) for c in data['characters'] if c.get('enabled',True)),
            total_score=sum(a['score'] for a in assignment),
            weighted_total=sum(a['weighted_score'] for a in assignment),
            weighted_regret=sum(a['regret']*a['priority'] for a in assignment),
            first_choice_count=sum(a['regret']==0 for a in assignment),
            minimum_score=min((a['score'] for a in assignment),default=None),
            five_star_count=sum(a['rarity']==5 for a in assignment),
            four_star_count=sum(a['rarity']==4 for a in assignment),
            used_weapon_kinds=len(usage),inventory_violation_count=0,
            certificate_verified=all(c['verified'] for c in certs.values())),
        inventory=[dict(**w,used=usage[w['id']],remaining=w['quantity']-usage[w['id']]) for w in data['weapons']])


def greedy(data: dict[str,Any]) -> dict[str,Any]:
    """Input-order greedy comparator, NOT an optimizer."""
    wm={w['id']:w for w in data['weapons']}
    stock={wid:w['quantity'] for wid,w in wm.items()}
    rows=[]
    for c in data['characters']:
        if not c.get('enabled',True): continue
        options=[wid for wid in wm if stock[wid]>0 and wid in c['scores']
                 and (not c.get('locked_weapon') or c['locked_weapon']==wid)]
        if not options:
            return dict(feasible=False,failed_at=c['name'],assigned_count=len(rows))
        best=max(options,key=lambda wid:c['scores'][wid])
        stock[best]-=1
        rows.append(dict(character=c['name'],weapon=wm[best]['name'],score=c['scores'][best],weighted_score=c['scores'][best]*c.get('priority',1)))
    return dict(feasible=True,total_score=sum(r['score'] for r in rows),weighted_total=sum(r['weighted_score'] for r in rows),assignment=rows)


def sensitivity(data: dict[str,Any], result: dict[str,Any]) -> list[dict[str,Any]]:
    """Forbid the selected weapon KIND for one character, then re-optimize ALL.

    Gap zero => a tied global solution avoiding this edge exists. This is NOT a
    DPS loss, a probability, or an arbitrary score-perturbation robustness test.
    """
    out=[]
    base=result['summary']['weighted_total']
    for a in result['assignment']:
        row={'character_id':a['character_id'],'character':a['character'],'weapon':a['weapon']}
        try:
            alt=solve(data,forbidden_pairs={(a['character_id'],a['weapon_id'])},certificates=False)
            b=next(b for b in alt['assignment'] if b['character_id']==a['character_id'])
            row.update(alternative_feasible=True,global_score_loss=base-alt['summary']['weighted_total'],alternative_weapon=b['weapon'])
        except AllocationError as err:
            row.update(alternative_feasible=False,reason=str(err))
        out.append(row)
    return out


def csv_safe(value: Any) -> Any:
    # Prevent formula execution on opening a user-edited export in Excel.
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
        return "'"+value
    return value


def write_results(result: dict[str,Any], out: Path) -> None:
    out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    fields={'character':'角色','type':'武器类型','role':'默认玩法','weapon':'分配武器','rarity':'星级',
            'refinement':'精炼','copy':'副本编号','score':'启发式评分_非伤害百分比','priority':'优先级',
            'regret':'相对独立首选的评分损失','notes':'前提备注','review':'资料核验状态'}
    with (out/'allocation.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f); writer.writerow(fields.values())
        for a in result['assignment']:
            writer.writerow([csv_safe(a.get(k,'')) for k in fields])
    with (out/'inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f); writer.writerow(['武器','英文名','类型','星级','库存','已用','剩余'])
        for w in result['inventory']:
            writer.writerow([csv_safe(w[k]) for k in ('name','name_en','type','rarity','quantity','used','remaining')])


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path(__file__).with_name('data.json'))
    parser.add_argument('--out',type=Path,default=Path(__file__).with_name('results'))
    parser.add_argument('--sensitivity',action='store_true',help='对每个选中配对禁用后重算，输出全局替代损失')
    args=parser.parse_args()
    try:
        data=json.loads(args.data.read_text(encoding='utf-8-sig'))
        if 'planning' in data:
            # Preserve the original CLI while honoring a v2 theater configuration.
            from planner import normalize, prepare, plan, export_results
            data=normalize(data)
            effective, _, _ = prepare(data)
            result=plan(data)
            output_writer=export_results
        else:
            effective=data
            result=solve(data)
            output_writer=write_results
        result['greedy_comparison']=greedy(effective)
        if args.sensitivity: result['sensitivity']=sensitivity(effective,result)
        output_writer(result,args.out)
        print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
        print(f'输出：{args.out.resolve()}')
        print(result['warning'])
    except (OSError,ValueError) as err:
        parser.exit(2,f'分配失败：{err}\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
