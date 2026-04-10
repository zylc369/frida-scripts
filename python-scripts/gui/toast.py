from PySide6.QtCore import QPoint, QTimer, QPropertyAnimation, Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect


class ToastWidget(QWidget):

    _STYLE_SUCCESS = """
        ToastWidget {
            background-color: #4CAF50;
            border-radius: 6px;
        }
        QLabel {
            color: white;
            font-size: 13px;
            padding: 10px 20px;
        }
    """
    _STYLE_ERROR = """
        ToastWidget {
            background-color: #F44336;
            border-radius: 6px;
        }
        QLabel {
            color: white;
            font-size: 13px;
            padding: 10px 20px;
        }
    """

    @staticmethod
    def show_success(parent: QWidget, message: str, duration_ms: int = 3000) -> None:
        ToastWidget(parent, message, duration_ms, ToastWidget._STYLE_SUCCESS)

    @staticmethod
    def show_error(parent: QWidget, message: str, duration_ms: int = 4000) -> None:
        ToastWidget(parent, message, duration_ms, ToastWidget._STYLE_ERROR)

    def __init__(
        self,
        parent: QWidget,
        message: str,
        duration_ms: int,
        stylesheet: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(message)
        layout.addWidget(label)

        self.setStyleSheet(stylesheet)
        self.adjustSize()
        self.setFixedSize(self.size())

        if parent is not None:
            top_left = parent.mapToGlobal(QPoint(0, 0))
            toast_x = top_left.x() + (parent.width() - self.width()) // 2
            toast_y = top_left.y() + 10
            self.move(toast_x, toast_y)

        opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacity)
        self._fade_in = QPropertyAnimation(opacity, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QPropertyAnimation(opacity, b"opacity")
        self._fade_out.setDuration(300)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.close)

        self.show()
        self._fade_in.start()

        QTimer.singleShot(duration_ms, self._start_fade_out)

    def _start_fade_out(self) -> None:
        self._fade_out.start()
