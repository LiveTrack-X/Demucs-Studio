from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from . import engine, media, stem_mix
from .backend_i18n import msg
from .config import Options, STEMS


def process_file(
    source: Path,
    options: Options,
    progress: Callable[[float, str], None],
    cancelled: Callable[[], bool],
) -> dict[str, Path]:
    """Publish a complete set of exports together. A retry gets its own directory."""
    def check_cancel() -> None:
        if cancelled():
            raise InterruptedError(msg("작업을 취소했습니다."))

    def stage(start: float, size: float):
        def report(value: float, label: str) -> None:
            check_cancel()
            progress(start + size * max(0.0, min(value, 1.0)), label)
        return report

    options = replace(options)
    options.validate()
    source = Path(source).resolve(strict=True)
    check_cancel()
    progress(0.0, msg("미디어 정보 확인"))
    info = media.probe(source)
    if options.output_kind == "video" and not info.has_video:
        raise ValueError(msg("영상 출력에는 화면이 있는 원본 파일이 필요합니다. 음원 출력을 선택해 주세요."))

    base = Path(options.output_dir).expanduser() if options.output_dir.strip() else source.parent / "separated"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".demucs-", dir=base) as temp:
        work = Path(temp)
        mix = work / "input.wav"
        requested = ("vocals",) if options.vocals_only else STEMS[options.stem_mode]
        if options.selected_stem != "all":
            requested = (options.selected_stem,)
        strength = options.separation_strength
        reduction = options.bleed_reduction_db
        render = strength > 0 and (strength < 100 or reduction > 0)
        decode_end = 0.07 if strength else 0.35
        info = media.decode(source, mix, info, stage(0.0, decode_end), cancelled)
        check_cancel()
        if strength:
            stem_dir = work / "stems"
            stem_dir.mkdir()
            export_start = 0.80 if render else 0.87
            stems = engine.separate(mix, stem_dir, options, stage(decode_end, export_start - decode_end), cancelled)
            if not render:
                mix.unlink()
        else:
            export_start = decode_end
            stems = dict.fromkeys(requested, mix)
        ready = work / "export"
        ready.mkdir()
        names = {}
        for index, name in enumerate(requested):
            check_cancel()
            names[name] = f"{source.stem}_{name}.{options.format}"
            size = (1 - export_start) / len(requested)
            start = export_start + size * index
            render_size = size * 0.5 if render else 0
            if render:
                stem_mix.apply_in_place(mix, stems[name], strength, reduction,
                                        stage(start, render_size), cancelled)
                if index == len(requested) - 1:
                    mix.unlink()
            report = stage(start + render_size, size - render_size)
            media.export(source, stems[name], ready / names[name], info, options, report, cancelled)
            if strength:
                stems[name].unlink()
        check_cancel()
        number = 1
        while True:
            target = base / (source.stem if number == 1 else f"{source.stem} ({number})")
            if not target.exists():
                try:
                    ready.rename(target)
                    break
                except FileExistsError:
                    pass  # Another instance finished the same source between check and rename.
            number += 1
    progress(1.0, msg("저장 완료"))
    return {name: target / filename for name, filename in names.items()}
