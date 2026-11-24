"""Windows executable metadata evaluated by the PyInstaller specification."""

from pathlib import Path
from runpy import run_path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

root = Path(__file__).resolve().parents[1]
version = run_path(str(root / "demucs_gui" / "version.py"))["VERSION"]
parts = (*map(int, version.split(".")), 0)
properties = {
    "CompanyName": "LiveTrack-X",
    "FileDescription": "Demucs Studio",
    "FileVersion": version,
    "InternalName": "DemucsStudio",
    "OriginalFilename": "DemucsStudio.exe",
    "ProductName": "Demucs Studio",
    "ProductVersion": version,
}
resource = VSVersionInfo(
    ffi=FixedFileInfo(filevers=parts, prodvers=parts),
    kids=[
        StringFileInfo([StringTable("041204b0", [StringStruct(k, v) for k, v in properties.items()])]),
        VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
    ],
)
