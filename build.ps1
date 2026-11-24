param([ValidateSet("cu124", "cpu")] [string]$TorchBuild = "cu124")
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    # The CPU and CUDA wheels share a public version number. Pin the local tag
    # so rebuilding with a different switch changes the installed wheel.
    if (!(Test-Path ".venv/Scripts/python.exe")) {
        py -3.11 -m venv .venv
        if ($LASTEXITCODE) { throw "Python 3.11 venv creation failed." }
    }
    $python = (Resolve-Path ".venv/Scripts/python.exe").Path
    & $python -m ensurepip --upgrade
    if ($LASTEXITCODE) { throw "pip setup failed." }
    & $python -m pip install "torch==2.5.1+$TorchBuild" "torchaudio==2.5.1+$TorchBuild" --index-url "https://download.pytorch.org/whl/$TorchBuild"
    if ($LASTEXITCODE) { throw "PyTorch installation failed." }
    & $python -m pip install -r requirements.txt "pyinstaller==6.16.0"
    if ($LASTEXITCODE) { throw "Application dependency installation failed." }
    & $python -m PyInstaller --noconfirm DemucsStudio.spec
    if ($LASTEXITCODE) { throw "Application build failed." }
} finally {
    Pop-Location
}
