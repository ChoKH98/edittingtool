#!/usr/bin/env python3
"""Main application window for the IHP SG13G2 layout editor."""
import sys
from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QAction,
        QActionGroup,
        QApplication,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QTabWidget,
        QTextEdit,
        QToolBar,
        QVBoxLayout,
    )
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtCore import Qt
except ImportError:
    print('Install PyQt5: pip3 install PyQt5')
    sys.exit(1)

import canvas
import drc_engine
import gds_backend
import layer_panel
import pcell
import router
import align_tools
from via_generator import ViaDialog
from pex.pex_engine import PexEngine
from pex.pex_report import PexReport
from verification_panel import VerificationPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('IHP SG13G2 Layout Editor')
        self.resize(1400, 900)
        self.current_file = None
        self._verification_gds_path = None

        self.layer_panel_widget = layer_panel.LayerPanel(self)
        self.canvas = canvas.LayoutCanvas(self)
        self.router_state = router.RouterState(self.canvas)
        self.canvas.set_layer_panel(self.layer_panel_widget)
        self.canvas.set_router(self.router_state)
        canvas._patch_canvas_for_realtime_drc(self.canvas)
        self.setCentralWidget(self.canvas)

        self.drc_results = QTextEdit(self)
        self.drc_results.setReadOnly(True)
        self.drc_results.setStyleSheet('background: #202020; color: #eeeeee;')
        self.pex_report = PexReport(self)
        self._verif_panel = VerificationPanel(self)
        self.verif_panel = self._verif_panel
        self._verif_window = None
        self._verif_panel.gds_changed.connect(self._on_verification_gds_changed)

        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._connect_status_bar()

    def _build_docks(self):
        layers_dock = QDockWidget('Layers', self)
        layers_dock.setWidget(self.layer_panel_widget)
        layers_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.LeftDockWidgetArea, layers_dock)

        drc_dock = QDockWidget('DRC Results', self)
        drc_dock.setWidget(self.drc_results)
        drc_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.RightDockWidgetArea, drc_dock)

        pex_dock = QDockWidget('PEX Results', self)
        pex_dock.setWidget(self.pex_report)
        pex_dock.setMinimumWidth(320)
        self.addDockWidget(Qt.RightDockWidgetArea, pex_dock)

    def _build_actions(self):
        self.new_action = QAction('New', self)
        self.new_action.setShortcut(QKeySequence.New)
        self.new_action.triggered.connect(self.new_layout)

        self.open_action = QAction('Open GDS', self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_gds)

        self.save_action = QAction('Save GDS', self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self.save_gds)

        self.save_oasis_action = QAction('Save OASIS', self)
        self.save_oasis_action.triggered.connect(self.save_oasis)

        self.load_pdk_action = QAction("Load PDK...", self)
        self.load_pdk_action.triggered.connect(self.load_pdk)

        self.exit_action = QAction('Exit', self)
        self.exit_action.triggered.connect(self.close)

        self.undo_action = self.canvas.undo_stack().createUndoAction(self, 'Undo')
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = self.canvas.undo_stack().createRedoAction(self, 'Redo')
        self.redo_action.setShortcut(QKeySequence.Redo)

        self.copy_action = QAction('Copy', self)
        self.copy_action.setShortcut(QKeySequence.Copy)
        self.copy_action.triggered.connect(self.canvas.copy_selected)

        self.paste_action = QAction('Paste', self)
        self.paste_action.setShortcut(QKeySequence.Paste)
        self.paste_action.triggered.connect(self.canvas.paste_clipboard)

        self.delete_action = QAction('Delete', self)
        self.delete_action.setShortcut(QKeySequence.Delete)
        self.delete_action.triggered.connect(self.canvas.delete_selected)

        self.flip_h_action = QAction('Flip Horizontal', self)
        self.flip_h_action.setShortcut('X')
        self.flip_h_action.triggered.connect(lambda: self.canvas.flip_selected(True))

        self.flip_v_action = QAction('Flip Vertical', self)
        self.flip_v_action.setShortcut('Shift+X')
        self.flip_v_action.triggered.connect(lambda: self.canvas.flip_selected(False))

        self.rotate_ccw_action = QAction('Rotate CCW', self)
        self.rotate_ccw_action.setShortcut('Ctrl+R')
        self.rotate_ccw_action.triggered.connect(lambda: self.canvas.rotate_selected(True))

        self.rotate_cw_action = QAction('Rotate CW', self)
        self.rotate_cw_action.setShortcut('Ctrl+Shift+R')
        self.rotate_cw_action.triggered.connect(lambda: self.canvas.rotate_selected(False))

        self.merge_action = QAction('Merge Shapes', self)
        self.merge_action.setShortcut('Ctrl+M')
        self.merge_action.triggered.connect(self.canvas.merge_selected)

        self.sel_layer_action = QAction('Select Active Layer', self)
        self.sel_layer_action.setShortcut('Shift+A')
        self.sel_layer_action.triggered.connect(
            lambda: self.canvas.select_all_on_layer(self.layer_panel_widget.active_layer())
        )

        self.via_action = QAction('Create Via...', self)
        self.via_action.setShortcut('V')
        self.via_action.triggered.connect(self.create_via)

        self.array_action = QAction('Create Array...', self)
        self.array_action.triggered.connect(self.create_array)


        self.fit_action = QAction('Fit View', self)
        self.fit_action.setShortcut('F')
        self.fit_action.triggered.connect(self.canvas.fit_view)

        self.toggle_grid_action = QAction('Toggle Grid', self)
        self.toggle_grid_action.setShortcut('G')
        self.toggle_grid_action.triggered.connect(self.canvas.toggle_grid)

        self.grid_settings_action = QAction('Grid Settings...', self)
        self.grid_settings_action.triggered.connect(self.show_grid_settings)

        self.zoom_in_action = QAction('Zoom In', self)
        self.zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        self.zoom_in_action.triggered.connect(lambda: self.canvas.zoom(1.15))

        self.zoom_out_action = QAction('Zoom Out', self)
        self.zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        self.zoom_out_action.triggered.connect(lambda: self.canvas.zoom(1.0 / 1.15))
        self.zoom_sel_action = QAction('Zoom to Selection', self)
        self.zoom_sel_action.setShortcut('E')
        self.zoom_sel_action.triggered.connect(self.canvas.zoom_to_selection)


        self.run_drc_action = QAction('Run DRC', self)
        self.run_drc_action.triggered.connect(self.run_drc)

        self.realtime_drc_action = QAction('Real-time DRC', self)
        self.realtime_drc_action.setCheckable(True)
        self.realtime_drc_action.toggled.connect(self.canvas.toggle_realtime_drc)

        self.clear_drc_action = QAction('Clear DRC', self)
        self.clear_drc_action.triggered.connect(self.clear_drc)

        self.run_pex_action = QAction('Run PEX', self)
        self.run_pex_action.triggered.connect(self.run_pex)

        self.verify_drc_action = QAction('Run DRC...', self)
        self.verify_drc_action.setShortcut('Ctrl+Shift+D')
        self.verify_drc_action.triggered.connect(lambda: self._open_verification(0))

        self.verify_lvs_action = QAction('Run LVS...', self)
        self.verify_lvs_action.setShortcut('Ctrl+Shift+L')
        self.verify_lvs_action.triggered.connect(lambda: self._open_verification(1))

        self.verify_pex_action = QAction('Run PEX...', self)
        self.verify_pex_action.setShortcut('Ctrl+Shift+P')
        self.verify_pex_action.triggered.connect(lambda: self._open_verification(2))

        self.verify_post_sim_action = QAction('Post-Layout Sim...', self)
        self.verify_post_sim_action.triggered.connect(lambda: self._open_verification(3))

        self.open_verification_action = QAction('Open Verification Panel', self)
        self.open_verification_action.setShortcut('Ctrl+Shift+V')
        self.open_verification_action.triggered.connect(lambda: self._open_verification(0))

        self.add_pcell_action = QAction('Add PCell Instance', self)
        self.add_pcell_action.triggered.connect(self.add_pcell_instance)

        self.about_action = QAction('About', self)
        self.about_action.triggered.connect(self.show_about)

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.select_action = QAction('Select', self, checkable=True)
        self.select_action.setShortcut('S')
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(lambda: self.set_mode('select'))
        self.rectangle_action = QAction('Rectangle', self, checkable=True)
        self.rectangle_action.setShortcut('R')
        self.rectangle_action.triggered.connect(lambda: self.set_mode('rectangle'))
        self.wire_action = QAction('Wire', self, checkable=True)
        self.wire_action.setShortcut('W')
        self.wire_action.triggered.connect(lambda: self.set_mode('wire'))
        self.polygon_action = QAction('Polygon', self, checkable=True)
        self.polygon_action.setShortcut('Shift+P')
        self.polygon_action.triggered.connect(lambda: self.set_mode('polygon'))
        self.label_action = QAction('Label', self, checkable=True)
        self.label_action.setShortcut('L')
        self.label_action.triggered.connect(lambda: self.set_mode('label'))

        self.ruler_action = QAction('Ruler', self, checkable=True)
        self.ruler_action.setShortcut('M')
        self.ruler_action.triggered.connect(lambda: self.set_mode('ruler'))
        self.mode_group.addAction(self.ruler_action)
        for action in (
            self.select_action,
            self.rectangle_action,
            self.wire_action,
            self.polygon_action,
            self.label_action,
            self.ruler_action,
        ):
            self.mode_group.addAction(action)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu('File')
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_oasis_action)
        file_menu.addSeparator()
        file_menu.addAction(self.load_pdk_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu('Edit')
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.flip_h_action)
        edit_menu.addAction(self.flip_v_action)
        edit_menu.addAction(self.rotate_ccw_action)
        edit_menu.addAction(self.rotate_cw_action)
        edit_menu.addAction(self.merge_action)
        edit_menu.addAction(self.sel_layer_action)
        align_menu = edit_menu.addMenu('Align')
        for label, fn in [
            ('Align Left', align_tools.align_left),
            ('Align Right', align_tools.align_right),
            ('Align Top', align_tools.align_top),
            ('Align Bottom', align_tools.align_bottom),
            ('Center Horizontal', align_tools.align_center_h),
            ('Center Vertical', align_tools.align_center_v),
            ('Distribute Horizontal', align_tools.distribute_h),
            ('Distribute Vertical', align_tools.distribute_v),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked, f=fn: f(self.canvas))
            align_menu.addAction(act)
        edit_menu.addAction(self.array_action)


        view_menu = self.menuBar().addMenu('View')
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.toggle_grid_action)
        view_menu.addAction(self.grid_settings_action)
        view_menu.addSeparator()
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_sel_action)

        tools_menu = self.menuBar().addMenu('Tools')
        tools_menu.addAction(self.run_drc_action)
        tools_menu.addAction(self.realtime_drc_action)
        tools_menu.addAction(self.clear_drc_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.run_pex_action)
        tools_menu.addAction(self.add_pcell_action)
        tools_menu.addAction(self.via_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.ruler_action)

        verification_menu = self.menuBar().addMenu('Verification')
        verification_menu.addAction(self.verify_drc_action)
        verification_menu.addAction(self.verify_lvs_action)
        verification_menu.addAction(self.verify_pex_action)
        verification_menu.addAction(self.verify_post_sim_action)
        verification_menu.addSeparator()
        verification_menu.addAction(self.open_verification_action)

        help_menu = self.menuBar().addMenu('Help')
        help_menu.addAction(self.about_action)

    def _build_toolbar(self):
        toolbar = QToolBar('Layout Tools', self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.select_action)
        toolbar.addAction(self.rectangle_action)
        toolbar.addAction(self.wire_action)
        self.wire_width_spin = QDoubleSpinBox(self)
        self.wire_width_spin.setRange(0.05, 10.0)
        self.wire_width_spin.setDecimals(2)
        self.wire_width_spin.setSingleStep(0.05)
        self.wire_width_spin.setSuffix(' um')
        self.wire_width_spin.setValue(0.20)
        self.wire_width_spin.valueChanged.connect(lambda value: setattr(self.router_state, 'width_um', value))
        toolbar.addWidget(QLabel('W:', self))
        toolbar.addWidget(self.wire_width_spin)
        toolbar.addAction(self.polygon_action)
        toolbar.addAction(self.label_action)
        toolbar.addAction(self.via_action)
        toolbar.addAction(self.ruler_action)
        toolbar.addSeparator()
        toolbar.addAction(self.flip_h_action)
        toolbar.addAction(self.flip_v_action)
        toolbar.addAction(self.rotate_ccw_action)
        toolbar.addAction(self.rotate_cw_action)
        toolbar.addAction(self.merge_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        toolbar.addAction(self.run_drc_action)
        toolbar.addAction(self.fit_action)

    def _connect_status_bar(self):
        self.statusBar().showMessage('x=0.000 um, y=0.000 um, dX=0.000 um, dY=0.000 um')
        self.canvas.coord_changed.connect(
            lambda x, y, dx, dy: self.statusBar().showMessage(
                f'x={x:.3f} um, y={y:.3f} um, dX={dx:.3f} um, dY={dy:.3f} um'
            )
        )

    def set_mode(self, mode):
        self.canvas.set_mode(mode)
        if mode == 'select':
            self.select_action.setChecked(True)
        elif mode == 'rectangle':
            self.rectangle_action.setChecked(True)
        elif mode == 'wire':
            self.wire_action.setChecked(True)
        elif mode == 'polygon':
            self.polygon_action.setChecked(True)
        elif mode == 'label':
            self.label_action.setChecked(True)
        elif mode == 'ruler':
            self.ruler_action.setChecked(True)

    def new_layout(self):
        self.canvas.clear_layout()
        self.drc_results.clear()
        self.current_file = None
        self._verification_gds_path = None
        self._update_verification_title()
        self.statusBar().showMessage('New layout')

    def open_gds(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open GDS', '', 'GDS/OASIS (*.gds *.gdsii *.oas *.oasis);;All files (*)')
        if not path:
            return
        try:
            shapes = gds_backend.load_gds(path)
            self.canvas.clear_layout()
            self.canvas.add_shapes(shapes)
            self.canvas.fit_view()
            self.current_file = path
            self._set_verification_gds(path)
            self.statusBar().showMessage(f'Loaded {len(shapes)} shapes from {path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Open GDS failed', str(exc))

    def save_gds(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save GDS', self.current_file or 'layout.gds', 'GDS files (*.gds);;All files (*)')
        if not path:
            return
        try:
            gds_backend.save_gds(path, self.canvas.get_all_shapes())
            self.current_file = path
            self.statusBar().showMessage(f'Saved GDS to {path}')
            self._set_verification_gds(path)
        except Exception as exc:
            QMessageBox.critical(self, 'Save GDS failed', str(exc))

    def load_pdk(self):
        from pdk_manager import PDK
        path, _ = QFileDialog.getOpenFileName(self, "Load PDK", "", "PDK JSON (*.json)")
        if path:
            name, _ = PDK.load(path)
            self.setWindowTitle(f"IHP SG13G2 Layout Editor [{name}]")
            self.statusBar().showMessage(f"PDK loaded: {name}")

    def load_pcell(self, cell_name, params=None):
        """Generate and display a PCell layout in the canvas."""
        try:
            from pdk.ihp_pcells import generate
        except ImportError:
            QMessageBox.warning(self, 'PCell Error', 'pdk/ihp_pcells.py not found.')
            return
        shapes = generate(cell_name, params or {})
        if not shapes:
            QMessageBox.information(self, 'PCell', f"No shapes generated for '{cell_name}'.")
            return
        self.canvas.clear_layout()
        self.canvas.add_shapes(shapes)
        self.canvas.fit_view()
        self.statusBar().showMessage(f"Loaded PCell '{cell_name}' with {len(shapes)} shapes")

    def save_oasis(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save OASIS', 'layout.oas', 'OASIS files (*.oas *.oasis);;All files (*)')
        if not path:
            return
        try:
            gds_backend.save_oasis(path, self.canvas.get_all_shapes())
            self.statusBar().showMessage(f'Saved OASIS to {path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Save OASIS failed', str(exc))

    def run_drc(self):
        violations = drc_engine.DrcEngine().run(self.canvas.get_all_shapes())
        self.canvas.show_drc_violations(violations)
        if not violations:
            self.drc_results.setPlainText('PASS: no DRC violations')
        else:
            lines = []
            for index, violation in enumerate(violations, 1):
                bbox = violation.get('bbox', ())
                lines.append(f"{index}. {violation.get('rule', 'DRC')}: {violation.get('description', '')}\n   bbox={bbox}")
            self.drc_results.setPlainText('\n'.join(lines))
        self.statusBar().showMessage(f'DRC complete: {len(violations)} violation(s)')

    def clear_drc(self):
        self.canvas.clear_drc()
        self.drc_results.clear()
        self.statusBar().showMessage('DRC overlays cleared')

    def run_pex(self):
        results = PexEngine().run(self.canvas.get_all_shapes())
        self.pex_report.show_results(results)
        total_r = sum(r["R_ohm"] for r in results)
        total_c = sum(r["C_fF"] for r in results)
        self.statusBar().showMessage(f"PEX: {len(results)} elements, R_total={total_r:.2f}Ω, C_total={total_c:.2f}fF")

    def add_pcell_instance(self):
        dialog = pcell.AddInstanceDialog(self)
        if dialog.exec_():
            try:
                shapes = dialog.get_shapes()
                self.canvas.add_shapes(shapes)
                self.statusBar().showMessage(f'Added PCell with {len(shapes)} shapes')
            except Exception as exc:
                QMessageBox.critical(self, 'Add PCell failed', str(exc))

    def create_via(self):
        dialog = ViaDialog(self)
        if dialog.exec_():
            try:
                shapes = dialog.get_shapes()
                self.canvas.add_shapes(shapes)
                self.statusBar().showMessage(f'Added via with {len(shapes)} shapes')
            except Exception as exc:
                QMessageBox.critical(self, 'Create Via failed', str(exc))

    def create_array(self):
        from array_dialog import ArrayDialog
        selected = [i for i in self.canvas.scene().selectedItems() if hasattr(i, 'shape_dict')]
        if not selected:
            QMessageBox.information(self, 'Array', 'Select shapes first.')
            return
        dlg = ArrayDialog(self)
        if dlg.exec_():
            rows, cols, dx, dy = dlg.get_params()
            base_shapes = [i.shape_dict for i in selected]
            new_shapes = []
            for r in range(rows):
                for c in range(cols):
                    if r == 0 and c == 0:
                        continue
                    for s in base_shapes:
                        ns = dict(s)
                        ns['x'] = round(float(s['x']) + c * dx, 6)
                        ns['y'] = round(float(s['y']) + r * dy, 6)
                        new_shapes.append(ns)
            self.canvas.add_shapes(new_shapes)
            self.statusBar().showMessage(
                f'Array: {rows}x{cols} = {len(new_shapes) + len(base_shapes)} shapes'
            )

    def show_grid_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Grid Settings')
        form = QFormLayout()

        minor_spin = QDoubleSpinBox()
        minor_spin.setRange(1, 10000)
        minor_spin.setDecimals(0)
        minor_spin.setSuffix(' nm')
        minor_spin.setValue(self.canvas._grid_minor * 1000)

        major_spin = QDoubleSpinBox()
        major_spin.setRange(1, 100000)
        major_spin.setDecimals(0)
        major_spin.setSuffix(' nm')
        major_spin.setValue(self.canvas._grid_major * 1000)

        form.addRow('Minor grid:', minor_spin)
        form.addRow('Major grid:', major_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if dlg.exec_():
            minor_um = minor_spin.value() / 1000.0
            major_um = major_spin.value() / 1000.0
            self.canvas.set_grid_spacing(minor_um, major_um)
            self.statusBar().showMessage(
                f'Grid: minor={int(minor_spin.value())}nm, major={int(major_spin.value())}nm'
            )

    def show_about(self):
        QMessageBox.about(
            self,
            'About',
            'IHP SG13G2 Layout Editor\nPyQt5 + klayout.db MVP',
        )

    def _cell_name(self):
        path = self._verification_gds_path or self.current_file
        if path:
            return Path(path).stem
        return 'Untitled'

    def _set_verification_gds(self, path):
        self._verif_panel.set_gds(path)

    def _on_verification_gds_changed(self, path):
        self._verification_gds_path = path
        self._update_verification_title()

    def _update_verification_title(self):
        if self._verif_window is not None:
            self._verif_window.set_cell_name(self._cell_name())

    def _open_verification(self, tab_index=0):
        if self._verif_window is None or not self._verif_window.isVisible():
            self._verif_window = VerificationWindow(self._verif_panel, self)
            self._verif_window.set_cell_name(self._cell_name())
            self._verif_window.show()
        self._verif_window.set_tab(tab_index)
        self._verif_window.raise_()
        self._verif_window.activateWindow()


class VerificationWindow(QMainWindow):
    TAB_NAMES = ('DRC', 'LVS', 'PEX', 'Post-Sim')

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._tab_widget = self._find_tab_widget()
        self.setWindowTitle('Verification — Untitled')
        self.resize(800, 600)
        self.setStyleSheet('QMainWindow{background:#1e1e2e;}')
        self.setCentralWidget(panel)
        self._build_menus()

    def _find_tab_widget(self):
        if hasattr(self._panel, 'setCurrentIndex'):
            return self._panel
        return self._panel.findChild(QTabWidget)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu('File')
        close_action = QAction('Close', self)
        close_action.setShortcut(QKeySequence.Close)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        view_menu = self.menuBar().addMenu('View')
        for index, name in enumerate(self.TAB_NAMES):
            action = QAction(name, self)
            action.triggered.connect(lambda checked, tab=index: self.set_tab(tab))
            view_menu.addAction(action)
        view_menu.addSeparator()

        self.keep_on_top_action = QAction('Keep on Top', self, checkable=True)
        self.keep_on_top_action.toggled.connect(self._set_keep_on_top)
        view_menu.addAction(self.keep_on_top_action)

    def set_cell_name(self, cell_name):
        self.setWindowTitle(f'Verification — {cell_name}')

    def set_tab(self, index):
        if self._tab_widget is not None:
            self._tab_widget.setCurrentIndex(index)

    def _set_keep_on_top(self, enabled):
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
            self.raise_()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
