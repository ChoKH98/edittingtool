"""PEX results dock widget for IHP SG13G2 layout editor."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFileDialog,
)
from PyQt5.QtCore import Qt


class PexReport(QWidget):
    """Qt5 widget that displays PEX results in a tree and supports CSV export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Layer", "Label", "R (Ohm)", "C (fF)", "Area (um2)"])
        self._tree.setAlternatingRowColors(True)
        layout.addWidget(self._tree)

        btn_row = QHBoxLayout()
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export)
        btn_row.addStretch()
        btn_row.addWidget(export_btn)
        layout.addLayout(btn_row)

        self._results = []

    def show_results(self, results):
        """Populate the tree with PEX result dicts."""
        self._results = results
        self._tree.clear()
        for r in results:
            item = QTreeWidgetItem([
                r.get("layer", ""),
                r.get("label", ""),
                "{:.4f}".format(r.get("R_ohm", 0.0)),
                "{:.4f}".format(r.get("C_fF", 0.0)),
                "{:.4f}".format(r.get("area_um2", 0.0)),
            ])
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            self._tree.addTopLevelItem(item)
        for col in range(5):
            self._tree.resizeColumnToContents(col)

    def _export(self):
        """Save results to a CSV file chosen via file dialog."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PEX CSV", "pex_results.csv", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("Layer,Label,R_ohm,C_fF,Area_um2\n")
            for r in self._results:
                f.write(
                    "{},{},{:.6f},{:.6f},{:.6f}\n".format(
                        r.get("layer", ""),
                        r.get("label", ""),
                        r.get("R_ohm", 0.0),
                        r.get("C_fF", 0.0),
                        r.get("area_um2", 0.0),
                    )
                )
