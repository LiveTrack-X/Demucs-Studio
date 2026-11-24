# Third-party software

Demucs Studio is a Windows interface by LiveTrack. The following projects provide its separation engine and media runtime.

| Component | Source and information |
|---|---|
| Demucs 4.0.1 | [Published package](https://pypi.org/project/demucs/4.0.1/), [original MIT-licensed source](https://github.com/facebookresearch/demucs), [author's follow-up repository](https://github.com/adefossez/demucs) |
| PyTorch and torchaudio 2.5.1 | [PyTorch source](https://github.com/pytorch/pytorch/tree/v2.5.1), [torchaudio source](https://github.com/pytorch/audio/tree/v2.5.1). The CUDA build includes the libraries supplied in the official Windows wheel. |
| Qt for Python and Qt 6.8.3 | [PySide source](https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.8.3), [Qt source packages](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/). The Windows package uses dynamically loaded Qt libraries. The GNU LGPL v3 and GPL v3 texts are included under `licenses/qt`. |
| FFmpeg and ffprobe 8.0.1 | [Windows build](https://www.gyan.dev/ffmpeg/builds/), [corresponding FFmpeg source](https://github.com/FFmpeg/FFmpeg/tree/894da5ca7d). The build's license, revision and configuration are included under `_internal/licenses/ffmpeg`. |
| NumPy, SciPy, SoundFile and libsndfile | [NumPy](https://github.com/numpy/numpy), [SciPy](https://github.com/scipy/scipy), [SoundFile](https://github.com/bastibe/python-soundfile), [libsndfile](https://github.com/libsndfile/libsndfile) |
| Inno Setup | [Installer project](https://jrsoftware.org/isinfo.php) |

Installed Python package metadata and the licenses supplied with those packages are included in the Windows runtime. The application fetches required model checkpoints from Demucs' model distribution on first use.
