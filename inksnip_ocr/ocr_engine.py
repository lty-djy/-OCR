from __future__ import annotations

from dataclasses import dataclass, replace
import sys
from time import perf_counter
from typing import Any

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage, QPixmap


@dataclass(frozen=True)
class OcrOutput:
    text: str
    line_count: int
    average_confidence: float | None
    device_key: str = "cpu"
    device_label: str = "CPU"
    elapsed_seconds: float | None = None
    fallback_message: str | None = None


@dataclass(frozen=True)
class OcrDevice:
    key: str
    label: str


@dataclass(frozen=True)
class OcrRequest:
    image: np.ndarray
    device_key: str = "cpu"


CPU_DEVICE = OcrDevice("cpu", "CPU")
CUDA_DEVICE = OcrDevice("cuda", "NVIDIA GPU（CUDA）")
DML_DEVICE = OcrDevice("dml", "GPU（DirectML）")


def has_working_nvidia_device() -> bool:
    """检查 NVIDIA 驱动是否能初始化并且至少存在一块 CUDA 设备。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        cuda = ctypes.WinDLL("nvcuda.dll")
        if cuda.cuInit(0) != 0:
            return False
        count = ctypes.c_int(0)
        return cuda.cuDeviceGetCount(ctypes.byref(count)) == 0 and count.value > 0
    except (AttributeError, OSError):
        return False


def prepare_onnxruntime() -> list[str]:
    """加载 pip 安装的可选 NVIDIA DLL，并返回编译可用的执行后端。"""
    import onnxruntime as ort

    providers = list(ort.get_available_providers())
    preload = getattr(ort, "preload_dlls", None)
    if "CUDAExecutionProvider" in providers and callable(preload):
        # 空字符串表示从 nvidia-* site-packages 中查找 CUDA/cuDNN DLL。
        preload(directory="")
    return providers


def detect_available_devices(provider_names: list[str] | None = None) -> list[OcrDevice]:
    """返回真正由当前 ONNX Runtime 提供的设备，CPU 始终作为保底。"""
    if provider_names is None:
        try:
            provider_names = prepare_onnxruntime()
        except Exception:
            provider_names = []

    providers = set(provider_names)
    devices = [CPU_DEVICE]
    if "CUDAExecutionProvider" in providers and has_working_nvidia_device():
        devices.append(CUDA_DEVICE)
    if "DmlExecutionProvider" in providers:
        devices.append(DML_DEVICE)
    return devices


def device_by_key(key: str, devices: list[OcrDevice] | None = None) -> OcrDevice:
    candidates = devices if devices is not None else detect_available_devices()
    return next((device for device in candidates if device.key == key), CPU_DEVICE)


def extract_text_and_confidence(raw_result: Any) -> OcrOutput:
    if not raw_result:
        return OcrOutput("", 0, None)

    lines: list[str] = []
    scores: list[float] = []
    for item in raw_result:
        if not item or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        lines.append(text)
        if len(item) >= 3:
            try:
                scores.append(float(item[2]))
            except (TypeError, ValueError):
                pass

    confidence = sum(scores) / len(scores) if scores else None
    return OcrOutput("\n".join(lines), len(lines), confidence)


def pixmap_to_rgb_array(pixmap: QPixmap) -> np.ndarray:
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
    width = image.width()
    height = image.height()
    bytes_per_line = image.bytesPerLine()
    buffer = np.frombuffer(image.bits(), dtype=np.uint8, count=image.sizeInBytes())
    rows = buffer.reshape((height, bytes_per_line))
    return rows[:, : width * 3].reshape((height, width, 3)).copy()


class OcrWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._engine = None
        self._engine_device = ""

    @staticmethod
    def _engine_kwargs(device_key: str) -> dict[str, Any]:
        # max：只缩小过大的截图，不再把小截图强制放大到 736 像素。
        kwargs: dict[str, Any] = {
            "det_limit_type": "max",
            "det_limit_side_len": 960,
            "rec_batch_num": 16,
        }
        if device_key == "cuda":
            kwargs.update(
                det_use_cuda=True,
                cls_use_cuda=True,
                rec_use_cuda=True,
            )
        elif device_key == "dml":
            kwargs.update(
                det_use_dml=True,
                cls_use_dml=True,
                rec_use_dml=True,
            )
        return kwargs

    def _ensure_engine(self, device_key: str):
        if self._engine is not None and self._engine_device == device_key:
            return self._engine

        from rapidocr_onnxruntime import RapidOCR

        if device_key in {"cuda", "dml"}:
            prepare_onnxruntime()
        engine = RapidOCR(**self._engine_kwargs(device_key))
        self._verify_engine_device(engine, device_key)
        self._engine = engine
        self._engine_device = device_key
        return self._engine

    @staticmethod
    def _verify_engine_device(engine: Any, device_key: str) -> None:
        expected_provider = {
            "cuda": "CUDAExecutionProvider",
            "dml": "DmlExecutionProvider",
        }.get(device_key)
        if expected_provider is None:
            return

        # RapidOCR 1.x 的检测、分类和识别模块使用了两层不同的会话包装。
        sessions = [
            engine.text_det.infer.session,
            engine.text_cls.infer.session,
            engine.text_rec.session.session,
        ]
        actual = [list(session.get_providers()) for session in sessions]
        if any(not providers or providers[0] != expected_provider for providers in actual):
            raise RuntimeError(
                f"请求 {expected_provider}，但模型实际后端为 {actual}"
            )

    def _run(self, image: np.ndarray, device_key: str) -> OcrOutput:
        engine = self._ensure_engine(device_key)
        started = perf_counter()
        # 电脑截图通常为正向文字，关闭方向分类可以减少一次模型推理。
        raw_result, _elapsed = engine(image, use_cls=False)
        elapsed_seconds = perf_counter() - started
        device = device_by_key(device_key)
        return replace(
            extract_text_and_confidence(raw_result),
            device_key=device.key,
            device_label=device.label,
            elapsed_seconds=elapsed_seconds,
        )

    @Slot(object)
    def recognize(self, request: OcrRequest) -> None:
        requested_device = device_by_key(request.device_key)
        try:
            self.completed.emit(self._run(request.image, requested_device.key))
        except Exception as exc:  # 将后台异常安全地传回 GUI 线程
            if requested_device.key == "cpu":
                self.failed.emit(f"{type(exc).__name__}: {exc}")
                return

            # GPU 驱动或运行库可能在启动后仍初始化失败，此时保证任务可继续。
            gpu_error = f"{type(exc).__name__}: {exc}"
            self._engine = None
            self._engine_device = ""
            try:
                output = self._run(request.image, "cpu")
                self.completed.emit(
                    replace(
                        output,
                        fallback_message=(
                            f"{requested_device.label} 初始化失败，已自动切换到 CPU。"
                            f"错误：{gpu_error}"
                        ),
                    )
                )
            except Exception as cpu_exc:
                self.failed.emit(
                    f"GPU 失败：{gpu_error}\nCPU 回退失败："
                    f"{type(cpu_exc).__name__}: {cpu_exc}"
                )
