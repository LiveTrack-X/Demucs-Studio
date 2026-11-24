"""Bilingual processing and updater messages. Values supplied by users stay verbatim."""

import re
from string import Formatter

from .i18n import language


ENGLISH = {
    "분리를 취소했습니다.": "Separation canceled.",
    "지원하지 않는 모델입니다. {model}": "Unsupported model: {model}",
    "선택한 모델과 스템 수의 조합을 지원하지 않습니다.": "The selected model does not support this number of stems.",
    "현재 설정에서 저장할 수 없는 스템입니다. {stem}": "These settings do not support exporting the {stem} stem.",
    "모델 다운로드 연결 중": "Connecting to the model download server",
    "모델 다운로드 {amount}": "Downloading model: {amount}",
    "다운로드한 모델의 체크섬이 일치하지 않습니다. {filename}": "Downloaded model checksum mismatch: {filename}",
    "모델 확인 중": "Checking model",
    "모델의 스템 구성 또는 오디오 규격이 예상과 다릅니다.": "The model returned an unexpected stem layout or audio format.",
    "오디오 레벨 분석 중": "Analyzing audio levels",
    "입력 오디오에 유효하지 않은 샘플이 있습니다.": "The input audio contains invalid samples.",
    "디코딩된 오디오의 샘플 수가 헤더와 다릅니다.": "The decoded sample count does not match the audio header.",
    "모델 출력의 샘플 수 또는 값이 올바르지 않습니다.": "The model returned an invalid sample count or sample value.",
    "Shifts 또는 Overlap이 지원 범위를 벗어났습니다.": "Shifts or overlap is outside the supported range.",
    "CUDA GPU를 사용할 수 없습니다. 자동 또는 CPU를 선택해 주세요.": "CUDA is unavailable. Choose Auto or CPU.",
    "지원하지 않는 장치입니다. {device}": "Unsupported device: {device}",
    "{device} · 모델 준비 중": "{device} · Loading model",
    "44.1 kHz 스테레오 PCM 입력이 필요합니다.": "The input must be 44.1 kHz stereo PCM.",
    "{device} · 스템 분리 중": "{device} · Separating stems",
    "완성된 스템의 샘플 수가 입력과 다릅니다.": "The exported stem sample count does not match the input.",
    "작업을 취소했습니다.": "Job canceled.",
    "미디어 정보 확인": "Reading media information",
    "영상 출력에는 화면이 있는 원본 파일이 필요합니다. 음원 출력을 선택해 주세요.":
        "Video export requires a source video track. Choose audio export for this file.",
    "저장 완료": "Export complete",
    "{filename} 파일을 찾을 수 없습니다. 설치 폴더의 bin 폴더를 확인해 주세요.":
        "Could not find {filename}. Check the bin folder in the installation directory.",
    "미디어 정보를 읽을 수 없습니다. {detail}": "Could not read media information. {detail}",
    "입력 파일에 분리할 오디오 트랙이 없습니다.": "The input file has no audio track to separate.",
    "FFmpeg 변환 실패": "FFmpeg conversion failed",
    "오디오 읽는 중": "Reading audio",
    "원본 샘플레이트로 음원 저장 중": "Saving audio at the original sample rate",
    "원본과 분리 음원의 샘플 길이가 일치하지 않습니다.": "The input and separated audio have different sample counts.",
    "원본 타임라인의 샘플 위치를 재구성하지 못했습니다.": "Could not reconstruct sample positions on the original timeline.",
    "출력 형식에 맞는 음질을 선택해 주세요.": "Choose a quality supported by the export format.",
    "음원 저장 중": "Saving audio",
    "원본 파일에 화면이 없습니다. 음원 출력을 선택해 주세요.": "The source has no video track. Choose audio export.",
    "원본 화면과 분리 음원 저장 중": "Saving the original video with the separated audio",
    "호환 영상으로 변환 중 (H.264)": "Converting video to H.264 for compatibility",
    "16-bit 무손실": "16-bit lossless",
    "24-bit 무손실": "24-bit lossless",
    "분리 모델과 스템 구성을 다시 선택해 주세요.": "Choose a valid model and stem configuration.",
    "6스템 분리에는 htdemucs_6s 모델이 필요합니다.": "Six-stem separation requires the htdemucs_6s model.",
    "선택한 스템이 현재 분리 모드에 없습니다.": "This stem is unavailable in the current separation mode.",
    "보컬만 저장할 때는 보컬 스템을 선택해 주세요.": "Select the vocals stem when exporting vocals only.",
    "연산 장치를 다시 선택해 주세요.": "Choose a supported processing device.",
    "Shifts 또는 Overlap 값이 범위를 벗어났습니다.": "Shifts or overlap is out of range.",
    "내보낼 파일 유형을 선택해 주세요.": "Choose an export file type.",
    "지원하지 않는 파일 형식입니다.": "Unsupported file format.",
    "현재 형식에 맞는 음질을 선택해 주세요.": "Choose a quality supported by the selected format.",
    "GitHub에서 업데이트 파일의 크기 또는 SHA-256을 확인할 수 없습니다.":
        "Could not verify the update size or SHA-256 digest on GitHub.",
    "릴리즈 설치 파일 구성이 올바르지 않습니다.": "The release is missing required installer files.",
    "업데이트 다운로드를 취소했습니다.": "Update download canceled.",
    "업데이트 파일이 공개된 크기보다 큽니다.": "The update file exceeds its published size.",
    "업데이트 파일의 SHA-256 또는 크기가 일치하지 않습니다. 다시 시도해 주세요.":
        "The update file does not match the published SHA-256 or size. Please try again.",
    "설치된 Windows 앱에서 업데이트를 적용할 수 있습니다.": "Install updates from the packaged Windows app.",
    "GitHub 프로젝트 열기 · 오른쪽 클릭으로 업데이트 확인": "Open the GitHub project · Right-click to check for updates",
    "업데이트 확인": "Check for updates",
    "업데이트 확인 실패": "Could not check for updates",
    "v{version} 업데이트": "Update to v{version}",
    "v{version}을 사용할 수 있습니다. Update 버튼을 눌러 주세요.": "v{version} is available. Select Update to continue.",
    "현재 사용할 수 있는 새 버전이 없습니다.": "No new version is available.",
    "업데이트": "Update",
    "분리 작업을 마친 후 업데이트해 주세요.": "Finish the current separation before updating.",
    "업데이트 설치": "Install update",
    "v{version} ({size} MB)을 설치할까요?\n다운로드와 무결성 확인이 끝나면 앱을 닫고 설치 프로그램을 실행합니다.":
        "Install v{version} ({size} MB)?\nThe app will close and launch the installer after verifying the download.",
    "업데이트 준비 중…": "Preparing update…",
    "취소": "Cancel",
    "분리 작업이 진행 중입니다. 작업을 마친 후 다시 업데이트해 주세요.":
        "A separation is in progress. Try updating after it finishes.",
    "업데이트 파일 정리 실패": "Could not remove update files",
    "업데이트 실패": "Update failed",
    "다운로드를 취소한 후 닫는 중…": "Canceling the download before closing…",
}


def msg(template: str, **fields) -> str:
    selected = ENGLISH[template] if language() == "en" else template
    return selected.format_map(fields) if fields else selected


def _pattern(template):
    parts = []
    for literal, field, _, _ in Formatter().parse(template):
        parts.append(re.escape(literal))
        if field:
            parts.append(f"(?P<{field}>.*?)")
    return re.compile("".join(parts), re.DOTALL)


# Qt signals keep text rather than the formatting arguments. Restore only known
# message shapes when re-rendering an earlier progress or error in a new language.
_STATIC = {
    "en": {ko: en for ko, en in ENGLISH.items() if "{" not in ko},
    "ko": {en: ko for ko, en in ENGLISH.items() if "{" not in ko},
}
_FORMATTED = {
    "en": [(_pattern(ko), en) for ko, en in ENGLISH.items() if "{" in ko],
    "ko": [(_pattern(en), ko) for ko, en in ENGLISH.items() if "{" in ko],
}


def translate_backend(text: str, language: str) -> str:
    """Translate a complete backend message, preserving paths and diagnostic details."""
    if text in _STATIC[language]:
        return _STATIC[language][text]
    # The model loader appends its ensemble position to each sub-step.
    numbered = re.fullmatch(r"(.+) (\(\d+/\d+\))", text)
    if numbered:
        return f"{translate_backend(numbered[1], language)} {numbered[2]}"
    for pattern, target in _FORMATTED[language]:
        match = pattern.fullmatch(text)
        if match:
            return target.format_map(match.groupdict())
    return text
