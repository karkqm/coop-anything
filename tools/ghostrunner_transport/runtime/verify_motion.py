"""Check real source locomotion against remote animation, bones and attached weapons."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_pair import Pair, near, wait


def check_source(pair, index):
    initial=wait(pair.observe)
    start=initial[index]['local_position']
    pair.command(index,'walk',direction=[1,0,0])
    wait(lambda: (pair.observe() or [{},{}])[index].get('qa_id')==pair.ids[index])
    observations=[]
    until=time.monotonic()+1.8
    while time.monotonic()<until:
        current=pair.observe()
        if current: observations.append(current)
        time.sleep(.03)
    last=wait(pair.observe)
    pair.command(index,'hold',position=start,rotation=initial[index]['local_rotation'])
    wait(lambda: (pair.observe() or [{},{}])[index].get('qa_id')==pair.ids[index])
    # Drain the last moving snapshots as the two file seams/UDP deliver them.
    until=time.monotonic()+.4
    while time.monotonic()<until:
        current=pair.observe()
        if current: observations.append(current)
        time.sleep(.03)
    displacement=math.dist(start,last[index]['local_position'])
    assert displacement>30,'real source did not move'
    dynamic=[]
    seen=set()
    for observation in observations:
        observer=observation[1-index]
        # Compare against the real source sample that was received, rather than
        # the newer source sample at the observer's wall-clock time.
        source=next((p[index] for p in observations
                     if near(p[index].get('local_position'),observer.get('peer_expected'))
                     and near(p[index].get('local_velocity'),observer.get('peer_velocity'))),None)
        if not source or observer.get('peer_seq') in seen: continue
        velocity=source.get('local_velocity') or [0,0,0]
        speed=math.hypot(*velocity[:2])
        appearance=observer.get('appearance') or {}
        expected='run' if speed>550 else 'walk'
        if (source.get('local_motion',{}).get('mode')==1 and speed>30 and
            appearance.get('group')==expected and appearance.get('playing') is True):
            assert near(observer.get('body_position'),source['local_position']),'moving avatar differs from received real source'
            seen.add(observer['peer_seq'])
            dynamic.append((source,observer))
    assert len(dynamic)>=3,'no sustained real locomotion with matching remote walk/run animation'
    times=[p[1]['appearance']['position'] for p in dynamic]
    assert max(times)-min(times)>.02,'remote walk/run animation time is static'
    feet=[]
    for _,observer in dynamic:
        foot=observer['appearance']['bones']['foot_l']
        root=observer['body_position']
        feet.append([x-y for x,y in zip(foot,root)])
    assert max(math.dist(a,b) for a in feet for b in feet)>2,'feet slide without an evaluated locomotion pose'
    for _,observer in dynamic:
        appearance=observer['appearance']
        assert appearance['weapon_visible'] and len(appearance['weapons'])==2
        for weapon in appearance['weapons']:
            assert not weapon['hidden'] and weapon['socket']=='hand_r'
            assert math.dist(weapon['position'],appearance['sword']['expected_grip'])<1,'katana detached during locomotion'
    before=last[index].get('local_motion',{}).get('attack',0)
    pair.command(index,'attack')
    attack_samples=[]
    until=time.monotonic()+2
    while time.monotonic()<until:
        current=pair.observe()
        if current:
            motion=current[index].get('local_motion',{})
            if motion.get('attack',0)>before or motion.get('attacking'):
                attack_samples.append(current)
        time.sleep(.03)
    assert attack_samples,'the real melee action was not captured in the source state'
    assert any(p[1-index].get('appearance',{}).get('group')=='attack' for p in attack_samples), 'remote melee animation not observed'
    return {'source':'AB'[index], 'displacement_cm':displacement, 'dynamic_samples':len(dynamic)}


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a-dir',required=True,type=Path)
    parser.add_argument('--b-dir',required=True,type=Path)
    parser.add_argument('--pid-a',required=True,type=int)
    parser.add_argument('--pid-b',required=True,type=int)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    pair=Pair(args)
    result={'success':False,'gates':[]}
    # Use the same collision-checked tutorial platform as verify_pair, independent
    # of whichever pose a previous test or the player left behind.
    expected=[{'position':[-20000,-67327,2100.75],'rotation':[0,90,0]},
              {'position':[-20000,-67000,2100.75],'rotation':[0,-90,0]}]
    try:
        initial=wait(pair.observe)
        assert all(p.get('world')=='/Game/Levels/Tutorial/L_Tutorial_Persistant' for p in initial),'wrong scenario world'
        for i in range(2): pair.command(i,'hold',**expected[i])
        pair.converge(expected)
        result['sources']=[]
        for i in range(2):
            result['sources'].append(check_source(pair,i))
            pair.converge(expected)
        result['gates'].append('real_source_addmovementinput_moves_player')
        result['gates'].append('remote_walk_run_clock_and_evaluated_foot_pose_advance')
        result['gates'].append('katana_follows_animated_hand_during_movement')
        result['gates'].append('real_source_melee_action_reaches_remote_animation')
        result['success']=True
    except Exception as exc:
        result['error']=str(exc)
    finally:
        for i in range(2): pair.command(i,'hold',**expected[i])
        pair.trace.close()
        (args.output/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    print('RESULT: PASS' if result['success'] else 'RESULT: FAIL')
    return 0 if result['success'] else 1


if __name__=='__main__':
    sys.exit(run())
