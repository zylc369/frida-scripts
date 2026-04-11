from __future__ import annotations

from typing import override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)


class GearButtonDelegate(QStyledItemDelegate):
    gear_clicked = Signal(QModelIndex)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._hovered_row: int = -1
        self._pressed_row: int = -1

    @override
    def editorEvent(
        self,
        event,
        model,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if not isinstance(event, QMouseEvent):
            return False

        btn_rect = self._button_rect(option.rect)

        if event.type() == QMouseEvent.Type.MouseMove:
            inside = btn_rect.contains(event.position().toPoint())
            new_row = index.row() if inside else -1
            if new_row != self._hovered_row:
                self._hovered_row = new_row
                table = self.parent()
                if isinstance(table, QAbstractItemView):
                    table.viewport().update()
            return False

        if event.type() == QMouseEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and btn_rect.contains(event.position().toPoint()):
                self._pressed_row = index.row()
                return True
            return False

        if event.type() == QMouseEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._pressed_row == index.row() and btn_rect.contains(event.position().toPoint()):
                    self._pressed_row = -1
                    self.gear_clicked.emit(index)
                    return True
                self._pressed_row = -1
                return False
            self._pressed_row = -1
            return False

        return False

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)

        painter.save()

        rect = self._button_rect(option.rect)

        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = "#BBDEFB"
        elif self._pressed_row == index.row():
            bg_color = "#c5e1a5"
        elif self._hovered_row == index.row():
            bg_color = "#dcedc8"
        else:
            bg_color = "#f1f8e9"

        painter.setBrush(QColor(bg_color))
        painter.setPen(QColor("#a5d6a7"))
        painter.drawRoundedRect(rect, 4, 4)

        painter.setPen(QColor("#2e7d32"))
        font = QFont()
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "\u2699")

        painter.restore()

    def _button_rect(self, cell_rect: QRect) -> QRect:
        center_x = cell_rect.x() + (cell_rect.width() - 28) // 2
        center_y = cell_rect.y() + (cell_rect.height() - 24) // 2
        return QRect(center_x, center_y, 28, 24)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(40, 28)
