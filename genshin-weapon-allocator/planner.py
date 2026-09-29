#!/usr/bin/env python3
"""Shared inventory plus an independent Imaginarium Theater preparation scenario.
Run: python planner.py --data data.json --out results [--mode theater]
The solver optimizes supplied utilities. It does not validate season eligibility,
choose teams for individual acts, or score trial/friend equipment.
"""
from __future__ import annotations
import argparse
import copy
import csv
import json
from pathlib import Path
from typing import Any
from allocator import AllocationError, MAX_QUANTITY, require_int, validate as validate_data, solve, write_results, csv_safe


def blank_theater() -> dict[str, Any]:
    return dict(name='我的剧诗方案',roster=[],reservations={},priorities={},locks={},use_account_locks=False)


def normalize(value: dict[str, Any]) -> dict[str, Any]:
    d=copy.deepcopy(value)
    validate_data(d)
    if 'planning' not in d:
        d['planning']=dict(mode='account',theater=blank_theater(),saved_plans=[])
    if not isinstance(d['planning'],dict):
        raise AllocationError('planning必须是对象。')
    d['planning'].setdefault('saved_plans',[])
    if isinstance(d.get('assumptions'),list):
        d['assumptions']=[s.replace('可在库存中改为0/1/2。','库存现可自定义为0或正整数。') if isinstance(s,str) else s for s in d['assumptions']]
    d['schema_version']=2
    d['tool_version']='2.0.0'
    validate(d)
    return d


def validate_theater(t: Any, d: dict[str, Any]) -> None:
    if not isinstance(t,dict) or not isinstance(t.get('name'),str) or not t['name'].strip() or len(t['name'])>120:
        raise AllocationError('剧诗方案名需为1–120个字符。')
    if not isinstance(t.get('roster'),list):
        raise AllocationError('剧诗roster必须是列表。')
    cm={c['id']:c for c in d['characters']}
    wm={w['id']:w for w in d['weapons']}
    seen=set()
    for r in t['roster']:
        if not isinstance(r,dict) or not isinstance(r.get('character_id'),str) or r['character_id'] not in cm or r['character_id'] in seen:
            raise AllocationError('剧诗名单包含未知或重复角色。')
        seen.add(r['character_id'])
        if r.get('source') not in ('own','trial','friend'):
            raise AllocationError('角色来源必须是自有、试用或好友助演。')
        if 'weapon_label' in r and (not isinstance(r['weapon_label'],str) or len(r['weapon_label'])>300):
            raise AllocationError('外部装备备注需为300字符以内的文字。')
    if not isinstance(t.get('use_account_locks'),bool):
        raise AllocationError('use_account_locks必须是布尔值。')
    for key in ('reservations','priorities','locks'):
        if not isinstance(t.get(key),dict):
            raise AllocationError(f'剧诗{key}必须是对象。')
    for wid,q in t['reservations'].items():
        if wid not in wm: raise AllocationError('预留了未知武器：'+wid)
        require_int(q,0,MAX_QUANTITY,'预留数量')
    for cid,q in t['priorities'].items():
        if cid not in cm: raise AllocationError('优先级包含未知角色：'+cid)
        require_int(q,0,100,'剧诗优先级')
    for cid,wid in t['locks'].items():
        if cid not in cm or (wid is not None and (not isinstance(wid,str) or wid not in cm[cid]['scores'])):
            raise AllocationError('剧诗锁定了未知角色或未评分武器。')


def validate(d: dict[str,Any]) -> None:
    validate_data(d)
    p=d.get('planning')
    if not isinstance(p,dict) or p.get('mode') not in ('account','theater'):
        raise AllocationError('分配模式必须为account或theater。')
    validate_theater(p.get('theater'),d)
    if not isinstance(p.get('saved_plans'),list) or len(p['saved_plans'])>50:
        raise AllocationError('最多保存50个剧诗方案。')
    for t in p['saved_plans']:validate_theater(t,d)


def prepare(d: dict[str,Any]) -> tuple[dict[str,Any],list[dict[str,Any]],dict[str,Any]]:
    validate(d)
    effective=copy.deepcopy(d)
    p=d['planning']; t=p['theater']; external=[]
    if p['mode']=='theater':
        own={r['character_id'] for r in t['roster'] if r['source']=='own'}
        cm={c['id']:c for c in d['characters']}
        for r in t['roster']:
            if r['source']=='own':continue
            c=cm[r['character_id']]
            external.append(dict(character_id=c['id'],character=c['name'],type=c['type'],source=r['source'],
                weapon_label=r.get('weapon_label') or ('试用自带装备' if r['source']=='trial' else '好友自带装备'),consumes_inventory=False))
        for c in effective['characters']:
            c['enabled']=c['id'] in own
            if c['id'] in t['priorities']:c['priority']=t['priorities'][c['id']]
            c['locked_weapon']=t['locks'].get(c['id'],c.get('locked_weapon') if t['use_account_locks'] else None)
        for w in effective['weapons']:
            reserved=t['reservations'].get(w['id'],0)
            if reserved>w['quantity']:
                raise AllocationError(f"{w['name']}预留{reserved}把，超过实际库存{w['quantity']}把。")
            w['quantity']-=reserved
    del effective['planning']
    own_count=sum(c.get('enabled',True) for c in effective['characters'])
    context=dict(mode=p['mode'],name=t['name'] if p['mode']=='theater' else '全角色方案',
        roster_count=own_count+len(external),own_count=own_count,external_count=len(external),
        use_account_locks=p['mode']=='account' or t['use_account_locks'],
        reservations=copy.deepcopy(t['reservations']) if p['mode']=='theater' else {},
        scope='开演前为整份参演名单一次性配装；未验证当期入场资格，未优化每幕配队、活力或祝福。')
    return effective,external,context


def plan(d: dict[str,Any]) -> dict[str,Any]:
    effective,external,context=prepare(d)
    r=solve(effective)
    total={w['id']:w for w in d['weapons']}
    for w in r['inventory']:
        q=total[w['id']]['quantity']; reserved=context['reservations'].get(w['id'],0)
        w.update(quantity=q,reserved=reserved,available=q-reserved,remaining=q-reserved-w['used'])
    r.update(planning=context,external_characters=external,schema_version=2,tool_version='2.0.0')
    r['summary'].update(roster_count=context['roster_count'],external_count=len(external),
        total_physical_copies=sum(w['quantity'] for w in d['weapons']),reserved_copies=sum(w['reserved'] for w in r['inventory']))
    return r


def export_results(r: dict[str,Any], out: Path) -> None:
    write_results(r,out)
    with (out/'inventory.csv').open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.writer(f);wr.writerow(['武器','类型','总库存','剧诗预留','可分配','本方案已用','可用剩余'])
        for w in r['inventory']:wr.writerow([csv_safe(w[k]) for k in ('name','type','quantity','reserved','available','used','remaining')])
    with (out/'external_characters.csv').open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.writer(f);wr.writerow(['角色','来源','自带装备备注','占用本人库存'])
        for e in r['external_characters']:wr.writerow([csv_safe(e['character']), '试用' if e['source']=='trial' else '好友助演',csv_safe(e['weapon_label']),'否'])


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path(__file__).with_name('data.json'))
    p.add_argument('--out',type=Path,default=Path(__file__).with_name('results'))
    p.add_argument('--mode',choices=('account','theater'),help='只覆盖本次计算模式')
    args=p.parse_args()
    try:
        d=normalize(json.loads(args.data.read_text(encoding='utf-8-sig')))
        if args.mode:d['planning']['mode']=args.mode
        r=plan(d);export_results(r,args.out)
        print(json.dumps(dict(planning=r['planning'],summary=r['summary']),ensure_ascii=False,indent=2))
        print(f'输出：{args.out.resolve()}')
    except (OSError,json.JSONDecodeError,AllocationError) as err:
        p.exit(2,f'分配失败：{err}\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
