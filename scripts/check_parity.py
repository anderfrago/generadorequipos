"""Compare the Python team metrics to the original Apps Script on synthetic data."""
import json
import random
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.grouping_engine import prepare_model,evaluate,PROFILES
from app.scoring import FUNCTION_CODES
rng=random.Random(72)
fixtures=[]
for n in range(25):
    students=[dict(id=str(i),profiles={k:rng.randrange(13)/12 for k in PROFILES},functional={k:rng.randrange(7)/6 for k in FUNCTION_CODES},conditions=['CALM'] if i%2 else ['STEPS']) for i in range(12)]
    model=prepare_model(students,[dict(a='0',b='1',type='MEJOR_SEPARADOS'),dict(a='2',b='4',type='CONVIENE_JUNTOS')],FUNCTION_CODES)
    fixtures.append(dict(model=model,teams=[[str(i) for i in range(j,j+4)] for j in (0,4,8)]))
(ROOT/'tmp').mkdir(exist_ok=True)
(ROOT/'tmp/grouping-fixtures.json').write_text(json.dumps(fixtures),encoding='utf-8')
subprocess.run(['node',str(ROOT/'scripts/check_grouping_parity.cjs')],check=True)
original=json.loads((ROOT/'tmp/grouping-original.json').read_text())
for fixture,expected in zip(fixtures,original):
    actual=evaluate(fixture['model'],fixture['teams'])
    for key in ('weakestTeamIndex','bestTeamIndex','meanIndex','spread'):
        assert abs(actual[key]-expected[key])<=.1,(key,actual[key],expected[key])
    for a,e in zip(actual['teamMetrics'],expected['teamMetrics']):
        assert abs(a['balanceIndex']-e['balanceIndex'])<=.1,(a,e)
        for key in a['components']:
            assert abs(a['components'][key]-e['components'][key])<=.1,(key,a,e)
print('Parity verified: 25 proposals, 75 team scores and all five components (tolerance 0.1).')
