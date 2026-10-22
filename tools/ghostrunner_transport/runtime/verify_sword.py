"""Verify real remote sword slashes, including a frozen-pose mutation, in two clients."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_pair import Pair,wait

PREFIX='/Game/Visual/Characters/FFP_View_Models/GhostRunner_VM_Hands/Animations/'


def assess(samples):
    errors=[]
    if len(samples)<3: return ['fewer than three distinct evaluated attack poses']
    phases=[];tips=[];hands=[]
    for sample in samples:
        a=sample.get('appearance') or {};s=a.get('sword') or {};motion=sample.get('peer_motion') or {}
        if not sample.get('peer_usable') or sample.get('body_hidden') is not False:
            errors.append('remote body unavailable')
        clip=s.get('clip','')
        if not (s.get('ready') and s.get('active') and clip.startswith(PREFIX) and '_att_sword_' in clip):
            errors.append('not a real player sword sequence')
        if clip!=motion.get('clip'): errors.append('receiver selected a different source clip')
        phase=s.get('phase')
        if not isinstance(phase,(int,float)): errors.append('missing actual sequence clock')
        else: phases.append(phase)
        expected=s.get('expected_grip');weapons=a.get('weapons') or []
        if len(weapons)!=2: errors.append('katana parts missing');continue
        for w in weapons:
            if w.get('hidden') is not False or w.get('visible') is not True or w.get('scale')!=[1,1,1]:
                errors.append('hidden or collapsed weapon')
            if not str(w.get('parent','')).startswith('PoseableMeshComponent ') or w.get('socket')!='hand_r':
                errors.append('weapon not attached to evaluated retargeted hand')
            if not expected or math.dist(w['position'],expected)>1:
                errors.append('weapon grip differs from evaluated socket transform')
        blade=weapons[1];tip=blade['tip'];handle=blade['handle']
        length=math.dist(tip,handle)
        if not 80<length<100: errors.append('blade geometry collapsed or wrong tip bone')
        else: tips.append([(t-h)/length for t,h in zip(tip,handle)])
        if a.get('hand') and sample.get('body_position'):
            hands.append([h-p for h,p in zip(a['hand'],sample['body_position'])])
    if not phases or max(phases)-min(phases)<.15: errors.append('sword animation clock did not advance')
    arc=max((math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))))))
             for a in tips for b in tips),default=0)
    travel=max((math.dist(a,b) for a in hands for b in hands),default=0)
    if arc<45: errors.append('blade did not sweep through a slash arc')
    if travel<20: errors.append('evaluated hand did not execute the swing')
    return sorted(set(errors))


def attack(pair,index):
    baseline=wait(pair.observe)
    before=baseline[index].get('local_motion',{}).get('attack',0)
    pair.command(index,'attack')
    samples=[];source_seen=False;seen=set()
    until=time.monotonic()+2
    while time.monotonic()<until:
        pair_now=pair.observe()
        if pair_now:
            source,observer=pair_now[index],pair_now[1-index]
            motion=source.get('local_motion') or {}
            if motion.get('attacking') and motion.get('attack',0)>before and motion.get('clip'):
                source_seen=True
            peer=observer.get('peer_motion') or {};sword=observer.get('appearance',{}).get('sword') or {}
            key=observer.get('tick')
            if (peer.get('attack',0)>before and peer.get('attacking') and sword.get('active') and key not in seen):
                seen.add(key);samples.append(observer)
        time.sleep(.02)
    assert source_seen,'actual source melee action/sequence not observed'
    return samples


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a-dir',required=True,type=Path);p.add_argument('--b-dir',required=True,type=Path)
    p.add_argument('--pid-a',required=True,type=int);p.add_argument('--pid-b',required=True,type=int)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    pair=Pair(args);result={'success':False,'attacks':[],'gates':[]}
    expected=[{'position':[-20000,-67327,2100.75],'rotation':[0,90,0]},
              {'position':[-20000,-67000,2100.75],'rotation':[0,-90,0]}]
    try:
        initial=wait(pair.observe)
        assert all(p.get('world')=='/Game/Levels/Tutorial/L_Tutorial_Persistant' for p in initial),'wrong scenario world'
        for i in range(2): pair.command(i,'hold',**expected[i])
        pair.converge(expected)
        for i in range(2):
            for repeat in range(2):
                samples=attack(pair,i);errors=assess(samples)
                assert not errors, 'source '+str(i)+': '+', '.join(errors)
                result['attacks'].append({'source':'AB'[i],'repeat':repeat,'poses':len(samples)})
        result['gates'].append('both_real_sources_repeat_actual_sword_slashes')
        bad=copy.deepcopy(samples)
        for s in bad: s['appearance']['sword']['clip']='ESP_12_pst_Attack1'
        assert assess(bad),'oracle accepted old pistol clip'
        bad=copy.deepcopy(samples)
        for s in bad: s['appearance']['weapons'][1]['tip']=bad[0]['appearance']['weapons'][1]['tip']
        assert assess(bad),'oracle accepted detached/static blade geometry'
        result['gates'].append('pistol_and_static_blade_negative_controls')
        pair.command(1,'mutation',freeze_sword=True)
        wait(lambda: (pair.observe() or [{},{}])[1].get('qa_id')==pair.ids[1])
        frozen=attack(pair,0)
        errors=assess(frozen)
        assert frozen and any('clock' in e or 'slash arc' in e or 'swing' in e for e in errors), 'real frozen-pose mutation escaped oracle'
        result['mutation_errors']=errors
        result['gates'].append('frozen_sword_mutation_detected_in_actual_game')
        pair.command(1,'mutation',freeze_sword=False)
        wait(lambda: (pair.observe() or [{},{}])[1].get('qa_id')==pair.ids[1])
        restored=attack(pair,0)
        assert not assess(restored),'sword did not recover after mutation'
        result['gates'].append('restored_slash_passes')
        pair.converge(expected)
        result['gates'].append('both_return_to_idle_and_keep_bidirectional_pose_sync')
        result['success']=True
    except Exception as exc: result['error']=str(exc)
    finally:
        pair.command(1,'mutation',freeze_sword=False)
        pair.trace.close()
        (args.output/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));print('RESULT: PASS' if result['success'] else 'RESULT: FAIL')
    return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
