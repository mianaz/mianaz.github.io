"""Optional Playwright UI checks. Uses an offline document and a localStorage mock.
The mock tests state serialization; actual file:// persistence is browser specific.
"""
from pathlib import Path
import json, shutil, tempfile
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
HTML=(ROOT/'index.html').read_text()
checks=[]; errors=[]; requests=[]
def check(ok,label):
    assert ok,label
    checks.append(label)
def state(page):return page.evaluate('appState()')
def setup(page,seed=None,storage=True):
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r.url))
    if storage:
        page.evaluate('''seed=>{const values={...seed};window.__savedValues=values;
        Object.defineProperty(window,'localStorage',{configurable:true,value:{
        getItem:k=>Object.hasOwn(values,k)?values[k]:null,
        setItem:(k,v)=>{values[k]=String(v);},removeItem:k=>delete values[k]}});}''',seed or {})
    page.set_content(HTML,wait_until='load')
    page.wait_for_function('typeof appState==="function"')

with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    options=dict(headless=True,args=['--no-sandbox'])
    exe=shutil.which('chromium') or shutil.which('google-chrome')
    if exe:options['executable_path']=exe
    browser=p.chromium.launch(**options)
    page=browser.new_page(viewport={'width':1440,'height':1050})
    page.on('dialog',lambda d:d.accept());setup(page)
    check(state(page)['result']['summary']['weighted_total']==11908,'Baseline full allocation')
    page.locator('[data-tab="inventory"]').click()
    page.locator('#bulkQuantity').fill('5');page.locator('#applyBulk').click()
    check(state(page)['dirty'] and page.locator('#csvBtn').is_disabled(),'Changes invalidate exports')
    check(all(w['quantity']==5 for w in state(page)['data']['weapons'] if w['name'].startswith('西风')),'Favonius batch quantity 5')
    page.locator('#undoBulk').click()
    check(all(w['quantity']==2 for w in state(page)['data']['weapons'] if w['name'].startswith('西风')),'Batch undo')
    page.locator('#applyBulk').click();page.locator('#solveBtn').click()
    check(state(page)['result']['summary']['weighted_total']==11937,'Reoptimization with larger inventory')
    page.locator('[data-tab="inventory"]').click();page.locator('#search').fill('西风剑')
    page.locator('[data-stock="fav_sword"]').fill('3');page.locator('[data-stock="fav_sword"]').press('Tab')
    check(next(w for w in state(page)['data']['weapons'] if w['id']=='fav_sword')['quantity']==3,'Individual stock accepts 3')
    page.locator('[data-stock="fav_sword"]').fill('-1');page.locator('[data-stock="fav_sword"]').press('Tab')
    check(next(w for w in state(page)['data']['weapons'] if w['id']=='fav_sword')['quantity']==3,'Invalid stock rejected')
    page.locator('#theaterMode').click()
    check(state(page)['result']['summary']['roster_count']==0,'Independent empty theater roster')
    page.locator('#rosterPaste').fill('枫原万叶、琴、行秋、夜兰、雷电将军、五郎、珐露珊、迪奥娜');page.locator('#rosterReplace').click()
    check(len(state(page)['data']['planning']['theater']['roster'])==8,'Paste eight names')
    page.locator('#rosterPaste').fill('琴、未知角色ABC');page.locator('#rosterReplace').click()
    check(len(state(page)['data']['planning']['theater']['roster'])==8,'Unknown name rejects entire batch')
    page.locator('[data-source="yelan"]').select_option('friend')
    page.locator('[data-external="yelan"]').fill('若水 精5');page.locator('[data-external="yelan"]').press('Tab')
    page.locator('[data-source="raiden"]').select_option('trial');page.locator('#solveBtn').click()
    r=state(page)['result']
    check(r['summary']['character_count']==6 and r['summary']['external_count']==2,'Trial and friend excluded from own allocation')
    check(len(r['assignment'])==len({a['physical_id'] for a in r['assignment']}),'No duplicate physical copies')
    page.locator('[data-tab="inventory"]').click();page.locator('#search').fill('西风剑')
    page.locator('[data-reserve="fav_sword"]').fill('1');page.locator('[data-reserve="fav_sword"]').press('Tab');page.locator('#solveBtn').click()
    w=next(w for w in state(page)['result']['inventory'] if w['id']=='fav_sword')
    check((w['quantity'],w['reserved'],w['available'])==(3,1,2),'Reservation arithmetic')
    page.locator('#search').fill('');page.locator('#rows [data-edit="kazuha"]').click()
    page.locator('#editLock').select_option('freedom');page.locator('#saveEdit').click()
    st=state(page)
    check(next(a for a in st['result']['assignment'] if a['character_id']=='kazuha')['weapon_id']=='freedom','Theater lock respected')
    check(next(c for c in st['data']['characters'] if c['id']=='kazuha')['locked_weapon'] is None,'Account lock remains independent')
    page.locator('#planName').fill('测试剧诗 A');page.locator('#planName').press('Tab');page.locator('#savePlan').click()
    page.locator('#newPlan').click();page.locator('#savedPlans').select_option('0');page.locator('#loadPlan').click()
    check(state(page)['result']['summary']['roster_count']==8,'Save and load named theater plan')
    page.locator('#accountMode').click()
    check(state(page)['result']['summary']['character_count']==121,'Switch back restores account roster')
    check(all(w['reserved']==0 for w in state(page)['result']['inventory']),'Reservations isolated to theater')
    page.locator('#theaterMode').click();page.locator('#solveBtn').click()
    with page.expect_download() as info:page.locator('#configBtn').click()
    config=Path(tmp)/'config.json';info.value.save_as(config)
    check(json.loads(config.read_text())==state(page)['data'],'Complete JSON export')
    with page.expect_download() as info:page.locator('#csvBtn').click()
    csvfile=Path(tmp)/'output.csv';info.value.save_as(csvfile)
    check('好友助演' in csvfile.read_text(encoding='utf-8-sig') and '若水 精5' in csvfile.read_text(encoding='utf-8-sig'),'CSV external equipment')
    before=state(page)['data'];bad=Path(tmp)/'bad.json';bad.write_text('{"characters":[],"weapons":"bad"}')
    page.locator('#fileInput').set_input_files(str(bad))
    check(state(page)['data']==before,'Invalid import is atomic')
    seed=page.evaluate('window.__savedValues')
    second=browser.new_page();setup(second,seed)
    check(state(second)['data']==before,'Mock localStorage serialization and restore')
    old=json.loads((ROOT/'data.json').read_text());del old['planning'];old['schema_version']=1
    legacy=Path(tmp)/'legacy.json';legacy.write_text(json.dumps(old,ensure_ascii=False))
    second.locator('#fileInput').set_input_files(str(legacy))
    check(state(second)['result']['summary']['weighted_total']==11908,'Legacy configuration migration')
    impossible=json.loads(config.read_text());impossible['planning']['theater']['reservations']['fav_sword']=4
    shortage=Path(tmp)/'shortage.json';shortage.write_text(json.dumps(impossible,ensure_ascii=False))
    second.locator('#fileInput').set_input_files(str(shortage))
    check(state(second)['result'] is None and second.locator('#csvBtn').is_disabled(),'Infeasible stock clears results and blocks export')
    (ROOT/'qa').mkdir(exist_ok=True)
    page.locator('#solveBtn').click();page.screenshot(path=str(ROOT/'qa'/'desktop.png'),full_page=True)
    page.locator('[data-tab="inventory"]').click();page.locator('#search').fill('西风');page.screenshot(path=str(ROOT/'qa'/'inventory.png'),full_page=True)
    mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True);setup(mobile,seed)
    mobile.locator('#theaterMode').click();mobile.locator('#selectedOnly').check()
    check(mobile.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Mobile 390px without page overflow')
    mobile.screenshot(path=str(ROOT/'qa'/'mobile.png'),full_page=True)
    ns=browser.new_page();setup(ns,storage=False)
    check(state(ns)['result']['summary']['weighted_total']==11908,'Blocked storage still allows calculation')
    check(not errors,'No script errors');check(not requests,'No network requests')
    browser.close()
report=dict(check_count=len(checks),checks=checks,script_errors=errors,network_requests=requests,
    browser='Chromium',loading='offline set_content; URL navigation blocked by runner',
    persistence='in-memory localStorage mock; native file URL storage not verified')
(ROOT/'browser_qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
