"""Display the device Demucs will use without blocking the window at startup."""

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from PySide6.QtWidgets import QLabel

from .i18n import t


class _Result(QObject):
    ready = Signal(str, str)


class _CudaProbe(QRunnable):
    def __init__(self):
        super().__init__()
        self.result = _Result()

    def run(self):
        try:
            import torch
            name = torch.cuda.get_device_name() if torch.cuda.is_available() else ""
        except Exception as error:
            self.result.ready.emit("", str(error) or type(error).__name__)
        else:
            self.result.ready.emit(name, "")


class DeviceStatus(QLabel):
    def __init__(self, pool):
        super().__init__()
        self.setObjectName("local")
        self.pool = pool
        self.mode = "auto"
        self.probing = False
        self.gpu = None
        self.error = ""

    def set_mode(self, mode):
        self.mode = mode
        self.refresh()
        if mode != "cpu" and self.isVisible() and self.gpu is None and not self.probing:
            self.probing = True
            probe = _CudaProbe()
            probe.result.ready.connect(self.detected)
            self.pool.start(probe)

    def showEvent(self, event):
        super().showEvent(event)
        self.set_mode(self.mode)

    @Slot(str, str)
    def detected(self, name, error):
        self.gpu, self.error = name, error
        self.probing = False
        self.refresh()

    def refresh(self):
        if self.mode == "cpu":
            device = "CPU"
        elif self.gpu is None:
            device = t("확인 중…")
        elif self.error:
            device = t("확인 실패")
        elif self.gpu:
            device = f"GPU (CUDA) · {self.gpu}"
        elif self.mode == "auto":
            device = t("CPU (자동)")
        else:
            device = t("CUDA GPU 사용 불가")
        self.setText(t("분리 장치 · {device}", device=device))
        hint = t("보컬·악기 분리에 사용할 장치입니다. 고급 설정에서 변경할 수 있습니다.")
        self.setToolTip(f"{hint}\n{self.error}" if self.error and self.mode != "cpu" else hint)
