$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir

$pythonExe = '.\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Run setup.ps1 before installing the optional GPU runtime.'
}

# CPU and GPU wheels provide the same onnxruntime Python module and must not coexist.
& $pythonExe -m pip uninstall -y onnxruntime onnxruntime-directml onnxruntime-gpu
& $pythonExe -m pip install 'onnxruntime-gpu[cuda,cudnn]==1.28.0'
& $pythonExe -c "import onnxruntime as ort; ort.preload_dlls(directory=''); from rapidocr_onnxruntime import RapidOCR; engine=RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True); print('Available:', ort.get_available_providers()); print('Detector:', engine.text_det.infer.session.get_providers()); print('Classifier:', engine.text_cls.infer.session.get_providers()); print('Recognizer:', engine.text_rec.session.session.get_providers())"

Write-Host ''
Write-Host 'CUDA runtime setup complete. Restart InkSnip OCR.' -ForegroundColor Green
