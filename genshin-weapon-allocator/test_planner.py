"""Regression tests for custom stocks, independent scenarios and external equipment."""
import copy
import json
from pathlib import Path
import unittest
from allocator import AllocationError, MAX_QUANTITY, build_problem, solve, validate as validate_data
from planner import normalize, blank_theater, plan, prepare, validate


def small(n=4,stock=2):
    chars=[dict(id=f'c{i}',name=f'角色{i}',type='单手剑',role='测试',scores={'fav':100,'alt':80},priority=1,enabled=True,locked_weapon=None) for i in range(n)]
    weapons=[dict(id='fav',name='西风剑',name_en='Favonius',type='单手剑',rarity=4,quantity=stock,refinement=5),
             dict(id='alt',name='测试五星',name_en='Alternative',type='单手剑',rarity=5,quantity=n,refinement=1)]
    return normalize(dict(characters=chars,weapons=weapons))


def theater(d,*ids,external=None):
    d['planning']['mode']='theater'
    d['planning']['theater']['roster']=[dict(character_id=cid,source='own') for cid in ids]
    if external:d['planning']['theater']['roster']+=external
    return d


class PlannerTests(unittest.TestCase):
    def test_four_star_three_five_copies(self):
        for count in (3,5):
            r=plan(small(5,count))
            self.assertEqual(sum(a['weapon_id']=='fav' for a in r['assignment']),count)
            self.assertEqual(len(set(a['physical_id'] for a in r['assignment'])),5)
    def test_multiple_five_star_copies_allowed(self):
        d=small();d['weapons'][0]['quantity']=0
        r=plan(d);self.assertEqual(r['summary']['five_star_count'],4)
    def test_inventory_increase_is_monotone(self):
        totals=[plan(small(5,q))['summary']['weighted_total'] for q in range(7)]
        self.assertEqual(totals,sorted(totals))
        self.assertEqual(totals[-1],500)
    def test_large_stock_is_compressed(self):
        d=small(4,MAX_QUANTITY)
        p=build_problem(d,'单手剑')
        self.assertEqual(len(p['copies']),8)
        self.assertEqual(plan(d)['summary']['weighted_total'],400)
        self.assertEqual(plan(d)['inventory'][0]['remaining'],MAX_QUANTITY-4)
    def test_bad_quantities(self):
        for value in (-1,1.3,True,'3',MAX_QUANTITY+1):
            d=small();d['weapons'][0]['quantity']=value
            with self.assertRaises(AllocationError):plan(d)
    def test_capacity_shortage(self):
        d=small(4,3);d['weapons'][1]['quantity']=0
        with self.assertRaises(AllocationError):plan(d)
    def test_theater_only_selected(self):
        d=theater(small(), 'c3')
        r=plan(d)
        self.assertEqual([a['character_id'] for a in r['assignment']],['c3'])
        self.assertEqual(r['assignment'][0]['weapon_id'],'fav')
    def test_selected_own_can_be_disabled_in_account(self):
        d=small();d['characters'][0]['enabled']=False
        theater(d,'c0')
        self.assertEqual(plan(d)['summary']['character_count'],1)
    def test_theater_reservation(self):
        d=theater(small(3,3),'c0','c1','c2');d['planning']['theater']['reservations']={'fav':2}
        r=plan(d);w=r['inventory'][0]
        self.assertEqual([w[k] for k in ('quantity','reserved','available','used','remaining')],[3,2,1,1,0])
    def test_reservation_exceeds_stock(self):
        d=theater(small(),'c0');d['planning']['theater']['reservations']={'fav':3}
        with self.assertRaises(AllocationError):plan(d)
    def test_reservation_never_affects_account(self):
        d=small();d['planning']['theater']['reservations']={'fav':MAX_QUANTITY}
        self.assertEqual(plan(d)['summary']['weighted_total'],360)
    def test_trial_and_friend_do_not_use_inventory(self):
        d=small(2,0);d['weapons'][1]['quantity']=0
        theater(d,external=[dict(character_id='c0',source='trial',weapon_label='测试五星 精1'),dict(character_id='c1',source='friend',weapon_label='测试五星 精5')])
        r=plan(d);self.assertEqual(r['summary']['roster_count'],2)
        self.assertEqual(r['summary']['character_count'],0)
        self.assertTrue(all(w['used']==0 for w in r['inventory']))
        self.assertEqual(len(r['external_characters']),2)
    def test_external_same_kind_as_own_is_independent(self):
        d=theater(small(2,1),'c0',external=[dict(character_id='c1',source='friend',weapon_label='西风剑 精5')])
        r=plan(d);self.assertEqual(r['inventory'][0]['used'],1)
        self.assertEqual(r['summary']['roster_count'],2)
    def test_independent_locks(self):
        d=small(2,2);d['characters'][0]['locked_weapon']='alt';theater(d,'c0')
        self.assertEqual(plan(d)['assignment'][0]['weapon_id'],'fav')
        d['planning']['theater']['use_account_locks']=True
        self.assertEqual(plan(d)['assignment'][0]['weapon_id'],'alt')
        d['planning']['theater']['locks']={'c0':None}
        self.assertEqual(plan(d)['assignment'][0]['weapon_id'],'fav')
    def test_theater_explicit_lock(self):
        d=theater(small(),'c0');d['planning']['theater']['locks']={'c0':'alt'}
        self.assertEqual(plan(d)['assignment'][0]['weapon_id'],'alt')
    def test_lock_over_capacity_errors(self):
        d=theater(small(2,1),'c0','c1');d['planning']['theater']['locks']={'c0':'fav','c1':'fav'}
        with self.assertRaises(AllocationError):plan(d)
    def test_scenario_priority_applies_and_keeps_account(self):
        d=theater(small(2,1),'c0','c1');d['planning']['theater']['priorities']={'c1':5}
        r=plan(d);self.assertEqual(next(a['weapon_id'] for a in r['assignment'] if a['character_id']=='c1'),'fav')
        self.assertEqual(d['characters'][1]['priority'],1)
    def test_no_mutation(self):
        d=theater(small(),'c0','c1');saved=copy.deepcopy(d);plan(d);self.assertEqual(d,saved)
    def test_empty_roster(self):
        d=theater(small());r=plan(d)
        self.assertEqual(r['summary']['roster_count'],0)
        self.assertEqual(r['summary']['weighted_total'],0)
    def test_unknown_duplicate_and_source(self):
        for entries in [[dict(character_id='unknown',source='own')],
                        [dict(character_id='c0',source='own'),dict(character_id='c0',source='friend')],
                        [dict(character_id='c0',source='other')]]:
            d=small();d['planning']['theater']['roster']=entries
            with self.assertRaises(AllocationError):validate(d)
    def test_unknown_reserve_or_lock_or_priority(self):
        for key,val in [('reservations',{'missing':1}),('locks',{'c0':'missing'}),('priorities',{'missing':1})]:
            d=small();d['planning']['theater'][key]=val
            with self.assertRaises(AllocationError):validate(d)
    def test_bad_saved_plan_is_rejected(self):
        d=small();t=blank_theater();t['roster']=[dict(character_id='missing',source='own')]
        d['planning']['saved_plans']=[t]
        with self.assertRaises(AllocationError):validate(d)
    def test_migration_old_config(self):
        d=small();del d['planning'];d['schema_version']=1
        d['assumptions']=['可在库存中改为0/1/2。'];new=normalize(d)
        self.assertEqual(new['planning']['mode'],'account')
        self.assertEqual(new['assumptions'],['库存现可自定义为0或正整数。'])
    def test_stock_does_not_change_refinement(self):
        d=small(4,5);self.assertTrue(all(a['refinement']==5 for a in plan(d)['assignment']))
    def test_full_data_and_favonius_example(self):
        d=normalize(json.loads(Path(__file__).with_name('data.json').read_text()))
        self.assertEqual(plan(d)['summary']['weighted_total'],11908)
        for w in d['weapons']:
            if w['name'].startswith('西风'):w['quantity']=5
        r=plan(d)
        self.assertEqual(r['summary']['weighted_total'],11937)
        self.assertEqual(r['summary']['character_count'],121)
        self.assertTrue(r['summary']['certificate_verified'])

if __name__=='__main__':unittest.main()
