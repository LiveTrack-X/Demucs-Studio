import hashlib
import io
import json

import pytest

from demucs_gui import updater


def release(tag="v1.1.0", filenames=None):
    assets = []
    for name in filenames or ["DemucsStudio-Setup-x64.exe"]:
        assets.append({"name": name, "state": "uploaded", "size": 5,
                       "digest": "sha256:" + hashlib.sha256(b"setup").hexdigest(),
                       "browser_download_url": f"{updater.REPO_URL}/releases/download/{tag}/{name}"})
    return {"tag_name": tag, "assets": assets}


def setup_response(monkeypatch, tmp_path, metadata, payload=b"setup"):
    monkeypatch.setattr(updater, "_cache_root", lambda: tmp_path)
    monkeypatch.setattr(updater, "_request",
                        lambda url, _: io.BytesIO(json.dumps(metadata).encode() if url == updater.LATEST else payload))


def test_new_version_downloads_and_verifies_all_parts(monkeypatch, tmp_path):
    data = release("v1.10.0", ["DemucsStudio-Setup-x64.exe", "DemucsStudio-Setup-x64-1.bin"])
    setup_response(monkeypatch, tmp_path, data)
    version = updater.check_update("1.9.9")
    assert version.version == "1.10.0" and version.size == 10
    assert updater.check_update("1.10.0") is None
    calls = []
    installer = updater.download_install(version, lambda v, _: calls.append(v), lambda: False)
    assert calls == [0.5, 1.0]
    assert installer.read_bytes() == installer.with_name("DemucsStudio-Setup-x64-1.bin").read_bytes() == b"setup"
    updater.prune_installed_downloads("1.10.0")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("condition", ["cancelled", "truncated", "corrupt"])
def test_failed_download_removes_partial_installer(monkeypatch, tmp_path, condition):
    body = {"cancelled": b"setup", "truncated": b"a", "corrupt": b"wrong"}[condition]
    setup_response(monkeypatch, tmp_path, release(), body)
    info = updater.check_update("1.0.0")
    with pytest.raises((ValueError, InterruptedError)):
        updater.download_install(info, lambda *_: None, lambda: condition == "cancelled")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("change", ["url", "digest", "missing_part"])
def test_invalid_release_assets_are_rejected(monkeypatch, tmp_path, change):
    data = release()
    if change == "url":
        data["assets"][0]["browser_download_url"] = "https://example.org/foreign.exe"
    if change == "digest":
        data["assets"][0]["digest"] = None
    if change == "missing_part":
        data = release(filenames=["DemucsStudio-Setup-x64.exe", "DemucsStudio-Setup-x64-2.bin"])
    setup_response(monkeypatch, tmp_path, data)
    with pytest.raises(ValueError):
        updater.check_update("1.0.0")
