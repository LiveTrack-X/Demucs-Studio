# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from runpy import run_path
from shutil import which
from PyInstaller.utils.hooks import collect_data_files, copy_metadata


tools = []
notices = []
for name in ("ffmpeg", "ffprobe"):
    path = which(name)
    if not path:
        raise SystemExit(f"{name}.exe is required on PATH to create the portable build.")
    tools.append((path, "bin"))
    if name == "ffmpeg":
        for filename in ("LICENSE", "README.txt"):
            notice = Path(path).parent.parent / filename
            if notice.is_file():
                notices.append((str(notice), "licenses/ffmpeg"))

data = collect_data_files("demucs", includes=["remote/*"]) + notices
data += [("licenses/qt/*.txt", "licenses/qt"), ("THIRD_PARTY.md", "licenses")]
data += collect_data_files("_soundfile_data", includes=["COPYING"])
for package in ("demucs", "PySide6", "scipy", "soundfile"):
    data += copy_metadata(package, recursive=True)

a = Analysis(
    ["app.py"],
    binaries=tools,
    datas=data,
    hiddenimports=[
        "demucs.htdemucs", "demucs.hdemucs", "demucs.demucs", "demucs.pretrained",
        "PySide6.QtWidgets", "PySide6.QtMultimedia", "scipy.signal", "soundfile",
    ],
    excludes=["IPython", "pytest", "matplotlib", "tensorboard", "torch.testing._internal"],
    module_collection_mode={"einops": "pyz+py", "torchaudio": "pyz+py"},
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="DemucsStudio",
    debug=False, strip=False, upx=False, console=False, icon="DemucsStudio.ico",
    version=run_path("packaging/version_resource.py")["resource"],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DemucsStudio")
