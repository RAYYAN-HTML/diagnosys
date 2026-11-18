"""Background Qt task worker and result router."""

from PySide6.QtCore import QObject, QThread, Signal, Slot


class TaskWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, function):
        super().__init__()
        self.function = function

    @Slot()
    def run(self):
        try:
            self.finished.emit(self.function())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class TaskRouter(QObject):
    """Deliver worker results to the GUI thread before running widget callbacks."""

    def __init__(self, window: "MainWindow", key: str, callback, thread: QThread, worker: TaskWorker):
        super().__init__(window)
        self.window = window
        self.key = key
        self.callback = callback
        self.thread = thread
        self.worker = worker

    @Slot(object)
    def complete(self, result) -> None:
        try:
            self.callback(result)
        except Exception as exc:
            self.window._show_error(f"{type(exc).__name__}: {exc}")
        finally:
            self.window._finish_task(self.key)

    @Slot(str)
    def fail(self, error: str) -> None:
        self.window._finish_task(self.key)
        if self.key == "refresh":
            self.window.monitoring_badge.setText("MONITOR ISSUE")
            self.window.monitoring_badge.setObjectName("PillError")
            self.window.monitoring_badge.style().unpolish(self.window.monitoring_badge)
            self.window.monitoring_badge.style().polish(self.window.monitoring_badge)
        self.window._show_error(error)

    @Slot()
    def thread_finished(self) -> None:
        self.window._release_thread(self.thread)
        self.window._release_worker(self.worker)
        self.deleteLater()
