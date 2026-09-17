import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class AsyncWorker(QRunnable):
    """Run one async backend operation without blocking the Qt event loop."""

    def __init__(self, task_factory: Callable[[], Awaitable[Any]]) -> None:
        super().__init__()
        self.task_factory = task_factory
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = asyncio.run(self.task_factory())
        except Exception as exc:  # GUI boundary: surface backend/network errors to the user.
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
