"""Standard-library transaction tests; no ECG packages, model, or data downloads."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import prepare_demo as prep


class PrepareDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source-data"
        self.out = self.root / "public" / "demo"
        self.out.mkdir(parents=True)
        for dataset, record, _lead, annotation, _start, _label in prep.RECORDS:
            folder = self.source / dataset
            folder.mkdir(parents=True, exist_ok=True)
            for extension in ("hea", "dat", annotation):
                (folder / f"{record}.{extension}").write_bytes(f"{record}-{extension}".encode())
        self.old_paths = [self.out / f"{p[0]}-{p[1]}.json" for p in prep.RECORDS]
        self.old_paths.append(self.out.parent / "generation_manifest.json")
        for path in self.old_paths:
            path.write_text(f"old:{path.name}", encoding="utf-8")
        self.old = {path: path.read_bytes() for path in self.old_paths}
        self.fake_model = SimpleNamespace()
        self.calls = []

    def loader(self):
        self.calls.append("load")
        return SimpleNamespace(Inference=lambda: self.fake_model)

    def builder(self, *params, detector, source, dependencies):
        self.assertIs(detector, self.fake_model)
        self.assertEqual(source, self.source)
        self.calls.append(f"{params[0]}-{params[1]}")
        return self.valid_payload(params)

    def valid_payload(self, params):
        return {"id": f"{params[0]}-{params[1]}", "dataset": params[0].upper(),
                "record": params[1], "lead": params[2], "startSec": params[4],
                "label": params[5], "fs": 250, "sourceFs": 500,
                "unit": "mV", "mode": "precomputed", "model": "fake model",
                "raw": [0.1] * 2500, "filtered": [0.0] * 2500,
                "waves": [], "groundTruth": [], "rPeaks": [], "rr": [],
                "metrics": {"rPeakCount": 0, "averageHr": None, "minHr": None,
                            "maxHr": None, "meanRr": None}}

    def install_preservable(self, original_only=False, record_ids=None):
        for params in prep.RECORDS:
            record_id = f"{params[0]}-{params[1]}"
            path = self.out / f"{record_id}.json"
            if ((original_only and record_id not in prep.ORIGINAL_RECORD_IDS)
                    or (record_ids is not None and record_id not in record_ids)):
                path.unlink(missing_ok=True)
            else:
                # Deliberate noncompact formatting verifies byte preservation,
                # rather than merely equality after JSON reserialization.
                path.write_text(json.dumps(self.valid_payload(params), indent=2) + "\n", encoding="utf-8")
        return {path: path.read_bytes() for path in self.out.glob("*.json")}

    def generate(self, **kwargs):
        return prep.generate_demos(source=self.source, out=self.out,
                                   dependency_loader=self.loader,
                                   demo_builder=kwargs.pop("demo_builder", self.builder),
                                   versions_provider=lambda: {"python": "fake", "openecg": "fake"},
                                   **kwargs)

    def assert_old_preserved(self):
        self.assertEqual({path: path.read_bytes() for path in self.old_paths}, self.old)

    def test_missing_source_fails_before_loading_and_preserves_all_outputs(self):
        (self.source / "qtdb" / "sel103.q1c").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "sel103.q1c"):
            self.generate()
        self.assertEqual(self.calls, [])
        self.assert_old_preserved()

    def test_model_failure_preserves_all_outputs(self):
        def failing_builder(*params, **kwargs):
            if params[1] == "1":
                raise ValueError("fake inference failed")
            return self.builder(*params, **kwargs)
        with self.assertRaisesRegex(ValueError, "fake inference failed"):
            self.generate(demo_builder=failing_builder)
        self.assert_old_preserved()

    def test_complete_success_replaces_all_records_and_writes_external_manifest(self):
        result = self.generate()
        manifest_path = self.out.parent / "generation_manifest.json"
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), result)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["recordCount"], len(prep.RECORDS))
        self.assertEqual(len(result["sources"]), len(prep.RECORDS) * 3)
        self.assertEqual(len(result["outputs"]), len(prep.RECORDS))
        self.assertEqual(result["generatedCount"], len(prep.RECORDS))
        self.assertEqual(result["preservedExisting"], [])
        self.assertEqual(result["model"]["status"], "unknown")
        self.assertFalse(result["payloadModelLabelIsRuntimeVerification"])
        self.assertEqual(len(list(self.out.glob("*.json"))), len(prep.RECORDS))
        for item in result["outputs"]:
            path = self.out.parent / item["path"]
            self.assertEqual(prep.sha256_file(path), item["sha256"])
        self.assertEqual(self.calls[0], "load")
        self.assertEqual(self.calls[1:], [f"{p[0]}-{p[1]}" for p in prep.RECORDS])
        self.assertEqual(list(self.out.parent.glob(".prepare-demo-*")), [])

    def test_late_manifest_publication_failure_rolls_back_record_group(self):
        calls = []
        real_replace = prep.os.replace
        def fail_once(source, target):
            calls.append(Path(target).name)
            if len(calls) == len(prep.RECORDS) + 1:
                raise OSError("fake manifest disk failure")
            return real_replace(source, target)
        with self.assertRaisesRegex(RuntimeError, "previous outputs restored"):
            self.generate(replace_file=fail_once)
        self.assert_old_preserved()
        self.assertEqual(list(self.out.parent.glob(".prepare-demo-*")), [])

    def test_group_rollback_removes_new_outputs_when_none_existed(self):
        for path in self.old_paths:
            path.unlink()
        calls = []
        def fail_once(source, target):
            calls.append(target)
            if len(calls) == 3:
                raise OSError("fake write failure")
            return prep.os.replace(source, target)
        with self.assertRaisesRegex(RuntimeError, "previous outputs restored"):
            self.generate(replace_file=fail_once)
        self.assertTrue(all(not path.exists() for path in self.old_paths))

    def test_rollback_failure_preserves_recovery_backups(self):
        calls = []
        def broken_replace(source, target):
            calls.append(target)
            if len(calls) >= 2:
                raise OSError("fake persistent disk failure")
            return prep.os.replace(source, target)
        with self.assertRaisesRegex(RuntimeError, "rollback incomplete"):
            self.generate(replace_file=broken_replace)
        stage, = self.out.parent.glob(".prepare-demo-*")
        self.assertEqual((stage / "backup-0").read_bytes(), self.old[self.old_paths[0]])

    def test_changed_source_during_generation_fails_without_publication(self):
        def changing_builder(*params, **kwargs):
            result = self.builder(*params, **kwargs)
            (self.source / "ludb" / "16.dat").write_bytes(b"changed")
            return result
        with self.assertRaisesRegex(RuntimeError, "Source files changed"):
            self.generate(demo_builder=changing_builder)
        self.assert_old_preserved()

    def test_nonfinite_json_preserves_old_group(self):
        def bad_builder(*params, **kwargs):
            result = self.builder(*params, **kwargs)
            result["raw"] = [float("nan")]
            return result
        with self.assertRaises(ValueError):
            self.generate(demo_builder=bad_builder)
        self.assert_old_preserved()

    def test_model_hash_only_comes_from_instantiated_runtime_path(self):
        model_file = self.root / "fake.onnx"
        model_file.write_bytes(b"fake model, never executed")
        self.fake_model.session = SimpleNamespace(_model_path=str(model_file))
        info = self.generate()["model"]
        self.assertEqual(info["status"], "identified")
        self.assertEqual(info["files"][0]["sha256"], prep.sha256_file(model_file))
        self.assertEqual(info["files"][0]["attribute"], "detector.session._model_path")
        # OpenECG 0.11.0's real Inference uses .path for the TFLite model.
        tflite_file = self.root / "boundary_int8.tflite"
        tflite_file.write_bytes(b"fixture tflite, never executed")
        direct = prep.model_provenance(SimpleNamespace(path=str(tflite_file)))
        self.assertEqual(direct["files"][0]["attribute"], "detector.path")
        self.assertEqual(direct["files"][0]["sha256"], prep.sha256_file(tflite_file))
        self.assertEqual(prep.model_provenance(SimpleNamespace(path=str(self.root)))["status"], "unknown")

    def test_cli_failure_returns_nonzero_and_names_error(self):
        stderr = io.StringIO()
        with patch.object(prep, "generate_demos", side_effect=RuntimeError("fake error")):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(prep.main([]), 1)
        self.assertIn("generation failed", stderr.getvalue())
        self.assertIn("fake error", stderr.getvalue())

    def test_new_only_preserves_original_bytes_and_infers_only_missing_catalog_entries(self):
        originals = self.install_preservable(original_only=True)
        result = self.generate(new_only=True)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        self.assertEqual(result["mode"], "new-only")
        self.assertEqual(result["preservedCount"], len(prep.ORIGINAL_RECORD_IDS))
        self.assertEqual(result["generatedCount"], len(prep.RECORDS) - len(prep.ORIGINAL_RECORD_IDS))
        self.assertEqual(self.calls[1:], [f"{p[0]}-{p[1]}" for p in prep.RECORDS
                                         if f"{p[0]}-{p[1]}" not in prep.ORIGINAL_RECORD_IDS])
        self.assertEqual(result["modelAppliesToRecordIds"], self.calls[1:])
        self.assertEqual(len(result["generatedRecordParameters"]), result["generatedCount"])
        for item in result["preservedExisting"]:
            self.assertEqual(prep.sha256_file(self.out.parent / item["path"]), item["sha256"])
            self.assertEqual(item["recordParameters"]["durationSec"], 10)
        self.assertEqual(len(list(self.out.glob("*.json"))), len(prep.RECORDS))

    def test_new_only_preserves_previous_fourteen_and_only_attributes_new_model_to_additions(self):
        previous_ids = {"ludb-16", "ludb-1", "ludb-2", "ludb-3", "ludb-4", "ludb-5", "ludb-6",
                        "qtdb-sel100", "qtdb-sel103", "qtdb-sel114", "qtdb-sel116", "qtdb-sel117", "qtdb-sel123", "qtdb-sel213"}
        self.assertTrue(previous_ids.issubset({f"{p[0]}-{p[1]}" for p in prep.RECORDS}))
        previous = self.install_preservable(record_ids=previous_ids)
        result = self.generate(new_only=True)
        new_ids = [f"{p[0]}-{p[1]}" for p in prep.RECORDS if f"{p[0]}-{p[1]}" not in previous_ids]
        self.assertEqual(len(previous), 14)
        self.assertEqual({path: path.read_bytes() for path in previous}, previous)
        self.assertEqual(result["preservedCount"], 14)
        self.assertEqual(result["generatedCount"], len(new_ids))
        self.assertEqual(result["modelAppliesToRecordIds"], new_ids)
        if new_ids:
            self.assertEqual(self.calls, ["load", *new_ids])
        else:
            self.assertEqual(self.calls, [])
        self.assertEqual(len(result["generatedRecordParameters"]), len(new_ids))
        self.assertEqual({Path(item["path"]).stem for item in result["preservedExisting"]}, previous_ids)

    def test_new_only_rejects_missing_original_before_dependency_loading(self):
        self.install_preservable(original_only=True)
        path = self.out / f"{prep.ORIGINAL_RECORD_IDS[0]}.json"
        path.unlink()
        before = {item: item.read_bytes() for item in self.out.parent.rglob("*.json")}
        with self.assertRaisesRegex(FileNotFoundError, "original frozen record"):
            self.generate(new_only=True)
        self.assertEqual(self.calls, [])
        self.assertEqual({item: item.read_bytes() for item in before}, before)

    def test_new_only_rejects_partial_wrong_id_and_malformed_json_before_loading(self):
        for change in ("filtered", "metrics", "id", "malformed"):
            with self.subTest(change=change):
                self.install_preservable(original_only=True)
                path = self.out / f"{prep.ORIGINAL_RECORD_IDS[0]}.json"
                payload = json.loads(path.read_bytes())
                if change == "malformed":
                    path.write_text('{"id":', encoding="utf-8")
                else:
                    if change == "filtered":
                        payload.pop("filtered")
                    elif change == "metrics":
                        payload["metrics"].pop("averageHr")
                    else:
                        payload["id"] = "wrong-id"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                before = {item: item.read_bytes() for item in self.out.parent.rglob("*.json")}
                with self.assertRaisesRegex(ValueError, "Invalid existing frozen JSON"):
                    self.generate(new_only=True)
                self.assertEqual(self.calls, [])
                self.assertEqual({item: item.read_bytes() for item in before}, before)

    def test_new_only_complete_catalog_does_not_load_or_run_model(self):
        before = self.install_preservable()
        manifest_path = self.out.parent / "generation_manifest.json"
        manifest_before = manifest_path.read_bytes()
        result = self.generate(new_only=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(result["generatedCount"], 0)
        self.assertEqual(result["preservedCount"], len(prep.RECORDS))
        self.assertEqual(result["model"]["status"], "not-run")
        self.assertEqual(result["modelAppliesToRecordIds"], [])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(result["publicationPerformed"])
        self.assertEqual(manifest_path.read_bytes(), manifest_before)
        self.assertEqual(list(self.out.parent.glob(".prepare-demo-*")), [])

    def test_new_only_complete_catalog_without_manifest_does_not_invent_provenance(self):
        before = self.install_preservable()
        manifest_path = self.out.parent / "generation_manifest.json"
        manifest_path.unlink()
        result = self.generate(new_only=True)
        self.assertEqual(self.calls, [])
        self.assertFalse(result["publicationPerformed"])
        self.assertFalse(manifest_path.exists())
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_new_only_late_failure_preserves_originals_and_removes_new_records(self):
        originals = self.install_preservable(original_only=True)
        old_manifest = (self.out.parent / "generation_manifest.json").read_bytes()
        def fail_manifest(source, target):
            if Path(target).name == "generation_manifest.json":
                raise OSError("fake manifest disk failure")
            return prep.os.replace(source, target)
        with self.assertRaisesRegex(RuntimeError, "previous outputs restored"):
            self.generate(new_only=True, replace_file=fail_manifest)
        self.assertEqual({path: path.read_bytes() for path in originals}, originals)
        self.assertEqual(set(self.out.glob("*.json")), set(originals))
        self.assertEqual((self.out.parent / "generation_manifest.json").read_bytes(), old_manifest)

    def test_cli_passes_new_only_flag(self):
        result = {"recordCount": len(prep.RECORDS), "generatedCount": 10,
                  "preservedCount": 4, "model": {"status": "unknown"}}
        with patch.object(prep, "generate_demos", return_value=result) as generate:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(prep.main(["--new-only"]), 0)
        generate.assert_called_once_with(new_only=True)

    def test_cli_noop_distinguishes_verification_from_publication(self):
        result = {"recordCount": len(prep.RECORDS), "generatedCount": 0,
                  "preservedCount": len(prep.RECORDS), "publicationPerformed": False,
                  "model": {"status": "not-run"}}
        stdout = io.StringIO()
        with patch.object(prep, "generate_demos", return_value=result):
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(prep.main(["--new-only"]), 0)
        self.assertIn("No model was run", stdout.getvalue())
        self.assertIn("provenance, if present, were preserved", stdout.getvalue())
        self.assertNotIn("Published", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
