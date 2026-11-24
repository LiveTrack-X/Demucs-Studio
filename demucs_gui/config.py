"""Shared job settings for separation, encoding, and the desktop window."""

from dataclasses import dataclass


_BITRATES = [(str(value), f"{value} kbps") for value in (128, 192, 256, 320)]
QUALITY_OPTIONS = {
    "wav": [("16", "16-bit PCM"), ("24", "24-bit PCM"), ("32f", "32-bit float")],
    "flac": [("16", "16-bit 무손실"), ("24", "24-bit 무손실")],
    **{fmt: _BITRATES.copy() for fmt in ("mp3", "aac", "m4a", "mp4", "mkv")},
}
STEMS = {
    "2": ("vocals", "accompaniment"),
    "4": ("vocals", "drums", "bass", "other"),
    "6": ("vocals", "drums", "bass", "other", "guitar", "piano"),
}
MODELS = ("htdemucs_ft", "htdemucs", "htdemucs_6s", "mdx_extra")


@dataclass
class Options:
    model: str = "htdemucs_ft"
    stem_mode: str = "2"
    vocals_only: bool = False
    shifts: int = 1
    overlap: float = 0.25
    device: str = "auto"
    output_kind: str = "audio"
    audio_format: str = "wav"
    video_format: str = "mp4"
    quality: str = "24"
    output_dir: str = ""
    selected_stem: str = "all"

    @property
    def format(self) -> str:
        return self.video_format if self.output_kind == "video" else self.audio_format

    def validate(self) -> None:
        if self.model not in MODELS or self.stem_mode not in STEMS:
            raise ValueError("분리 모델과 스템 구성을 다시 선택해 주세요.")
        if self.stem_mode == "6" and self.model != "htdemucs_6s":
            raise ValueError("6스템 분리에는 htdemucs_6s 모델이 필요합니다.")
        if self.selected_stem != "all" and self.selected_stem not in STEMS[self.stem_mode]:
            raise ValueError("선택한 스템이 현재 분리 모드에 없습니다.")
        if self.vocals_only and self.selected_stem not in ("all", "vocals"):
            raise ValueError("보컬만 저장할 때는 보컬 스템을 선택해 주세요.")
        if self.device not in ("auto", "cuda", "cpu"):
            raise ValueError("연산 장치를 다시 선택해 주세요.")
        if not 0 <= self.shifts <= 10 or not 0 <= self.overlap <= 0.99:
            raise ValueError("Shifts 또는 Overlap 값이 범위를 벗어났습니다.")
        if self.output_kind not in ("audio", "video"):
            raise ValueError("내보낼 파일 유형을 선택해 주세요.")
        if self.video_format not in ("mp4", "mkv") or self.audio_format not in ("wav", "flac", "mp3", "aac", "m4a"):
            raise ValueError("지원하지 않는 파일 형식입니다.")
        if self.quality not in dict(QUALITY_OPTIONS[self.format]):
            raise ValueError("현재 형식에 맞는 음질을 선택해 주세요.")
