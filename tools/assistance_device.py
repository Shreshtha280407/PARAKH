#!/usr/bin/env python3
"""Non-destructive USB runner for the isolated assistance package; never operates on PARAKH.

Requires an explicit serial and expected model for every device action. No uninstall,
pm clear, production package installation, account/database or Keystore operations.
All private media/gray files remain in harness-private storage or --output outside Git.
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path
from assistance_source import source_version

REPO = Path(__file__).resolve().parents[1]
PACKAGE = 'in.kaushalpramaan.assist.benchmark'
ACTIVITY = PACKAGE + '/.BenchmarkActivity'


class Device:
    def __init__(self, serial, expected_model):
        self.prefix = ['adb', '-s', serial]
        self.call(['get-state'])
        model = self.call(['shell', 'getprop', 'ro.product.model']).decode().strip()
        if model != expected_model:
            raise ValueError(f'Expected model {expected_model!r}; connected device reports {model!r}')
        if self.call(['shell', 'getprop', 'ro.kernel.qemu']).decode().strip() == '1':
            raise ValueError('Physical-device protocol refuses an emulator')

    def call(self, args, **kwargs):
        return subprocess.check_output(self.prefix + args, timeout=kwargs.pop('timeout', 120), **kwargs)

    def private(self, args, **kwargs):
        return self.call(['shell', '-T', 'run-as', PACKAGE] + args, **kwargs)

    def put_file(self, source, destination):
        # Shell-v2 (-T, no PTY) waits for stdin to drain and preserves binary bytes.
        # adb exec-in can return after a truncated write on some host/device versions.
        # Every transfer is independently hash checked before analysis.
        with source.open('rb') as f:
            subprocess.run(self.prefix + ['shell', '-T', 'run-as', PACKAGE, 'tee', destination], stdin=f,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=180)


def stage(device, args):
    if args.output.resolve().is_relative_to(REPO):
        raise ValueError('--output must be outside Git')
    args.output.mkdir(parents=True, exist_ok=True)
    raw = [json.loads(line) for line in (REPO / 'ml/quality/data/manifest.jsonl').read_text().splitlines()]
    unique = {}
    for row in raw:
        old = unique.get(row['sha256'])
        if old is None or (old['folder_hand_label'] == 'not_labelled' and row['folder_hand_label'] != 'not_labelled'):
            unique[row['sha256']] = row
    selected = list(unique.values())
    if args.representative:
        selected = []
        for kind in ('photo', 'video'):
            for condition in ('good', 'dark', 'blurry', 'motion_blurry', 'out_of_frame'):
                selected += [r for r in unique.values() if r['kind'] == kind and r['folder_quality_label'] == condition][:2]
        # Include a known visually reviewed absent clip, a mixed clip and both real video rotations.
        selected += [r for r in unique.values() if r['id'] in ('m-3e019e88238b', 'm-f0d3e8f0f933') or
                     (r['kind'] == 'video' and str(r.get('rotation')) == '90')]
        selected = list({r['id']: r for r in selected}.values())
    plan = {'source_version': source_version(), 'repeats': args.repeats, 'export_photo_gray': True, 'items': []}
    device.private(['mkdir', '-p', 'files/dataset', 'files/reports'])
    for i, row in enumerate(selected):
        source = args.dataset_root / 'originals' / row['relative_path']
        digest = hashlib.sha256()
        with source.open('rb') as f:
            for b in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(b)
        if digest.hexdigest() != row['sha256']:
            raise ValueError('Local source media hash differs from manifest')
        name = row['id'] + ('.mp4' if row['kind'] == 'video' else '.jpg')
        destination = 'files/dataset/' + name
        existing = subprocess.run(device.prefix + ['shell', '-T', 'run-as', PACKAGE, 'sha256sum', destination],
                                  capture_output=True, timeout=20)
        existing_hash = existing.stdout.decode().split()
        if existing.returncode != 0 or not existing_hash or existing_hash[0] != row['sha256']:
            device.put_file(source, destination)
        if device.private(['sha256sum', destination]).decode().split()[0] != row['sha256']:
            raise ValueError('USB transfer hash mismatch')
        plan['items'].append({'id': row['id'], 'filename': name, 'sha256': row['sha256'], 'kind': row['kind'],
                              'hands': True, 'dataset_role': 'development_only_pending_new_independent_sets'})
        print(f"Staged {i + 1}/{len(selected)} {row['id']} {row['kind']}", flush=True)
    local = args.output / 'plan.json'
    local.write_text(json.dumps(plan, indent=2) + '\n')
    device.put_file(local, 'files/plan.json')
    print('Private test plan staged; no analysis has run')


def run(device, args):
    if not args.run_id or not all(c.isalnum() or c in '_-' for c in args.run_id) or len(args.run_id) > 64:
        raise ValueError('Provide a new alphanumeric --run-id')
    for suffix in ('jsonl', 'done.json'):
        exists = subprocess.run(device.prefix + ['shell', '-T', 'run-as', PACKAGE, 'test', '-e', f'files/reports/{args.run_id}.{suffix}'],
                                capture_output=True, timeout=15)
        if exists.returncode == 0:
            raise ValueError('Run identifier already exists; refusing to report an old run as a new completion')
    previous_airplane = device.call(['shell', 'settings', 'get', 'global', 'airplane_mode_on']).decode().strip()
    try:
        if args.airplane:
            device.call(['shell', 'cmd', 'connectivity', 'airplane-mode', 'enable'])
            if device.call(['shell', 'settings', 'get', 'global', 'airplane_mode_on']).decode().strip() != '1':
                raise RuntimeError('Airplane-mode physical confirmation is required; command did not enable it')
        print(device.call(['shell', 'am', 'start', '-W', '-n', ACTIVITY, '--es', 'action', 'run', '--es', 'run_id', args.run_id]).decode(), flush=True)
        # am start measures scheduling/startup only. Wait for the actual completed/cancelled result file.
        deadline = time.monotonic() + 1800
        last_update = time.monotonic()
        while time.monotonic() < deadline:
            completion = subprocess.run(device.prefix + ['shell', '-T', 'run-as', PACKAGE, 'cat', f'files/reports/{args.run_id}.done.json'],
                                        capture_output=True, timeout=15)
            if completion.returncode == 0:
                result = json.loads(completion.stdout)
                print(json.dumps(result, indent=2), flush=True)
                if result['status'] != 'COMPLETED':
                    raise RuntimeError('Harness run did not complete; collect the failure evidence')
                rows = [json.loads(line) for line in device.private(['cat', f'files/reports/{args.run_id}.jsonl']).decode().splitlines()]
                failed = [(r['id'], r['module'], r['status'], r.get('error')) for r in rows
                          if r.get('module') and r['status'] in ('FAILED', 'UNAVAILABLE')]
                if failed:
                    raise RuntimeError(f'Module analyses failed; preserve/collect reports and correct failures: {failed}')
                return
            if time.monotonic() - last_update > 30:
                print('Waiting for completed module analyses...', flush=True); last_update = time.monotonic()
            time.sleep(1)
        raise TimeoutError('Run deadline exceeded; no completion assumed')
    finally:
        if args.airplane and previous_airplane == '0':
            device.call(['shell', 'cmd', 'connectivity', 'airplane-mode', 'disable'])


def summary(rows):
    result = {}
    for module in ('quality', 'hands'):
        items = [r for r in rows if r.get('module') == module]
        analysed = [[s for s in r['samples'] if s['state'] == 'ANALYSED'] for r in items] if module == 'hands' else []
        timings = [s['inference_ms'] for group in analysed for s in group[1:]]
        if timings:
            ordered = sorted(timings)
            result['warm_hand_inference_ms'] = {'samples': len(timings), 'mean': statistics.mean(timings),
                'p50': statistics.median(timings), 'p95_nearest_rank': ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]}
        if analysed:
            first = [group[0]['inference_ms'] for group in analysed if group]
            result['first_hand_inference_ms_per_analysis'] = first
            result['hand_initialization_ms_per_analysis'] = [r['initialization_ms'] for r in items]
            result['hand_sample_end_to_end_ms'] = [s['decode_ms'] + s['preprocessing_ms'] + s['inference_ms'] for group in analysed for s in group]
        video = [r for r in items if r['duration_ms']]
        result[module] = {'results': len(items), 'status_counts': {s: sum(r['status'] == s for r in items) for s in sorted({r['status'] for r in items})},
            'videos': len(video), 'total_video_ms': sum(r['duration_ms'] for r in video),
            'end_to_end_ms_per_video_minute_including_init': sum(r['wall_time_ms'] for r in video) * 60000 / sum(r['duration_ms'] for r in video) if video else None}
    result['acceptance'] = 'Measurements only; held-out accuracy, labelled coverage and representative hardware gates are separate'
    combined = [r for r in rows if r.get('type') == 'item_end_to_end' and r.get('duration_ms')]
    result['combined_modules_ms_per_video_minute_including_init_and_result_writes'] = (
        sum(r['wall_ms'] for r in combined) * 60000 / sum(r['duration_ms'] for r in combined) if combined else None)
    return result


def collect(device, args):
    if args.output.resolve().is_relative_to(REPO):
        raise ValueError('Private report/gray output must be outside Git')
    args.output.mkdir(parents=True, exist_ok=True)
    for suffix in ('jsonl', 'done.json'):
        (args.output / f'{args.run_id}.{suffix}').write_bytes(device.private(['cat', f'files/reports/{args.run_id}.{suffix}']))
    rows = [json.loads(x) for x in (args.output / f'{args.run_id}.jsonl').read_text().splitlines()]
    if args.gray:
        for r in rows:
            if r.get('module') == 'quality' and r['duration_ms'] is None and r['samples'] and r['samples'][0]['metrics']:
                name = f"{args.run_id}-{r['id']}.gray"
                (args.output / name).write_bytes(device.private(['cat', f'files/reports/{name}']))
    report = summary(rows)
    (args.output / f'{args.run_id}.summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'run', 'collect', 'instrument'])
    parser.add_argument('--serial', required=True); parser.add_argument('--expect-model', required=True)
    parser.add_argument('--dataset-root', type=Path); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id'); parser.add_argument('--representative', action='store_true')
    parser.add_argument('--repeats', type=int, default=1); parser.add_argument('--airplane', action='store_true'); parser.add_argument('--gray', action='store_true')
    args = parser.parse_args()
    device = Device(args.serial, args.expect_model)
    if args.action == 'stage':
        if not args.dataset_root or not 1 <= args.repeats <= 20:
            raise ValueError('Provide --dataset-root and --repeats in 1..20')
        stage(device, args)
    elif args.action == 'run':
        run(device, args)
    elif args.action == 'collect':
        collect(device, args)
    else:
        result = device.call(['shell', 'am', 'instrument', '-w', '-e', 'class', PACKAGE + '.AssistanceInstrumentedTest',
                              PACKAGE + '.test/androidx.test.runner.AndroidJUnitRunner'], timeout=300).decode()
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'instrumentation.log').write_text(result)
        print(result)
        if 'OK (7 tests)' not in result or 'FAILURES!!!' in result:
            raise SystemExit('Real-device instrumentation did not pass all seven tests')


if __name__ == '__main__':
    main()
