from pathlib import Path
import sys

import pytest

from demucs_gui import engine, media, updater
from demucs_gui.backend_i18n import ENGLISH, msg, translate_backend
from demucs_gui.config import Options
from demucs_gui.i18n import language, set_language


@pytest.fixture
def english():
    original = language()
    set_language("en")
    try:
        yield
    finally:
        set_language(original)


def test_localized_validation_and_model_errors_preserve_user_data(english):
    with pytest.raises(ValueError, match="Unsupported file format"):
        Options(audio_format="q").validate()
    with pytest.raises(ValueError, match="Unsupported model: 사용자 이름"):
        engine._stem_groups(Options(model="사용자 이름"))
    with pytest.raises(InterruptedError, match="Job canceled"):
        media._check_cancel(lambda: True)


def test_rerender_progress_and_diagnostics_in_both_languages(english):
    label = "GPU · 장치 이름"
    status = msg("{device} · 모델 준비 중", device=label)
    assert status == f"{label} · Loading model"
    assert translate_backend(status, "ko") == f"{label} · 모델 준비 중"
    assert translate_backend("모델 다운로드 90% · 123 MB (2/4)", "en") == "Downloading model: 90% · 123 MB (2/4)"
    detail = "test\nC:\\홍길동\\{name}.mp4"
    error = msg("미디어 정보를 읽을 수 없습니다. {detail}", detail=detail)
    assert error == "Could not read media information. " + detail
    assert translate_backend(error, "ko") == "미디어 정보를 읽을 수 없습니다. " + detail
    assert translate_backend(detail, "en") == detail
    for ko, en in ENGLISH.items():
        if "{" not in ko:
            assert translate_backend(ko, "en") == en
            assert translate_backend(en, "ko") == ko


@pytest.mark.skipif(sys.platform != "win32", reason="Windows installer")
@pytest.mark.parametrize(("code", "argument"), [("en", "/LANG=english"), ("ko", "/LANG=korean")])
def test_installer_inherits_selected_language(english, monkeypatch, tmp_path, code, argument):
    import ctypes
    from unittest.mock import Mock

    set_language(code)
    launch = Mock()
    monkeypatch.setattr(updater.subprocess, "Popen", launch)
    monkeypatch.setattr(ctypes.windll.kernel32, "SetDllDirectoryW", Mock())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    updater.launch_installer(Path("test.exe"))
    assert argument in launch.call_args.args[0]
