"""Verify transforms in two already-running real Ghostrunner clients, using opt-in QA."""
import argparse
import copy
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def near(a, b, angles=False):
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != 3 or len(b) != 3:
        return False
    for x, y in zip(a, b):
        if not isinstance(x, (int, float)) or not math.isfinite(x):
            return False
        delta = (x-y+180) % 360-180 if angles else x-y
        if abs(delta) > 0.05:
            return False
    return True


def score(a, b, expected):
    errors = []
    for index, (own, peer) in enumerate(((a, b), (b, a))):
        label = 'AB'[index]
        if own.get('gameplay') is not True or own.get('local_players') != 1:
            errors.append(label + ': wrong gameplay/player-count precondition')
        if not str(own.get('pawn', '')).startswith('BP_PlayerCharacter_C '):
            errors.append(label + ': no real source player pawn')
        if not str(own.get('body', '')).startswith('Character '):
            errors.append(label + ': no non-player remote character')
        if own.get('peer_usable') is not True or own.get('body_hidden') is not False:
            errors.append(label + ': peer avatar unavailable/hidden')
        validation=own.get('qa_validation') or {}
        if validation.get('capsule_clear') is not True:
            errors.append(label + ': source standing position was not checked against world collision')
        if not str(own.get('mesh', '')).startswith('SkeletalMesh /Game/'):
            errors.append(label + ': no game skeletal mesh')
        if own.get('world') != peer.get('world') or not own.get('world'):
            errors.append(label + ': different worlds')
        if not near(own.get('local_position'), expected[index]['position']):
            errors.append(label + ': source did not reach requested position')
        if not near(own.get('local_rotation'), expected[index]['rotation'], True):
            errors.append(label + ': source did not reach requested rotation')
        if not near(own.get('body_position'), peer.get('local_position')):
            errors.append(label + ': actual body differs from the other real player')
        if not near(own.get('body_rotation'), peer.get('local_rotation'), True):
            errors.append(label + ': actual body rotation differs from the other player')
        if not near(own.get('peer_expected'), peer.get('local_position')):
            errors.append(label + ': received pose differs from the other real player')
        appearance=own.get('appearance') or {}
        if appearance.get('playing') is not True or appearance.get('group') not in ('idle','walk','run','air','attack'):
            errors.append(label + ': no active remote animation')
        bones=appearance.get('bones') or {}
        try:
            flat=all(abs(bones['hand_'+side][2]-bones['upperarm_'+side][2])<3 for side in ('l','r'))
            hand_span=math.dist(bones['hand_l'],bones['hand_r'])
            shoulder_span=math.dist(bones['upperarm_l'],bones['upperarm_r'])
            if flat and hand_span>2.3*shoulder_span:
                errors.append(label + ': both arms remain in horizontal bind pose')
        except (KeyError,TypeError,IndexError):
            errors.append(label + ': missing actual bone observations')
        weapons=appearance.get('weapons') or []
        if appearance.get('weapon_visible') is not True or len(weapons)!=2:
            errors.append(label + ': missing remote katana parts')
        for weapon in weapons:
            if weapon.get('hidden') is not False or weapon.get('socket')!='hand_r':
                errors.append(label + ': weapon is hidden or attached to the wrong socket')
            hand=appearance.get('hand')
            wp=weapon.get('position')
            if not hand or not wp or math.dist(hand,wp)>6:
                errors.append(label + ': weapon is not following the actual hand bone')
    if near(a.get('local_position'), b.get('local_position')):
        errors.append('source poses must be distinct')
    return errors


def read_json(path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def wait(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError('observation deadline exceeded')


def process_image(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise AssertionError('game process is missing: ' + str(pid))
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise AssertionError('cannot inspect game process')
        image = Path(buffer.value)
        if image.name != 'Ghostrunner-Win64-Shipping.exe':
            raise AssertionError('PID is not a Ghostrunner game client')
        return image
    finally:
        kernel.CloseHandle(handle)


def rpc(port, method, **params):
    with socket.create_connection(('127.0.0.1', port), timeout=3) as conn:
        conn.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                                 'params': params}).encode() + b'\n')
        with conn.makefile('rb') as stream:
            result = json.loads(stream.readline())
    if 'error' in result:
        raise AssertionError(str(result['error']))
    return result['result']


class Pair:
    def __init__(self, args):
        self.args, self.ids = args, [0, 0]
        self.dirs = [args.a_dir, args.b_dir]
        self.pids = [args.pid_a, args.pid_b]
        self.images = [process_image(pid) for pid in self.pids]
        if self.images[0] == self.images[1]:
            raise AssertionError('clients must use different test copies')
        if self.dirs[0].resolve() == self.dirs[1].resolve():
            raise AssertionError('clients must use different file directories')
        self.trace = (args.output / 'observations.jsonl').open('w')
        for i, directory in enumerate(self.dirs):
            current = read_json(directory / 'runtime.json') or {}
            self.ids[i] = int(current.get('qa_id') or 0)

    def observe(self):
        result = []
        for pid, directory in zip(self.pids, self.dirs):
            process_image(pid)
            path = directory / 'runtime.json'
            value = read_json(path)
            if not value or time.time() - path.stat().st_mtime > 1.5:
                return None
            result.append(value)
        self.trace.write(json.dumps({'at': time.time(), 'a': result[0], 'b': result[1]}) + '\n')
        self.trace.flush()
        return result

    def command(self, index, action, **params):
        self.ids[index] += 1
        value = dict(params, action=action, id=self.ids[index])
        directory = self.dirs[index]
        temporary = directory / 'qa.producer.tmp'
        def publish():
            try:
                temporary.write_text(json.dumps(value), encoding='utf-8')
                os.replace(str(temporary), str(directory / 'qa.json'))
                return True
            except OSError:
                return False
        wait(publish, 2)
        return value

    def converge(self, expected):
        def good():
            pair = self.observe()
            return pair if pair and not score(*pair, expected) else None
        pair = wait(good)
        ticks = [p['tick'] for p in pair]
        animation_times=[p.get('appearance',{}).get('position') for p in pair]
        for _ in range(5):
            time.sleep(0.15)
            pair = wait(good)
        if not all(p['tick'] > old for p, old in zip(pair, ticks)):
            raise AssertionError('game observation streams stopped advancing')
        if not all(abs(p['appearance']['position']-old)>0.001 for p,old in zip(pair,animation_times)):
            raise AssertionError('remote animation time is not advancing')
        return pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a-dir', required=True, type=Path)
    parser.add_argument('--b-dir', required=True, type=Path)
    parser.add_argument('--pid-a', required=True, type=int)
    parser.add_argument('--pid-b', required=True, type=int)
    parser.add_argument('--chaos-info', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'success': False, 'gates': [], 'game_clients': 2}
    pair = None
    try:
        pair = Pair(args)
        baseline = wait(pair.observe)
        assert all(p.get('world')=='/Game/Levels/Tutorial/L_Tutorial_Persistant' for p in baseline), 'wrong scenario world'
        # Native QA validates the floor and a standing capsule at every requested
        # pose. The fixture is on the open tutorial platform, before its metal gate.
        origin=[-20000,-67327,2100.75]
        expected = [{'position': list(origin), 'rotation': [0, 90, 0]},
                    {'position': [-20000,-67000,2100.75], 'rotation': [0, -90, 0]}]
        for i in range(2):
            pair.command(i, 'hold', **expected[i])
        snapshots = pair.converge(expected)
        result['gates'].append('distinct_sources_and_bidirectional_transforms')
        # Exercise the real scorer with bad observations rather than assuming a green oracle.
        broken = copy.deepcopy(snapshots)
        broken[0]['body_position'][0] += 100
        assert score(*broken, expected), 'scorer accepted a displaced avatar'
        broken = copy.deepcopy(snapshots)
        broken[1]['local_players'] = 2
        assert score(*broken, expected), 'scorer accepted the wrong game mode'
        result['gates'].append('scorer_negative_controls')
        broken=copy.deepcopy(snapshots)
        broken[0]['appearance']['playing']=False
        assert score(*broken,expected),'scorer accepted a non-animated avatar'
        broken=copy.deepcopy(snapshots)
        broken[1]['appearance']['weapons']=[]
        assert score(*broken,expected),'scorer accepted an avatar with no weapon'
        broken=copy.deepcopy(snapshots)
        bones=broken[0]['appearance']['bones']
        bones['upperarm_l']=[0,-20,100]; bones['upperarm_r']=[0,20,100]
        bones['hand_l']=[0,-100,100]; bones['hand_r']=[0,100,100]
        assert score(*broken,expected),'scorer accepted a horizontal bind pose'
        result['gates'].append('actual_animation_bones_and_attached_katana_on_both_clients')
        expected[0]['position'][1] += 100
        expected[0]['rotation'][1] = 25
        expected[1]['position'][1] -= 100
        expected[1]['rotation'][1] = -155
        for i in range(2):
            pair.command(i, 'hold', **expected[i])
        pair.converge(expected)
        result['gates'].append('both_sources_move_and_rotate_independently')
        pair.command(0, 'mutation', drop_receive=True)
        wait(lambda: (pair.observe() or [{}])[0].get('qa_id') == pair.ids[0])
        expected[1]['position'][1] += 75
        pair.command(1, 'hold', **expected[1])
        def mutant_observed():
            observations = pair.observe()
            if not observations or not near(observations[0].get('peer_expected'), expected[1]['position']):
                return None
            return observations if score(*observations, expected) else None
        wait(mutant_observed)
        result['gates'].append('disabled_receive_mutation_detected_in_real_game')
        pair.command(0, 'mutation', drop_receive=False)
        pair.converge(expected)
        result['gates'].append('receive_restored_and_converged')
        port = read_json(args.chaos_info)['rpc']
        rpc(port, 'set_params', params={'loss': 0.1, 'latency_ms': 80, 'jitter_ms': 40,
                                      'duplicate': 0.1, 'reorder': 0.2})
        rpc(port, 'reset_stats')
        expected[0]['position'][1] -= 75
        expected[1]['position'][1] += 75
        for i in range(2):
            pair.command(i, 'hold', **expected[i])
        pair.converge(expected)
        time.sleep(0.5)
        stats = rpc(port, 'stats')
        assert sum(s['dropped'] for s in stats.values()) > 0, 'loss profile dropped no packets'
        result['chaos'] = stats
        result['gates'].append('loss_delay_reorder_convergence')
        rpc(port, 'disconnect', duration_ms=5000)
        def disconnected():
            observations = pair.observe()
            return observations if observations and all(p.get('peer_usable') is False and
                p.get('body_hidden') is True and p.get('local_players') == 1 for p in observations) else None
        wait(disconnected, 4.8)
        result['gates'].append('blackout_hides_both_remote_avatars')
        pair.converge(expected)
        result['gates'].append('blackout_rejoin_converges_without_game_restart')
        result['final'] = pair.observe()
        result['success'] = True
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if pair:
            pair.trace.close()
        (args.output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'final'}, indent=2))
    print('RESULT: PASS' if result['success'] else 'RESULT: FAIL')
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
