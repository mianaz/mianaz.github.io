"""Run: python -m unittest -v test_allocator.py (no third-party dependencies)."""
import copy
import itertools
import json
from pathlib import Path
import random
import unittest
from allocator import AllocationError, hungarian, verify_certificate, solve, validate, build_problem

class HungarianTests(unittest.TestCase):
    def test_bruteforce_random(self):
        rng=random.Random(71)
        checked=0
        for n in range(1,6):
            for m in range(n,7):
                for _ in range(12):
                    c=[[rng.randint(-20,30) for _ in range(m)] for _ in range(n)]
                    a,u,v=hungarian(c)
                    actual=sum(c[i][j] for i,j in enumerate(a))
                    expected=min(sum(c[i][j] for i,j in enumerate(p)) for p in itertools.permutations(range(m),n))
                    self.assertEqual(actual,expected)
                    self.assertTrue(verify_certificate(c,a,u,v)['verified'])
                    checked+=1
        self.assertEqual(checked,240)
    def test_greedy_counterexample(self):
        cost=[[0,1],[2,50]]
        a,u,v=hungarian(cost)
        self.assertEqual(a,[1,0])
        self.assertEqual(verify_certificate(cost,a,u,v)['primal_cost'],3)
    def test_all_zero_rectangular(self):
        c=[[0]*7 for _ in range(4)]
        a,u,v=hungarian(c)
        self.assertEqual(verify_certificate(c,a,u,v)['gap'],0)
    def test_bad_certificate(self):
        c=[[3,1],[1,2]]
        a,u,v=hungarian(c)
        u[0]+=1
        with self.assertRaises(AllocationError): verify_certificate(c,a,u,v)
    def test_empty_and_shortage(self):
        self.assertEqual(hungarian([]),([],[],[]))
        with self.assertRaises(AllocationError): hungarian([[1],[2]])

class AllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(Path(__file__).with_name('data.json').read_text())
    def test_full_inventory_and_roster(self):
        r=solve(self.data)
        self.assertEqual(r['summary']['character_count'],121)
        self.assertEqual(r['summary']['weighted_total'],11908)
        self.assertEqual(len({x['physical_id'] for x in r['assignment']}),121)
        self.assertTrue(r['summary']['certificate_verified'])
        for w in r['inventory']:
            self.assertLessEqual(w['used'],w['quantity'])
            self.assertLessEqual(w['quantity'],1 if w['rarity']==5 else 2)
        self.assertEqual([c['id'] for c in self.data['characters']].count('traveler'),1)
    def test_deterministic(self):
        self.assertEqual(solve(self.data)['assignment'],solve(self.data)['assignment'])
    def test_inventory_shortage(self):
        d=copy.deepcopy(self.data)
        for w in d['weapons']: w['quantity']=0
        with self.assertRaises(AllocationError): solve(d)
    def test_hall_conflict_without_total_shortage(self):
        d=copy.deepcopy(self.data)
        d['characters']=d['characters'][:2]
        for c in d['characters']: c['scores']={'mist':100}
        with self.assertRaises(AllocationError): solve(d)
    def test_conflicting_locks(self):
        d=copy.deepcopy(self.data)
        d['characters']=d['characters'][:2]
        for c in d['characters']:
            c['scores']['mist']=100; c['locked_weapon']='mist'
        with self.assertRaises(AllocationError): solve(d)
    def test_feasible_lock(self):
        d=copy.deepcopy(self.data)
        c=next(c for c in d['characters'] if c['id']=='kazuha')
        c['locked_weapon']='freedom'
        r=solve(d)
        self.assertEqual(next(a for a in r['assignment'] if a['character_id']=='kazuha')['weapon_id'],'freedom')
    def test_bad_type_and_unknown_id(self):
        for wid in ['skyharp','NONEXISTENT']:
            d=copy.deepcopy(self.data); d['characters'][0]['scores'][wid]=99
            with self.assertRaises(AllocationError): validate(d)
    def test_bad_quantities_and_scores(self):
        for bad in [True,1.2,-1,1000001]:
            d=copy.deepcopy(self.data); d['weapons'][0]['quantity']=bad
            with self.assertRaises(AllocationError): validate(d)
        for bad in [False,-1,101,99.5]:
            d=copy.deepcopy(self.data); d['characters'][0]['scores']['chrysalis']=bad
            with self.assertRaises(AllocationError): validate(d)
    def test_zero_priority(self):
        d=copy.deepcopy(self.data)
        for c in d['characters']: c['priority']=0
        r=solve(d)
        self.assertEqual(r['summary']['character_count'],121)
        self.assertEqual(r['summary']['weighted_total'],0)
        self.assertTrue(r['summary']['certificate_verified'])
    def test_disable_all(self):
        d=copy.deepcopy(self.data)
        for c in d['characters']: c['enabled']=False
        r=solve(d)
        self.assertEqual(r['summary']['character_count'],0)
        self.assertEqual(r['summary']['weighted_total'],0)
    def test_removed_inventory_reoptimization(self):
        d=copy.deepcopy(self.data)
        next(w for w in d['weapons'] if w['id']=='freedom')['quantity']=0
        r=solve(d)
        self.assertEqual(r['summary']['character_count'],121)
        self.assertNotIn('freedom',{a['weapon_id'] for a in r['assignment']})

if __name__=='__main__': unittest.main()
