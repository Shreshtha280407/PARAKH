"""Frozen grouped-split guards shared by calibration and held-out evaluation."""
import csv
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_protocol(path):
    path = Path(path)
    protocol = json.loads(path.read_text())
    if protocol.get('state') != 'frozen':
        raise ValueError('Freeze independently reviewed, grouped splits before tuning/evaluation')
    for key in ('manifest', 'quality_labels', 'hand_sample_labels', 'assignments', 'near_duplicate_candidates'):
        relative = Path(protocol[key]['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Protocol metadata paths must be repository-relative and portable')
        source = REPO / protocol[key]['path']
        if digest(source) != protocol[key]['sha256']:
            raise ValueError(f'{key} changed after split freeze; version the protocol instead of silently replacing truth')
    if not 0 < protocol['quality_clip_bad_fraction'] <= 1:
        raise ValueError('Invalid frozen clip aggregation fraction')
    rows = [json.loads(x) for x in (REPO / protocol['manifest']['path']).read_text().splitlines()]
    unique = {r['sha256'] for r in rows}
    by_id = {r['id']: r for r in rows}
    partitions = protocol['partitions']
    design = protocol.get('evaluation_design', 'independent_grouped')
    if set(partitions) != {'calibration', 'validation', 'heldout'}:
        raise ValueError('Protocol must explicitly declare all partition roles')
    if design == 'owner_approved_proxy_resubstitution':
        if not partitions['calibration'] or partitions['validation'] or partitions['heldout'] or not protocol.get('owner_scope_amendment'):
            raise ValueError('Proxy scope must not invent validation/holdout partitions')
    elif design != 'independent_grouped' or not all(partitions.values()):
        raise ValueError('Independent design requires three non-empty partitions')
    ids = [identity for values in partitions.values() for identity in values]
    if len(ids) != len(set(ids)) or any(identity not in by_id for identity in ids):
        raise ValueError('Repeated or unknown capture identity in splits')
    if {by_id[i]['sha256'] for i in ids} != unique or len(ids) != len(unique):
        raise ValueError('Each unique capture must occur exactly once; derivatives/aliases cannot inflate the set')
    owners = {}
    groups = protocol['groups']
    for split, identities in partitions.items():
        for identity in identities:
            group = groups[identity]
            if group in owners and owners[group] != split:
                raise ValueError('Scene/session group leakage across partitions')
            owners[group] = split
    # All initial archive media must stay together; owner supplied no independent-session map.
    original_ids = set(protocol.get('original_collection_ids', []))
    original_partitions = {s for s, identities in partitions.items() if original_ids.intersection(identities)}
    if len(original_partitions) > 1:
        raise ValueError('Initial repeated-scene collection was split across partitions')
    return protocol, by_id, digest(path)


def partition_ids(protocol, role):
    proxy = protocol.get('evaluation_design') == 'owner_approved_proxy_resubstitution'
    if role == 'proxy':
        if not proxy:
            raise ValueError('Proxy evaluation requires explicit owner-approved resubstitution design')
        return protocol['partitions']['calibration']
    if proxy and role in ('validation', 'heldout'):
        raise ValueError('Proxy reuse can never be reported as independent validation/holdout')
    return protocol['partitions'][role]


def read_results(path, module):
    records = [json.loads(x) for x in Path(path).read_text().splitlines()]
    module_records = [r for r in records if r.get('module') == module]
    if len({r['id'] for r in module_records}) != len(module_records):
        raise ValueError('Evaluation requires one result per capture, not repeated benchmark runs')
    return {r['id']: r for r in module_records}


def quality_labels(protocol):
    with (REPO / protocol['quality_labels']['path']).open(newline='') as f:
        rows = list(csv.DictReader(f))
    required = {'id', 'sha256', 'verified_quality_labels', 'bad_capture', 'review_status', 'provenance'}
    if not rows or not required <= rows[0].keys():
        raise ValueError('Quality truth must include independent verified labels, status, bad_capture and provenance')
    if len(rows) != len({r['id'] for r in rows}):
        raise ValueError('Duplicate quality ground-truth rows')
    for row in rows:
        if row['review_status'] not in ('verified', 'unjudgeable') or row['bad_capture'] not in ('true', 'false', 'unjudgeable') or not row['provenance']:
            raise ValueError('Quality truth has an invalid review state or missing provenance')
        labels = set(filter(None, row['verified_quality_labels'].split('|')))
        if not labels <= {'DARK', 'BLURRY', 'CAMERA_MOTION', 'OVEREXPOSED'}:
            raise ValueError('Unsupported verified quality condition')
        if row['review_status'] == 'verified' and (row['bad_capture'] == 'unjudgeable' or (row['bad_capture'] == 'true') != bool(labels)):
            raise ValueError('Verified quality truth disagrees with independently observed conditions')
        if row['review_status'] == 'unjudgeable' and row['bad_capture'] != 'unjudgeable':
            raise ValueError('Unknown review cannot become an observed good/bad label')
    manifest = {r['id']: r for r in (json.loads(x) for x in (REPO / protocol['manifest']['path']).read_text().splitlines())}
    expected = {i for ids in protocol['partitions'].values() for i in ids}
    if set(r['id'] for r in rows) != expected or any(r['sha256'] != manifest[r['id']]['sha256'] for r in rows):
        raise ValueError('Quality truth must exactly match all unique assigned capture identities/hashes')
    return {r['id']: r for r in rows}


def capture_flags(record, thresholds):
    """Recompute the exact Kotlin threshold rules on exported Android metrics."""
    out = []
    for sample in record['samples']:
        metrics = sample['metrics']; motion = sample['motion']; flags = set()
        if metrics:
            if metrics['mean_luma'] < thresholds['mean_dark_below']:
                flags.add('DARK')
            if (metrics['mean_luma'] > thresholds['mean_bright_above'] and
                    metrics['highlight_clip_fraction'] > thresholds['highlight_fraction_above']):
                flags.add('OVEREXPOSED')
            blur_threshold = thresholds.get('video_laplacian_variance_below', thresholds['laplacian_variance_below']) if record['duration_ms'] is not None else thresholds['laplacian_variance_below']
            if (metrics['mean_luma'] >= thresholds['mean_dark_below'] and metrics['laplacian_variance'] is not None
                    and metrics['laplacian_variance'] < blur_threshold):
                flags.add('BLURRY')
            if motion and motion['reliable'] and motion['translation_px'] >= thresholds['motion_translation_px_at_least']:
                flags.add('CAMERA_MOTION')
        out.append((sample['timestamp_ms'], flags, metrics is not None))
    return out


def technical_prediction(record, thresholds, clip_bad_fraction=0.2, condition=None,
                          min_consecutive_anchors=None, excluded_conditions=None):
    """min_consecutive_anchors/excluded_conditions refine ONLY the combined (condition=None)
    clip verdict: a per-condition run shorter than its minimum is noise, not a sustained
    defect, and an excluded condition is still computed/reported but never gates the verdict.
    Per-condition standalone evaluation (condition=<X>) is unaffected, so each flag's own
    disclosed precision/recall stays honest regardless of how it is combined for the verdict."""
    if condition == 'CAMERA_MOTION' and not any(s.get('motion', {}).get('reliable') if s.get('motion') else False for s in record['samples']):
        return None  # No reliable temporal observations must not become a negative decision.
    samples = capture_flags(record, thresholds)
    if condition:
        samples = [(time, flags.intersection({condition}), valid) for time, flags, valid in samples]
    if not any(valid for _, _, valid in samples):
        return None
    if record['duration_ms'] is None:
        return bool(samples[0][1])
    lookup = {time: (flags, valid) for time, flags, valid in samples}
    anchors = [(time, flags, valid) for time, flags, valid in samples if time % 1000 == 0]
    if not anchors:
        return None
    anchor_times = [time for time, _, _ in anchors]
    # Failures remain in the requested-anchor denominator; never silently improve recall/coverage.
    combined = {time: flags | lookup.get(time + 125, (set(), False))[0] for time, flags, _ in anchors}
    if condition is None and (min_consecutive_anchors or excluded_conditions):
        excluded = excluded_conditions or set()
        min_run = min_consecutive_anchors or {}
        observed_conditions = {c for flags in combined.values() for c in flags}
        qualifying = set()
        for cond in observed_conditions - excluded:
            required = min_run.get(cond, 1)
            run = []
            for time in anchor_times:
                if cond in combined[time]:
                    run.append(time)
                else:
                    if len(run) >= required:
                        qualifying.update(run)
                    run = []
            if len(run) >= required:
                qualifying.update(run)
        bad = len(qualifying)
    else:
        bad = sum(1 for time in anchor_times if combined[time])
    return bad / len(anchor_times) >= clip_bad_fraction


def confusion(truth_prediction):
    matrix = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unavailable_positive': 0, 'unavailable_negative': 0}
    for truth, prediction in truth_prediction:
        if prediction is None:
            matrix['unavailable_positive' if truth else 'unavailable_negative'] += 1
        else:
            matrix[('tp' if truth else 'fp') if prediction else ('fn' if truth else 'tn')] += 1
    tp, fp, fn, tn = (matrix[k] for k in ('tp', 'fp', 'fn', 'tn'))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn + matrix['unavailable_positive']) if tp + fn + matrix['unavailable_positive'] else None
    return {'confusion': matrix, 'precision': precision, 'recall': recall, 'captures': sum(matrix.values()),
            'false_positive_rate_on_technically_good': fp / (fp + tn + matrix['unavailable_negative']) if fp + tn + matrix['unavailable_negative'] else None}
