from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished=Signal(object)
    error=Signal(str)
    progress=Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self,fn,*args,**kwargs)->None:
        super().__init__();self.fn=fn;self.args=args;self.kwargs=kwargs;self.signals=WorkerSignals()

    @Slot()
    def run(self)->None:
        try:
            result=self.fn(*self.args,**self.kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)
