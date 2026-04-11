from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QObject
from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from .frida_ops import AppInfo

COL_INDEX = 0
COL_STATUS = 1
COL_PID = 2
COL_APP_NAME = 3
COL_PACKAGE = 4
COL_SCRIPTS = 5
COL_ACTION = 6
COLUMN_COUNT = 7

HEADERS = ["#", "状态", "PID", "应用名", "包名", "脚本", "操作"]

AppIdRole = Qt.ItemDataRole.UserRole + 1


class AppTableModel(QAbstractTableModel):

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all_apps: list[AppInfo] = []
        self._script_counts: dict[str, int] = {}
        self._search: str = ""
        self._display_apps: list[AppInfo] = []
        self._fingerprint: str = ""

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        return len(self._display_apps)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        return COLUMN_COUNT

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        app = self._display_apps[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_INDEX:
                return str(row + 1)
            if col == COL_STATUS:
                return "运行中" if app.is_running else "未运行"
            if col == COL_PID:
                return str(app.pid) if app.is_running else "-"
            if col == COL_APP_NAME:
                return app.name
            if col == COL_PACKAGE:
                return app.identifier
            if col == COL_SCRIPTS:
                count = self._script_counts.get(app.identifier, 0)
                return str(count) if count > 0 else "-"
            if col == COL_ACTION:
                return None
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == COL_STATUS:
                return QColor(Qt.GlobalColor.darkGreen) if app.is_running else QColor(Qt.GlobalColor.gray)
            if col == COL_PID:
                return QColor(Qt.GlobalColor.gray) if not app.is_running else None
            if col == COL_SCRIPTS:
                count = self._script_counts.get(app.identifier, 0)
                return QColor(Qt.GlobalColor.darkGreen) if count > 0 else QColor(Qt.GlobalColor.gray)
            return None

        if role == AppIdRole:
            return app.identifier

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (COL_INDEX, COL_STATUS, COL_PID):
                return Qt.AlignmentFlag.AlignCenter
            return None

        return None

    @override
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return super().headerData(section, orientation, role)

    @override
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_data(self, apps: list[AppInfo], script_counts: dict[str, int]) -> None:
        fingerprint = ",".join(
            f"{a.is_running}:{a.pid}:{a.name}:{a.identifier}"
            for a in sorted(apps, key=lambda a: (not a.is_running, -(a.pid or 0), a.name.lower()))
        )
        if fingerprint == self._fingerprint and self._search == "":
            return
        self._all_apps = apps
        self._script_counts = script_counts
        self._fingerprint = fingerprint
        self._recompute_display()

    def set_search(self, text: str) -> None:
        if text == self._search:
            return
        self._search = text
        self._recompute_display()

    def _recompute_display(self) -> None:
        self.beginResetModel()
        apps = self._all_apps
        if self._search:
            search_lower = self._search.lower()
            apps = [
                a for a in apps
                if search_lower in a.name.lower() or search_lower in a.identifier.lower()
            ]
        self._display_apps = sorted(
            apps,
            key=lambda a: (not a.is_running, a.name.lower()),
        )
        self.endResetModel()

    def app_at_row(self, row: int) -> AppInfo | None:
        if 0 <= row < len(self._display_apps):
            return self._display_apps[row]
        return None
