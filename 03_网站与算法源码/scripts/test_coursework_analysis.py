"""Known-answer checks for measurement and partial-annotation comparison."""
import copy
from itertools import combinations
import random
import unittest

from coursework_analysis import analyze_record, pair_intervals


def wave(kind, a, b):
    return {"type": kind, "start": a, "end": b}


def record(predicted=(), references=(), peaks=()):
    return {"id": "fixture", "fs": 250, "raw": [0] * 2500,
            "waves": list(predicted), "groundTruth": list(references), "rPeaks": list(peaks)}


class CourseworkAnalysisTests(unittest.TestCase):
    def test_qrs_known_durations_and_clipped_edges(self):
        result = analyze_record(record([
            wave("QRS", 0, .08), wave("QRS", 1, 1.1),
            wave("QRS", 2, 2.2), wave("QRS", 9.9, 9.996)], peaks=[.04, 1.04, 2.05, 9.94]))
        s = result["qrs"]["summary"]
        self.assertEqual((s["totalCount"], s["includedCount"], s["edgeExcludedCount"]), (4, 2, 2))
        self.assertEqual((s["meanMs"], s["medianMs"], s["minMs"], s["maxMs"]), (150, 150, 100, 200))
        self.assertEqual(s["sampleStepMs"], 4)

    def test_signed_error_and_qrs_duration_error(self):
        result = analyze_record(record([wave("QRS", 1.004, 1.108)], [wave("QRS", 1, 1.1)]))
        row = result["comparison"]["rows"][0]
        self.assertEqual((row["onsetErrorMs"], row["offsetErrorMs"], row["durationErrorMs"]), (4, 8, 4))
        self.assertTrue(row["bothWithinLimits"])

    def test_missing_prediction_stays_in_acceptance_denominator(self):
        c = analyze_record(record([wave("P", 1, 1.1)], [wave("P", 1, 1.1), wave("P", 2, 2.1)]))["comparison"]
        s = c["summaries"][0]
        self.assertEqual((s["matchedCount"], s["unmatchedReferenceCount"], s["pairingRatePct"]), (1, 1, 50))
        self.assertEqual(s["bothWithinRatePct"], 50)
        self.assertEqual(s["onsetMaeMs"], 0)

    def test_unannotated_predictions_are_unscored(self):
        c = analyze_record(record([wave("T", 1, 1.2)]))["comparison"]
        s = c["summaries"][2]
        self.assertEqual(s["unscoredPredictionCount"], 1)
        self.assertIsNone(s["pairingRatePct"])
        self.assertIsNone(s["bothWithinRatePct"])
        self.assertIsNone(s["onsetMaeMs"])
        self.assertIsNone(c["precision"])
        self.assertIsNone(c["f1"])

    def test_duplicates_cannot_reuse_reference(self):
        c = analyze_record(record([wave("P", 1, 1.1), wave("P", 1.01, 1.11)], [wave("P", 1, 1.1)]))["comparison"]
        self.assertEqual(c["summaries"][0]["matchedCount"], 1)
        self.assertEqual(c["summaries"][0]["unscoredPredictionCount"], 1)
        self.assertEqual(c["rows"][0]["predictionIndex"], 1)

    def test_global_pairing_maximizes_count_before_error(self):
        predicted = [(0, wave("P", .04, .48)), (1, wave("P", .25, .35))]
        references = [(0, wave("P", .1, .2)), (1, wave("P", .22, .32))]
        self.assertEqual(pair_intervals(predicted, references), ((0, 0), (1, 1)))

    def test_association_is_not_boundary_acceptance(self):
        c = analyze_record(record([wave("QRS", 1.044, 1.144)], [wave("QRS", 1, 1.1)]))["comparison"]
        self.assertEqual(c["summaries"][1]["matchedCount"], 1)
        self.assertFalse(c["rows"][0]["bothWithinLimits"])
        exact = analyze_record(record([wave("QRS", 1.04, 1.14)], [wave("QRS", 1, 1.1)]))
        self.assertTrue(exact["comparison"]["rows"][0]["bothWithinLimits"])

    def test_no_overlap_or_wrong_class_cannot_match(self):
        c = analyze_record(record([wave("P", 1.1, 1.2), wave("T", 1, 1.1)], [wave("P", 1, 1.1)]))["comparison"]
        self.assertEqual(c["summaries"][0]["matchedCount"], 0)

    def test_r_peak_association_must_be_unique(self):
        q = analyze_record(record([wave("QRS", 1, 1.1), wave("QRS", 1.05, 1.15)], peaks=[1.08]))["qrs"]
        self.assertEqual([r["rPeakSec"] for r in q["rows"]], [None, None])
        q = analyze_record(record([wave("QRS", 1, 1.2)], peaks=[1.05, 1.1]))["qrs"]
        self.assertIsNone(q["rows"][0]["rPeakSec"])

    def test_r_peak_in_multi_peak_qrs_cannot_link_to_another_qrs(self):
        q = analyze_record(record([
            wave("QRS", 1, 1.3), wave("QRS", 1.15, 1.25),
            wave("QRS", 2, 2.1), wave("QRS", 3, 3.1)],
            peaks=[1.1, 1.2, 2.05]))["qrs"]
        self.assertEqual([r["rPeakSec"] for r in q["rows"]], [None, None, 2.05, None])
        self.assertEqual([r["rPeakAssociation"] for r in q["rows"]],
                         ["multiple-peaks", "shared-peak", "unique", "no-peak"])
        self.assertEqual([r["rPeakCountInInterval"] for r in q["rows"]], [2, 1, 1, 0])
        # Duration remains a waveform-boundary measurement even without a peak.
        self.assertEqual(q["summary"]["includedCount"], 4)

    def test_peak_exactly_on_shared_boundary_is_ambiguous(self):
        q = analyze_record(record([
            wave("QRS", 1, 1.1), wave("QRS", 1.1, 1.2)], peaks=[1.1]))["qrs"]
        self.assertEqual([r["rPeakAssociation"] for r in q["rows"]], ["shared-peak", "shared-peak"])
        self.assertEqual([r["rPeakSec"] for r in q["rows"]], [None, None])

    def test_pairing_handles_more_intervals_than_python_recursion_limit(self):
        intervals = [(i, wave("P", .1 + i * .005, .102 + i * .005)) for i in range(1100)]
        pairs = pair_intervals(intervals, intervals)
        self.assertEqual(pairs, tuple((i, i) for i in range(1100)))
        self.assertEqual(pair_intervals([], intervals), ())
        self.assertEqual(pair_intervals(intervals, []), ())

    def test_pairing_matches_exhaustive_feasible_assignments(self):
        # Enumerate all monotone one-to-one assignments for small fixtures. This
        # independent oracle verifies cardinality, error and deterministic ties.
        generator = random.Random(4137)
        for fixture_index in range(80):
            predicted, references = [], []
            for target in (predicted, references):
                for index in range(generator.randrange(5)):
                    start = generator.randrange(20) / 100
                    end = start + generator.randrange(1, 15) / 100
                    target.append((10 - index, wave("P", start, end)))
                target.sort(key=lambda item: (item[1]["start"], item[1]["end"], item[0]))
            feasible = []
            for count in range(min(len(predicted), len(references)) + 1):
                for pi in combinations(range(len(predicted)), count):
                    for ri in combinations(range(len(references)), count):
                        pairs = [(predicted[p], references[r]) for p, r in zip(pi, ri)]
                        if any(min(p["end"], r["end"]) <= max(p["start"], r["start"]) + 1e-8
                               or abs((p["start"] + p["end"]) / 2 - (r["start"] + r["end"]) / 2) > .15 + 1e-11
                               for (_, p), (_, r) in pairs):
                            continue
                        cost = sum(abs(p["start"] - r["start"]) + abs(p["end"] - r["end"])
                                   for (_, p), (_, r) in pairs)
                        assignment = tuple((p[0], r[0]) for p, r in pairs)
                        feasible.append((-count, round(cost, 12), assignment))
            with self.subTest(fixture=fixture_index):
                self.assertEqual(pair_intervals(predicted, references), min(feasible)[2])

    def test_aggregate_statistics_are_not_computed_from_rounded_rows(self):
        predicted = [wave("QRS", i + 0.00000049, i + .10000098) for i in (1, 2)]
        predicted.append(wave("QRS", 3 + 0.00000149, 3 + .10000298))
        references = [wave("QRS", i, i + .1) for i in (1, 2, 3)]
        result = analyze_record(record(predicted, references))
        summary = result["comparison"]["summaries"][1]
        self.assertEqual(summary["onsetMaeMs"], .001)
        self.assertEqual(summary["durationMaeMs"], .001)
        self.assertEqual(result["qrs"]["summary"]["meanMs"], 100.001)

    def test_invalid_interval_is_rejected_and_input_unchanged(self):
        source = record([wave("QRS", 1, 1.1)])
        before = copy.deepcopy(source)
        analyze_record(source)
        self.assertEqual(source, before)
        for candidate in [wave("QRS", 1, 1), wave("QRS", -1, 1), wave("QRS", 1, float("nan"))]:
            with self.assertRaises(ValueError):
                analyze_record(record([candidate]))

    def test_invalid_input_types_and_nonfinite_signals_raise_value_error(self):
        for key, values in {
            "id": [None, "", 23],
            "fs": [True, "250", None, 0, -1, float("nan"), float("inf"), 1e-306, 10 ** 500],
            "raw": [None, [], "signal", [0, float("nan")], [False], ["0"]],
            "filtered": [None, [], [0] * 2499, [float("inf")] * 2500],
            "waves": [None, "waves", [{}], [None], [wave([], 1, 2)],
                      [wave("QRS", "1", 2)], [wave("QRS", True, 2)]],
            "groundTruth": [None, [wave("QRS", 1, None)]],
            "rPeaks": [None, [True], ["1"], [float("nan")], [1, 1], [2, 1], [10]],
        }.items():
            for value in values:
                with self.subTest(key=key, value=repr(value)[:60]):
                    candidate = record()
                    candidate[key] = value
                    with self.assertRaises(ValueError):
                        analyze_record(candidate)
        for candidate in (None, [], "record"):
            with self.assertRaises(ValueError):
                analyze_record(candidate)
        for key in ("fs", "raw", "waves", "groundTruth", "rPeaks"):
            candidate = record()
            del candidate[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                analyze_record(candidate)


if __name__ == "__main__":
    unittest.main()
