# 墨捕 OCR

一个使用 Python、PySide6 和 RapidOCR 开发的 Windows 本地截图文字识别工具。

## 当前功能

- 在鼠标所在屏幕拖拽框选截图区域
- 导入 PNG、JPG、BMP、WebP、TIFF 等本地图片识别文字
- 使用本地 ONNX 模型识别中英文文字
- 显示识别结果和平均置信度
- 识别后自动复制到剪贴板
- 自动检测 CPU、NVIDIA CUDA 和 DirectML，并允许用户切换
- GPU 不可用或初始化失败时自动回退 CPU
- 可自定义并保存 Windows 系统级截图快捷键，默认 `Ctrl+Shift+A`
- `Esc` 或右键取消截图

## 隐私说明

OCR 识别由 RapidOCR 的本地 ONNX 模型完成，不调用百度、腾讯等云端 OCR API，截图不会因识别功能被上传。首次安装依赖需要联网下载 Python 包；安装完成后，OCR 可以断网运行。

## 安装和运行

在项目目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

以后双击 `run.bat` 即可启动，也可以运行：

```powershell
.\.venv\Scripts\python.exe .\main.py
```

## CPU 与 GPU

默认安装使用 CPU，任何没有独立显卡的电脑都可以运行。如果程序只检测到 CPU，界面不会显示“推理设备”选项。

NVIDIA 显卡用户可选择安装 CUDA 运行库：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu_cuda.ps1
```

重启程序后，检测到 `CUDAExecutionProvider` 才会出现“CPU / NVIDIA GPU（CUDA）”选择框。GPU 依赖体积较大，因此不放入默认 CPU 安装包。选择的设备会被保存；GPU 初始化失败时，本次任务自动使用 CPU，并把选择恢复为 CPU。

## 工程结构

```text
main.py                         程序入口
assets/app-icon.ico             Windows 多尺寸应用图标
assets/app-icon.png             应用图标高清源文件
inksnip_ocr/capture_overlay.py  屏幕框选遮罩
inksnip_ocr/ocr_engine.py       本地 OCR 后台任务
inksnip_ocr/main_window.py      主窗口和交互流程
tests/                          自动化测试
```

## 当前范围

这是第一版最小可用工程。截图快捷键为系统级热键，软件失去焦点后仍可使用；下一阶段可加入托盘运行、多屏跨屏框选、截图预览和打包为独立 EXE。
