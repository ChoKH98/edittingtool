from PyQt5.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTreeWidget, QTreeWidgetItem, QFileDialog, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal

class LvsDockWidget(QDockWidget):
    error_selected = pyqtSignal(str, str)  # component, category

    def __init__(self, parent=None):
        super().__init__('LVS Report', parent)
        self._lvs_result = None
        self._rerun_callback = None
        widget = QWidget()
        layout = QVBoxLayout(widget)
        btn_row = QHBoxLayout()
        self._rerun_btn = QPushButton('Re-run LVS')
        self._rerun_btn.clicked.connect(self._rerun)
        self._export_btn = QPushButton('Export Report')
        self._export_btn.clicked.connect(self._export)
        btn_row.addWidget(self._rerun_btn)
        btn_row.addWidget(self._export_btn)
        layout.addLayout(btn_row)
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(['Item', 'Detail'])
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)
        self.setWidget(widget)

    def show_results(self, lvs_result):
        self._lvs_result = lvs_result
        self._tree.clear()
        n_match = len(lvs_result.matches)
        n_err = len(lvs_result.errors)
        n_warn = len(lvs_result.warnings)
        match_root = QTreeWidgetItem(self._tree, [f'✅ MATCH ({n_match} items)', ''])
        for comp in lvs_result.matches:
            QTreeWidgetItem(match_root, [comp, ''])
        err_root = QTreeWidgetItem(self._tree, [f'❌ ERRORS ({n_err} items)', ''])
        for err in lvs_result.errors:
            item = QTreeWidgetItem(err_root, [f'{err.category}: {err.component}', err.detail])
            item.setData(0, Qt.UserRole, (err.component, err.category))
        warn_root = QTreeWidgetItem(self._tree, [f'⚠️ WARNINGS ({n_warn} items)', ''])
        for w in lvs_result.warnings:
            item = QTreeWidgetItem(warn_root, [f'{w.category}: {w.component}', w.detail])
            item.setData(0, Qt.UserRole, (w.component, w.category))
        self._tree.expandAll()
        self.show()

    def set_rerun_callback(self, callback):
        self._rerun_callback = callback

    def _rerun(self):
        if self._rerun_callback:
            self._rerun_callback()

    def _on_item_clicked(self, item, col):
        data = item.data(0, Qt.UserRole)
        if data:
            self.error_selected.emit(data[0], data[1])

    def _export(self):
        if not self._lvs_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export LVS Report', 'lvs_report.txt',
            'Text Files (*.txt)')
        if not path:
            return
        lines = ['LVS Report', '=' * 40]
        lines.append(f'MATCH: {len(self._lvs_result.matches)} components')
        for c in self._lvs_result.matches:
            lines.append(f'  OK: {c}')
        lines.append(f'ERRORS: {len(self._lvs_result.errors)}')
        for e in self._lvs_result.errors:
            lines.append(f'  [{e.category}] {e.component}: {e.detail}')
        lines.append(f'WARNINGS: {len(self._lvs_result.warnings)}')
        for w in self._lvs_result.warnings:
            lines.append(f'  [{w.category}] {w.component}: {w.detail}')
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
