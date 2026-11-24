"""Consume stable Windows installers published by the application's GitHub repository."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .backend_i18n import msg
from .i18n import language
from .version import REPO_URL, VERSION


LATEST = "https://api.github.com/repos/LiveTrack-X/Demucs-Studio/releases/latest"
SETUP = "DemucsStudio-Setup-x64"
VERSION_PATTERN = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SLICE_PATTERN = re.compile(re.escape(SETUP) + r"-([1-9][0-9]*)\.bin")


@dataclass(frozen=True)
class Asset:
    name: str
    size: int
    sha256: str
    url: str


@dataclass(frozen=True)
class Release:
    version: str
    page_url: str
    assets: tuple[Asset, ...]

    @property
    def size(self):
        return sum(asset.size for asset in self.assets)


def _version(text):
    match = VERSION_PATTERN.fullmatch(text)
    return tuple(map(int, match.groups())) if match else None


def _request(url, accept):
    req = Request(url, headers={"User-Agent": f"DemucsStudio/{VERSION}", "Accept": accept})
    return urlopen(req, timeout=20)


def check_update(current_version=VERSION):
    prune_installed_downloads(current_version)
    try:
        with _request(LATEST, "application/vnd.github+json") as response:
            raw = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None  # A newly created repository may have no published releases yet.
        raise
    tag = raw.get("tag_name", "")
    version = _version(tag)
    if not version or version <= _version(current_version) or raw.get("draft") or raw.get("prerelease"):
        return None
    exe = SETUP + ".exe"
    assets = []
    parts = []
    for item in raw.get("assets", []):
        name = item["name"]
        part = SLICE_PATTERN.fullmatch(name)
        if name != exe and not part:
            continue
        expected_url = f"{REPO_URL}/releases/download/{tag}/{name}"
        digest = item.get("digest") or ""
        if (item.get("state") != "uploaded" or item.get("browser_download_url") != expected_url
                or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                or not isinstance(item["size"], int) or item["size"] <= 0):
            raise ValueError(msg("GitHub에서 업데이트 파일의 크기 또는 SHA-256을 확인할 수 없습니다."))
        if part:
            parts.append(int(part[1]))
        assets.append(Asset(name, item["size"], digest[7:].lower(), expected_url))
    if not assets:
        return None
    if sum(a.name == exe for a in assets) != 1 or sorted(parts) != list(range(1, len(parts) + 1)):
        raise ValueError(msg("릴리즈 설치 파일 구성이 올바르지 않습니다."))
    return Release(tag.removeprefix("v"), f"{REPO_URL}/releases/tag/{tag}", tuple(assets))


def _cache_root():
    return Path(tempfile.gettempdir()) / "LiveTrack-DemucsStudio-Updates"


def _discard(folder):
    # The uninstaller and the user can place other files here. Remove only ours.
    for file in folder.iterdir():
        if file.is_file() and (file.name == SETUP + ".exe" or SLICE_PATTERN.fullmatch(file.name)):
            file.unlink(missing_ok=True)
    if not any(folder.iterdir()):
        folder.rmdir()


def discard_download(path):
    path = Path(path)
    folder = path.parent
    if (path.name == SETUP + ".exe" and folder.parent == _cache_root()
            and _version(folder.name.partition("_")[0]) and folder.is_dir() and not folder.is_symlink()):
        _discard(folder)


def prune_installed_downloads(current_version):
    root = _cache_root()
    if not root.is_dir():
        return
    for folder in root.iterdir():
        version = _version(folder.name.partition("_")[0])
        if folder.is_dir() and not folder.is_symlink() and version and version <= _version(current_version):
            try:
                _discard(folder)
            except OSError:
                pass  # Running installers on Windows hold their files open until exit.


def download_install(release, progress, cancelled):
    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"v{release.version}_", dir=root))
    downloaded = 0
    total = release.size
    try:
        for asset in release.assets:
            if cancelled():
                raise InterruptedError(msg("업데이트 다운로드를 취소했습니다."))
            digest = hashlib.sha256()
            size = 0
            dest = folder / asset.name
            with _request(asset.url, "application/octet-stream") as response, dest.open("xb") as out:
                while data := response.read(1024 * 1024):
                    if cancelled():
                        raise InterruptedError(msg("업데이트 다운로드를 취소했습니다."))
                    size += len(data)
                    if size > asset.size:
                        raise ValueError(msg("업데이트 파일이 공개된 크기보다 큽니다."))
                    out.write(data)
                    digest.update(data)
                    downloaded += len(data)
                    progress(downloaded / total, f"{downloaded / 2**20:.0f} / {total / 2**20:.0f} MB")
            if size != asset.size or digest.hexdigest() != asset.sha256:
                raise ValueError(msg("업데이트 파일의 SHA-256 또는 크기가 일치하지 않습니다. 다시 시도해 주세요."))
        if cancelled():
            raise InterruptedError(msg("업데이트 다운로드를 취소했습니다."))
        return folder / (SETUP + ".exe")
    except BaseException:
        _discard(folder)
        raise


def launch_installer(path: Path):
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        raise RuntimeError(msg("설치된 Windows 앱에서 업데이트를 적용할 수 있습니다."))
    import ctypes
    install_dir = Path(sys.executable).resolve().parent
    setup_language = "english" if language() == "en" else "korean"
    # A child inherits PyInstaller's DLL search path. Give Windows Setup its normal environment.
    ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        subprocess.Popen([str(path), "/SP-", "/SILENT", "/NORESTART", "/RELAUNCH=1",
                          f"/DIR={install_dir}", f"/LANG={setup_language}"], cwd=path.parent, close_fds=True)
    finally:
        ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))
