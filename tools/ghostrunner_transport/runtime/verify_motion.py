"""Check real source locomotion against remote animation, bones and attached weapons."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_pair import Pair, wait


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
    observations=[]
    try:
        initial=wait(pair.observe)
        start=initial[0]['local_position']
        pair.command(0,'walk',direction=[1,0,0])
        until=time.monotonic()+1.8
        while time.monotonic()<until:
            current=pair.observe()
            if current: observations.append(current)
            time.sleep(.05)
        last=wait(pair.observe)
        pair.command(0,'hold',position=last[0]['local_position'],rotation=last[0]['local_rotation'])
        displacement=math.dist(start,last[0]['local_position'])
        assert displacement>30,'real source did not move'
        result['displacement_cm']=displacement
        dynamic=[]
        for source,observer in observations:
            velocity=source.get('local_velocity') or [0,0,0]
            speed=math.hypot(*velocity[:2])
            appearance=observer.get('appearance') or {}
            expected='run' if speed>550 else 'walk'
            if (source.get('local_motion',{}).get('mode')==1 and speed>30 and
                appearance.get('group')==expected and appearance.get('playing') is True):
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
                assert math.dist(weapon['position'],appearance['hand'])<6,'katana detached during locomotion'
        result['gates'].append('real_source_addmovementinput_moves_player')
        result['gates'].append('remote_walk_run_clock_and_evaluated_foot_pose_advance')
        result['gates'].append('katana_follows_animated_hand_during_movement')
        result['dynamic_samples']=len(dynamic)
        # Try the game's actual melee callback; observe source and receiver rather than
        # substituting a fabricated attack packet.
        before=last[0].get('local_motion',{}).get('attack',0)
        pair.command(0,'attack')
        attack_samples=[]
        until=time.monotonic()+2
        while time.monotonic()<until:
            current=pair.observe()
            if current:
                motion=current[0].get('local_motion',{})
                if motion.get('attack',0)>before or motion.get('attacking'):
                    attack_samples.append(current)
            time.sleep(.03)
        assert attack_samples,'the real melee action was not captured in the source state'
        assert any(p[1].get('appearance',{}).get('group')=='attack' for p in attack_samples), 'remote melee animation not observed'
        result['gates'].append('real_source_melee_action_reaches_remote_animation')
        result['success']=True
    except Exception as exc:
        result['error']=str(exc)
    finally:
        latest=pair.observe()
        if latest:
            pair.command(0,'hold',position=latest[0]['local_position'],rotation=latest[0]['local_rotation'])
        pair.trace.close()
        (args.output/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    print('RESULT: PASS' if result['success'] else 'RESULT: FAIL')
    return 0 if result['success'] else 1


if __name__=='__main__':
    sys.exit(run())
