#!/usr/bin/env python3
"""Generate durable scalar-only benchmark evidence from completed isolated Android runs."""
import argparse
import hashlib
import json
import math
import statistics
import zipfile
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distribution(values):
    values = sorted(values)
    return {'count': len(values), 'mean': statistics.mean(values) if values else None,
        'p50': statistics.median(values) if values else None,
        'p95_nearest_rank': values[math.ceil(0.95 * len(values)) - 1] if values else None,
        'max': max(values) if values else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True); p.add_argument('--done', type=Path, required=True)
    p.add_argument('--debug-apk', type=Path, required=True); p.add_argument('--release-apk', type=Path, required=True)
    p.add_argument('--quality-aar', type=Path, required=True); p.add_argument('--hands-aar', type=Path, required=True)
    p.add_argument('--instrumentation', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise ValueError('Preserve existing evidence; use a new report version')
    rows = [json.loads(x) for x in args.results.read_text().splitlines()]
    metadata = next(r for r in rows if r.get('type') == 'run'); done = json.loads(args.done.read_text())
    if done['status'] != 'COMPLETED' or done['run_id'] != metadata['run_id'] or metadata['airplane_mode'] != 1:
        raise ValueError('Completed, matching airplane-mode run evidence is required')
    if 'OK (7 tests)' not in args.instrumentation.read_text():
        raise ValueError('Actual seven-test instrumentation success is required')
    modules = [r for r in rows if r.get('module')]
    if any(r['status'] in ('FAILED', 'UNAVAILABLE') for r in modules):
        raise ValueError('Module failures must be resolved, not relabelled accepted')
    if len({(r['module'], r['id'], r['repeat']) for r in modules}) != len(modules):
        raise ValueError('Duplicate result rows')
    result = {'scope': 'owner-approved proxy functional verification; no independent holdout, field, entry/mid or IC-2 acceptance',
        'physical_device': {k: metadata[k] for k in ('manufacturer', 'model', 'api', 'abis', 'ram_bytes')},
        'device_class': 'OnePlus 13R flagship', 'measured_variant': 'isolated debug harness; release built/packaged, not physically run',
        'source_version': metadata['source_version'], 'run_id': metadata['run_id'], 'airplane_mode': metadata['airplane_mode'],
        'memory_method': metadata['memory_method'], 'completed_run': done,
        'input_evidence_sha256': {'android_results': sha(args.results), 'done': sha(args.done), 'instrumentation': sha(args.instrumentation)},
        'sample_timestamps': metadata['timestamp_convention'], 'modules': {}}
    for module in ('quality', 'hands'):
        records = [r for r in modules if r['module'] == module]
        video = [r for r in records if r['duration_ms'] is not None]
        photos = [r for r in records if r['duration_ms'] is None]
        samples = [s for r in video for s in r['samples']]
        summary = {'unique_captures': len({r['id'] for r in records}), 'analyses': len(records),
            'photos': len(photos), 'videos': len(video), 'sampled_video_duration_ms': sum(r['duration_ms'] for r in video),
            'status_counts': {status: sum(r['status'] == status for r in records) for status in sorted({r['status'] for r in records})},
            'video_module_ms_per_video_minute_including_initialization_and_close': sum(r['wall_time_ms'] for r in video) * 60000 / sum(r['duration_ms'] for r in video),
            'photo_module_wall_ms': distribution([r['wall_time_ms'] for r in photos]),
            'video_module_wall_ms': distribution([r['wall_time_ms'] for r in video]),
            'video_frame_decode_ms': distribution([s['decode_ms'] for s in samples]),
            'video_sample_count': len(samples)}
        if module == 'hands':
            valid_groups = [[s for s in r['samples'] if s['state'] == 'ANALYSED'] for r in video]
            valid = [s for group in valid_groups for s in group]
            summary.update(initialization_ms_all_analyses=distribution([r['initialization_ms'] for r in records]),
                first_video_inference_ms=distribution([g[0]['inference_ms'] for g in valid_groups if g]),
                warm_video_inference_ms=distribution([s['inference_ms'] for g in valid_groups for s in g[1:]]),
                video_preprocessing_ms=distribution([s['preprocessing_ms'] for s in valid]),
                video_sample_decode_preprocess_inference_ms=distribution([sum(s[k] for k in ('decode_ms', 'preprocessing_ms', 'inference_ms')) for s in valid]),
                observed_input_resolutions=sorted({f"{s['width']}x{s['height']}" for s in valid}),
                hand_count_samples={str(n): sum(s['hand_count'] == n for s in valid) for n in (0, 1, 2)},
                delegate='CPU', native_threads='MediaPipe defaults; this dependency exposes no explicit CPU thread setting',
                configuration_sha256=records[0]['configuration_sha256'], model_sha256=records[0]['model_sha256'])
        else:
            summary.update(video_calculation_ms=distribution([s['calculation_ms'] for s in samples]),
                observed_input_resolutions=sorted({f"{s['metrics']['width']}x{s['metrics']['height']}" for s in samples if s['metrics']}),
                motion_reliable_pairs=sum(r['motion_analysed_pairs'] for r in video),
                motion_requested_pairs=sum(r['motion_requested_pairs'] for r in video),
                threshold_version=records[0]['threshold_version'], threshold_sha256=records[0]['threshold_sha256'])
        result['modules'][module] = summary
    combined = [r for r in rows if r.get('type') == 'item_end_to_end' and r['duration_ms'] is not None]
    result['combined_analysis_and_result_writes_ms_per_video_minute'] = sum(r['wall_ms'] for r in combined) * 60000 / sum(r['duration_ms'] for r in combined)
    result['wall_time_scope'] = 'Module wall includes reader/model close; combined includes both modules and result writes, excludes harness input-checksum validation; completed-run wall includes that validation too. am-start scheduling is never analysis time.'
    result['measurement_conditions'] = 'USB attached, consecutive local runs; debug harness, memory sampler active. No thermal/frequency control or cold-storage claim. The sampler delays 100ms between calls; measurement overhead lengthens effective cadence. Observed peaks are not kernel high-water marks.'
    result['artifacts'] = {name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for name, path in
        [('debug_apk', args.debug_apk), ('release_unsigned_apk', args.release_apk), ('quality_release_aar', args.quality_aar), ('hands_release_aar', args.hands_aar)]}
    with zipfile.ZipFile(args.debug_apk) as z:
        if json.loads(z.read('assets/assistance-source.json'))['source_version'] != metadata['source_version']:
            raise ValueError('Benchmark source differs from packaged source')
        result['packaged_model_and_native_entries'] = [{'entry': info.filename, 'stored_bytes': info.compress_size, 'uncompressed_bytes': info.file_size}
            for info in z.infolist() if info.filename == 'assets/hands/hand_landmarker.task' or info.filename.startswith('lib/')]
    result['size_scope'] = 'Standalone four-ABI harness and AAR sizes; native/model entries are attributable components, not a measured incremental production-APK delta. Production app does not depend on assistance.'
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'run_id': metadata['run_id'], 'source_version': result['source_version'],
        'completed_wall_ms': done['wall_ms'], 'observed_peak_pss_kb': done['observed_peak_pss_kb'],
        'combined_ms_per_video_minute': result['combined_analysis_and_result_writes_ms_per_video_minute']}, indent=2))


if __name__ == '__main__':
    main()
