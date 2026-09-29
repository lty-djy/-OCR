from __future__ import annotations

import unittest
from types import SimpleNamespace

from PySide6.QtGui import QKeySequence

from inksnip_ocr.global_hotkey import (
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    sequence_to_windows_hotkey,
)
from inksnip_ocr.ocr_engine import (
    OcrWorker,
    detect_available_devices,
    extract_text_and_confidence,
)


class ExtractTextTests(unittest.TestCase):
    def test_empty_result(self) -> None:
        output = extract_text_and_confidence(None)
        self.assertEqual(output.text, "")
        self.assertEqual(output.line_count, 0)
        self.assertIsNone(output.average_confidence)

    def test_lines_and_confidence(self) -> None:
        output = extract_text_and_confidence(
            [
                [[[0, 0], [10, 0], [10, 10], [0, 10]], "第一行", 0.8],
                [[[0, 12], [10, 12], [10, 22], [0, 22]], "第二行", 1.0],
            ]
        )
        self.assertEqual(output.text, "第一行\n第二行")
        self.assertEqual(output.line_count, 2)
        self.assertAlmostEqual(output.average_confidence or 0, 0.9)


class DeviceDetectionTests(unittest.TestCase):
    def test_cpu_is_always_available(self) -> None:
        devices = detect_available_devices([])
        self.assertEqual([device.key for device in devices], ["cpu"])

    def test_cuda_and_dml_are_exposed_only_when_available(self) -> None:
        devices = detect_available_devices(
            ["CPUExecutionProvider", "CUDAExecutionProvider", "DmlExecutionProvider"]
        )
        self.assertEqual([device.key for device in devices], ["cpu", "cuda", "dml"])

    def test_unrelated_provider_is_not_shown_as_local_gpu(self) -> None:
        devices = detect_available_devices(
            ["AzureExecutionProvider", "CPUExecutionProvider"]
        )
        self.assertEqual([device.key for device in devices], ["cpu"])

    def test_cuda_switch_enables_all_three_models(self) -> None:
        kwargs = OcrWorker._engine_kwargs("cuda")
        self.assertTrue(kwargs["det_use_cuda"])
        self.assertTrue(kwargs["cls_use_cuda"])
        self.assertTrue(kwargs["rec_use_cuda"])

    def test_cpu_switch_does_not_request_gpu(self) -> None:
        kwargs = OcrWorker._engine_kwargs("cpu")
        self.assertNotIn("det_use_cuda", kwargs)
        self.assertNotIn("det_use_dml", kwargs)

    def test_silent_gpu_fallback_is_rejected(self) -> None:
        class FakeSession:
            def get_providers(self):
                return ["CPUExecutionProvider"]

        session = FakeSession()
        engine = SimpleNamespace(
            text_det=SimpleNamespace(infer=SimpleNamespace(session=session)),
            text_cls=SimpleNamespace(infer=SimpleNamespace(session=session)),
            text_rec=SimpleNamespace(session=SimpleNamespace(session=session)),
        )
        with self.assertRaises(RuntimeError):
            OcrWorker._verify_engine_device(engine, "cuda")


class GlobalHotkeyTests(unittest.TestCase):
    def test_ctrl_shift_a_mapping(self) -> None:
        modifiers, virtual_key = sequence_to_windows_hotkey(
            QKeySequence("Ctrl+Shift+A")
        )
        self.assertEqual(virtual_key, ord("A"))
        self.assertTrue(modifiers & MOD_CONTROL)
        self.assertTrue(modifiers & MOD_SHIFT)
        self.assertTrue(modifiers & MOD_NOREPEAT)

    def test_function_key_mapping(self) -> None:
        _modifiers, virtual_key = sequence_to_windows_hotkey(QKeySequence("Alt+F8"))
        self.assertEqual(virtual_key, 0x77)


if __name__ == "__main__":
    unittest.main()
