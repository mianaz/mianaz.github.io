"""Optional independent checks: Python vs JavaScript; SciPy vs core matrices.
Requires Node.js and scipy. Run from this directory: python verify_planner.py.
"""
import copy
import json
from pathlib import Path
import random
import subprocess
from scipy.optimize import linear_sum_assignment
from allocator import AllocationError, TYPES, build_problem
from planner import normalize, plan, prepare

ROOT=Path(__file__).resolve().parent
D=normalize(json.loads((ROOT/'data.json').read_text()))
cases=[copy.deepcopy(D)]
for q in (3,5,20):
    d=copy.deepcopy(D)
    for w in d['weapons']:
        if w['name'].startswith('西风'):w['quantity']=q
    cases.append(d)
rng=random.Random(20260928)
for i in range(100):
    d=copy.deepcopy(D)
    d['planning']['mode']='theater'
    t=d['planning']['theater']
    selected=rng.sample(d['characters'],rng.randrange(0,35))
    t['roster']=[dict(character_id=c['id'],source=rng.choice(['own']*7+['trial','friend'])) for c in selected]
    for w in d['weapons']:
        w['quantity']=rng.randrange(0,7)
        if rng.random()<0.08:t['reservations'][w['id']]=rng.randrange(w['quantity']+1)
    for c in selected:
        if rng.random()<0.12:t['priorities'][c['id']]=rng.randrange(0,11)
        if rng.random()<0.07:t['locks'][c['id']]=rng.choice(list(c['scores']))
    cases.append(d)
code="""
const P=require('./planner.js');let text='';process.stdin.setEncoding('utf8');
process.stdin.on('data',s=>text+=s);process.stdin.on('end',()=>{
const out=JSON.parse(text).map(d=>{try{const r=P.plan(d);return {ok:true,summary:r.summary,
assignment:r.assignment.map(a=>[a.character_id,a.weapon_id,a.copy,a.score,a.priority]),external:r.external_characters};}
catch(e){return {ok:false};}});console.log(JSON.stringify(out));});
"""
proc=subprocess.run(['node','-e',code],input=json.dumps(cases,ensure_ascii=False),text=True,capture_output=True,cwd=ROOT,check=True)
js=json.loads(proc.stdout)
feasible=0;infeasible=0;matrices=0
for d,j in zip(cases,js):
    try:r=plan(d)
    except AllocationError:
        assert j['ok'] is False
        infeasible+=1;continue
    feasible+=1
    assert j['ok']
    assert r['summary']==j['summary']
    assert [[a[k] for k in ('character_id','weapon_id','copy','score','priority')] for a in r['assignment']]==j['assignment']
    assert r['external_characters']==j['external']
    effective,_,_=prepare(d)
    for typ in TYPES:
        p=build_problem(effective,typ)
        if not p['characters']:continue
        rows,cols=linear_sum_assignment(p['cost'])
        cost=sum(p['cost'][i][k] for i,k in zip(rows,cols))
        assert cost==r['certificates'][typ]['primal_cost']
        matrices+=1
report=dict(case_count=len(cases),feasible=feasible,infeasible_agreed=infeasible,scipy_matrices=matrices,python_javascript_exact_assignment_agreement=True,scipy_objective_agreement=True)
(ROOT/'crosscheck_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
