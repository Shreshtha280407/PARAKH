import unittest
from protocol import confusion, partition_ids, technical_prediction


def sample(time, mean=120, variance=100, motion=None):
    return {'timestamp_ms': time, 'metrics': {'mean_luma': mean, 'highlight_clip_fraction': 0,
        'laplacian_variance': variance}, 'motion': motion}


class EvaluationProtocolTest(unittest.TestCase):
    def setUp(self):
        self.thresholds = {'mean_dark_below': 60, 'mean_bright_above': 255, 'highlight_fraction_above': 1,
            'laplacian_variance_below': 40, 'motion_translation_px_at_least': 2}

    def test_failed_predictions_are_not_absence_or_true_negatives(self):
        result = confusion([(True, True), (True, None), (False, False), (False, None)])
        self.assertEqual(result['confusion']['unavailable_positive'], 1)
        self.assertEqual(result['confusion']['unavailable_negative'], 1)
        self.assertEqual(result['recall'], 0.5)
        self.assertEqual(result['precision'], 1.0)

    def test_clear_missing_target_and_ordinary_local_motion_do_not_become_bad(self):
        record = {'duration_ms': 1001, 'samples': [sample(0), sample(125, motion={'reliable': True, 'translation_px': 0}), sample(1000)]}
        self.assertFalse(technical_prediction(record, self.thresholds))
        record['samples'][1]['motion'] = {'reliable': False, 'translation_px': 4}
        self.assertFalse(technical_prediction(record, self.thresholds))

    def test_burst_partner_flags_and_actual_camera_motion_count(self):
        record = {'duration_ms': 1000, 'samples': [sample(0), sample(125, motion={'reliable': True, 'translation_px': 3})]}
        self.assertTrue(technical_prediction(record, self.thresholds))
        self.assertTrue(technical_prediction(record, self.thresholds, condition='CAMERA_MOTION'))
        self.assertFalse(technical_prediction(record, self.thresholds, condition='BLURRY'))

    def test_all_failed_capture_is_unavailable_not_good(self):
        self.assertIsNone(technical_prediction({'duration_ms': 1000, 'samples': [
            {'timestamp_ms': 0, 'metrics': None, 'motion': None}]}, self.thresholds))

    def test_unavailable_camera_motion_is_not_a_negative_observation(self):
        record = {'duration_ms': 1000, 'samples': [sample(0), sample(125, motion={'reliable': False, 'translation_px': 4})]}
        self.assertIsNone(technical_prediction(record, self.thresholds, condition='CAMERA_MOTION'))

    def test_owner_proxy_design_cannot_be_reported_as_holdout(self):
        protocol = {'evaluation_design': 'owner_approved_proxy_resubstitution', 'partitions': {'calibration': ['one'], 'validation': [], 'heldout': []}}
        self.assertEqual(['one'], partition_ids(protocol, 'proxy'))
        for role in ('validation', 'heldout'):
            with self.assertRaisesRegex(ValueError, 'never'):
                partition_ids(protocol, role)

    def test_photo_and_video_blur_calibration_do_not_share_a_boundary(self):
        thresholds = dict(self.thresholds, laplacian_variance_below=400, video_laplacian_variance_below=40)
        self.assertTrue(technical_prediction({'duration_ms': None, 'samples': [sample(0, variance=100)]}, thresholds))
        self.assertFalse(technical_prediction({'duration_ms': 1000, 'samples': [sample(0, variance=100)]}, thresholds))

    def test_isolated_single_anchor_spike_is_suppressed_by_min_consecutive_anchors(self):
        # Two non-adjacent camera-motion anchors out of 10: real evidence from the proxy
        # dataset (e.g. m-5dba026ae2fe) shows this pattern on videos independently reviewed
        # as technically good, not a sustained shake event.
        motion = {'reliable': True, 'translation_px': 3}
        samples = [sample(t) for t in range(0, 10000, 1000)]
        samples[6] = sample(6000, motion=motion)
        samples[9] = sample(9000, motion=motion)
        record = {'duration_ms': 10000, 'samples': samples}
        self.assertTrue(technical_prediction(record, self.thresholds, clip_bad_fraction=0.2))
        self.assertFalse(technical_prediction(record, self.thresholds, clip_bad_fraction=0.2,
            min_consecutive_anchors={'CAMERA_MOTION': 2}))

    def test_sustained_run_still_counts_under_min_consecutive_anchors(self):
        motion = {'reliable': True, 'translation_px': 3}
        samples = [sample(t) for t in range(0, 10000, 1000)]
        samples[5] = sample(5000, motion=motion)
        samples[6] = sample(6000, motion=motion)
        record = {'duration_ms': 10000, 'samples': samples}
        self.assertTrue(technical_prediction(record, self.thresholds, clip_bad_fraction=0.2,
            min_consecutive_anchors={'CAMERA_MOTION': 2}))

    def test_excluded_condition_never_gates_the_combined_verdict_but_still_reports_standalone(self):
        motion = {'reliable': True, 'translation_px': 3}
        record = {'duration_ms': 1000, 'samples': [sample(0), sample(125, motion=motion)]}
        self.assertFalse(technical_prediction(record, self.thresholds, clip_bad_fraction=0.2,
            excluded_conditions={'CAMERA_MOTION'}))
        self.assertTrue(technical_prediction(record, self.thresholds, clip_bad_fraction=0.2,
            excluded_conditions={'CAMERA_MOTION'}, condition='CAMERA_MOTION'))


if __name__ == '__main__':
    unittest.main()
