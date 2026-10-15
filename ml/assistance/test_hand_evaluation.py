import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('hand_eval', Path(__file__).resolve().parents[1] / 'hands/eval.py')
hand_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hand_eval)


class HandEvaluationTest(unittest.TestCase):
    def record(self):
        return {'duration_ms': 2500, 'visible_ratio': 0.0,
            'samples': [{'timestamp_ms': 0, 'state': 'ANALYSED', 'hand_present': False},
                        {'timestamp_ms': 1000, 'state': 'INFERENCE_FAILED', 'hand_present': None},
                        {'timestamp_ms': 2000, 'state': 'ANALYSED', 'hand_present': False}],
            'hands_not_visible_intervals': [{'start_ms': 0, 'end_ms': 1000}, {'start_ms': 2000, 'end_ms': 2500}]}

    def test_failed_sample_breaks_absence_cells_and_ratio_uses_valid_samples(self):
        hand_eval.verify_aggregation(self.record(), 1000)

    def test_incorrect_actual_android_ratio_is_rejected(self):
        record = self.record(); record['visible_ratio'] = 1 / 3
        with self.assertRaisesRegex(ValueError, 'ratio'):
            hand_eval.verify_aggregation(record, 1000)

    def test_interval_bridge_over_failed_sample_is_rejected(self):
        record = self.record(); record['hands_not_visible_intervals'] = [{'start_ms': 0, 'end_ms': 2500}]
        with self.assertRaisesRegex(ValueError, 'interval'):
            hand_eval.verify_aggregation(record, 1000)

    def test_transition_tolerance_and_unjudgeable_gaps_are_explicit(self):
        truth = {0: 'present', 1000: 'absent', 2000: 'absent', 3000: 'unjudgeable', 4000: 'present'}
        predictions = {t: {'state': 'ANALYSED', 'hand_present': t < 2000} for t in truth}
        result = hand_eval.transition_metrics(truth, predictions, 1000)
        self.assertEqual(1, result['manual_transitions'])
        self.assertEqual(1, result['matched_within_one_sampling_step'])
        self.assertEqual(1000, result['matched_boundary_mean_absolute_error_ms'])

    def test_gap_filled_fills_isolated_miss_but_not_a_sustained_absence(self):
        samples = [{'timestamp_ms': 0, 'state': 'ANALYSED', 'hand_present': True},
                   {'timestamp_ms': 1000, 'state': 'ANALYSED', 'hand_present': False},
                   {'timestamp_ms': 2000, 'state': 'ANALYSED', 'hand_present': True},
                   {'timestamp_ms': 3000, 'state': 'ANALYSED', 'hand_present': False},
                   {'timestamp_ms': 4000, 'state': 'ANALYSED', 'hand_present': False},
                   {'timestamp_ms': 5000, 'state': 'ANALYSED', 'hand_present': True}]
        filled = hand_eval.gap_filled(samples, 1000)
        self.assertEqual({0: True, 1000: True, 2000: True, 3000: False, 4000: False, 5000: True}, filled)

    def test_gap_filled_never_fills_across_a_failed_or_unjudgeable_neighbour(self):
        samples = [{'timestamp_ms': 0, 'state': 'ANALYSED', 'hand_present': True},
                   {'timestamp_ms': 1000, 'state': 'INFERENCE_FAILED', 'hand_present': None},
                   {'timestamp_ms': 2000, 'state': 'ANALYSED', 'hand_present': False},
                   {'timestamp_ms': 3000, 'state': 'ANALYSED', 'hand_present': True}]
        filled = hand_eval.gap_filled(samples, 1000)
        self.assertEqual({0: True, 1000: None, 2000: False, 3000: True}, filled)

    def test_incorrect_actual_android_gap_filled_ratio_is_rejected(self):
        record = {'duration_ms': 4000, 'visible_ratio_gap_filled': 0.0,
            'samples': [{'timestamp_ms': 0, 'state': 'ANALYSED', 'hand_present': True},
                        {'timestamp_ms': 1000, 'state': 'ANALYSED', 'hand_present': False},
                        {'timestamp_ms': 2000, 'state': 'ANALYSED', 'hand_present': True}],
            'hands_not_visible_intervals_gap_filled': []}
        with self.assertRaisesRegex(ValueError, 'ratio'):
            hand_eval.verify_gap_filled_aggregation(record, 1000)


if __name__ == '__main__':
    unittest.main()
