"""UI translations. Format arguments are user data and are never translated."""

_language = "ko"


def language():
    return _language


def set_language(code):
    global _language
    _language = code if code in ("en", "ko") else "ko"


def t(source, **fields):
    template = EN.get(source, source) if _language == "en" else source
    return template.format(**fields) if fields else template


EN = {
    "전체 스템 (각각 저장)": "All stems (separate files)",
    "보컬": "Vocals", "반주": "Instrumental", "드럼": "Drums", "베이스": "Bass",
    "그 외 악기": "Other instruments", "기타": "Guitar", "피아노": "Piano",
    "표준": "Standard", "빠른 분리": "Fast separation",
    "최고 품질": "Best quality", "정밀한 분리": "Cleanest stems",
    "6스템 모델": "6-stem model", "기타·피아노 추가": "Adds guitar & piano",
    "MDX 계열 모델": "MDX model family",
    "2스템": "2 stems", "4스템": "4 stems", "6스템": "6 stems",
    "보컬 · 반주": "Vocals, instrumental",
    "보컬 · 드럼 · 베이스 등": "Vocals, drums, bass, other",
    "기타 · 피아노 포함": "Includes guitar and piano",
    "무손실 PCM": "Lossless PCM", "손실 압축": "Lossy audio",
    "ADTS 스트림": "ADTS stream", "AAC 컨테이너": "AAC container",
    "무손실 압축": "Lossless audio", "MP4 컨테이너": "MP4 container",
    "Matroska 컨테이너": "Matroska container", "16-bit 무손실": "16-bit lossless",
    "24-bit 무손실": "24-bit lossless", "보컬만 추출": "Extract vocals",
    "반주만 추출": "Extract instrumental", "악기별 분리": "Separate instruments",
    "분리 · 내보내기 설정": "Separation & export", "프리셋 선택": "Select a preset",
    "적용": "Apply", "새로 저장": "Save as", "사용자 프리셋 관리": "Manage custom preset",
    "사용자 프리셋 이름 변경 또는 삭제": "Rename or delete this custom preset",
    "이름 변경": "Rename", "삭제": "Delete", "프리셋": "Preset", "모델": "Model",
    "분리할 스템": "Stems", "6스템을 선택하면 6스템 모델로 전환합니다.":
        "Selecting six stems switches to the six-stem model.",
    "저장할 스템": "Stems to export", "출력 형식": "Output format",
    "음원": "Audio", "영상": "Video",
    "원본 화면에 선택한 스템을 넣어 저장합니다.":
        "Export the original picture with the selected audio stem.",
    "저장 위치": "Save to", "원본 옆 separated 폴더": "A separated folder beside the source",
    "출력 폴더": "Output folder", "출력 폴더 선택": "Choose output folder",
    "고급 설정": "Advanced settings", "자동 (CUDA 우선)": "Auto (prefer CUDA)",
    "입력 위치를 바꿔 반복 계산합니다. 값이 크면 시간이 더 걸립니다.":
        "Run separation with shifted inputs. More shifts take longer.",
    "분리할 오디오 구간이 서로 겹치는 비율": "Fraction of overlap between audio segments",
    "모델 이름": "Model name", "장치": "Device", "비트 깊이": "Bit depth",
    "오디오 비트레이트": "Audio bitrate", "내 프리셋 · {name}": "My preset · {name}",
    "저장된 프리셋을 불러올 수 없습니다.": "Could not load the saved preset.",
    "취소": "Cancel", "사용자 프리셋": "Custom preset", "프리셋 이름": "Preset name",
    "저장": "Save", "프리셋 덮어쓰기": "Replace preset", "덮어쓰기": "Replace",
    "‘{name}’ 프리셋을 현재 설정으로 바꿀까요?": "Replace “{name}” with the current settings?",
    "기존 ‘{name}’ 프리셋을 바꿀까요?": "Replace the existing preset “{name}”?",
    "프리셋 삭제": "Delete preset", "‘{name}’ 프리셋을 삭제할까요?": "Delete the preset “{name}”?",
    "미리듣기": "Preview", "결과 폴더": "Results folder", "재생": "Play",
    "재생 위치": "Playback position", "일시 정지": "Pause",
    "미리듣기 오류 · {detail}": "Preview error · {detail}",
    "원본": "Original", "파일 선택": "Select a file",
    "Demucs Studio · 음원 분리": "Demucs Studio · Audio separation",
    "음원 분리 작업실": "Audio separation", "로컬 처리": "On-device",
    "작업 대기열": "Job queue", "다시 대기": "Requeue", "제거": "Remove", "비우기": "Clear",
    "영상·음원 파일을 여기에 놓으세요": "Drop video or audio files here",
    "MP4 · MKV · WAV · FLAC · MP3 외": "MP4 · MKV · WAV · FLAC · MP3 and more",
    "파일 추가": "Add files", "파일 추가 (Ctrl+O)": "Add files (Ctrl+O)",
    "파일 이름": "File name", "길이": "Length", "상태": "Status", "진행률": "Progress",
    "배치 작업 대기열": "Batch job queue", "대기열에서 제거": "Remove from queue",
    "작업 대기 중": "Ready", "경과 00:00   ·   남은 시간 —": "Elapsed 00:00   ·   Remaining —",
    "작업 기록": "Job log", "현재 파일 취소 · 다음 파일 계속": "Cancel this file and continue",
    "현재 파일 취소 · 전체 중지": "Cancel this file and stop the batch",
    "현재 파일 또는 전체 작업 취소": "Cancel this file or the entire batch",
    "분리 시작": "Start separation", "전체 작업 진행률": "Batch progress",
    "영상·음원 파일 추가": "Add video or audio files",
    "영상·음원 ({extensions});;모든 파일 (*)": "Video and audio ({extensions});;All files (*)",
    "{name} 진행률": "Progress for {name}", "지원하지 않는 파일 · {files}": "Unsupported files · {files}",
    "선택 파일 다시 대기": "Requeue selected files",
    "대기": "Queued", "실패": "Failed", "완료": "Completed", "처리 중": "Processing",
    "취소됨": "Cancelled", "시작 중": "Starting",
    "분리 시작 · {count}개 · {model} · {format} · {quality}":
        "Started · {count} file(s) · {model} · {format} · {quality}",
    "{name} · 처리 시작": "{name} · Started",
    "계산 중": "Estimating",
    "전체 {progress}   ·   경과 {elapsed}   ·   예상 남은 시간 {remaining}":
        "Overall {progress}   ·   Elapsed {elapsed}   ·   Remaining {remaining}",
    "취소 중…": "Cancelling…", "전체 작업 중지 요청": "Batch cancellation requested",
    "현재 파일 취소 요청": "File cancellation requested", "경과 {elapsed}": "Elapsed {elapsed}",
    "{status} {count}개": "{status} {count}", "작업 종료": "Close application",
    "처리 중인 파일을 취소하고 앱을 닫을까요?": "Cancel the current file and close the application?",
    "취소 후 종료": "Cancel and close", "계속 처리": "Keep processing",
    "표시 언어": "Display language", "작업이 끝난 후 언어를 변경할 수 있습니다.":
        "You can change the language when the current operation finishes.",
    "분리 장치 선택": "Select processing device",
    "확인 중…": "Checking…", "확인 실패": "Detection failed", "CPU (자동)": "CPU (auto)",
    "CUDA GPU 사용 불가": "CUDA GPU unavailable", "분리 장치 · {device}": "Device · {device}",
    "보컬·악기 분리에 사용할 장치입니다. 고급 설정에서 변경할 수 있습니다.":
        "Device used to separate vocals and instruments. Change it in Advanced settings.",
}
