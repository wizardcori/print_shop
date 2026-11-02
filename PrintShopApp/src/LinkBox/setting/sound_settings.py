"""Approval Sound Alerts settings and UI component."""
import os
import shutil
try:
    import winsound
except ImportError:
    winsound = None

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup, QFileDialog, QMessageBox
from Common.config import FileConfigManager, ConfigType
from Common.settings_dialog import register_settings_tab
from Common.paths import APPROVAL_SOUND_DIR
from LinkBox.print_log_writer import play_notification_sound

DEFAULT_APPROVAL_SOUND_ENABLED = True
DEFAULT_APPROVAL_SOUNDS = ['', '', '', '', '']

class ApprovalSoundConfig(FileConfigManager):
    section = "ApprovalSoundConfig"
    section_order = 40
    schema = {
        'approval_sound_enabled': {"default": DEFAULT_APPROVAL_SOUND_ENABLED, "type": ConfigType.BOOLEAN},
        'approval_sounds': {"default": DEFAULT_APPROVAL_SOUNDS, "type": ConfigType.LIST},
    }

class ApprovalSoundTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ApprovalSoundConfig()
        self.approval_sound_dir = APPROVAL_SOUND_DIR
        self.approval_sounds = list(self.config.get('approval_sounds')[:5])
        self.selected_sound_index = -1
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h3>Approval Sound Alerts</h3>"))
        
        self.approval_sound_checkbox = QCheckBox("Play sound on approval")
        self.approval_sound_checkbox.setChecked(self.config.get('approval_sound_enabled'))
        layout.addWidget(self.approval_sound_checkbox)
        layout.addWidget(QLabel("Add sounds to play on approval and select one."))
        
        self.sound_radio_group = QButtonGroup(self)
        self.sound_radio_group.setExclusive(True)
        self.sound_radios = []
        
        self.play_sound_button = QPushButton("Play Sound")
        self.play_sound_button.clicked.connect(self.play_selected_approval_sound)
        self.play_sound_button.setEnabled(False)
        layout.addWidget(self.play_sound_button)
        
        self.sound_inputs = []
        for index in range(5):
            sound_row = QHBoxLayout()
            sound_radio = QRadioButton()
            sound_radio.setEnabled(bool(self.approval_sounds[index] if index < len(self.approval_sounds) else ''))
            sound_radio.toggled.connect(lambda checked, i=index: self.select_approval_sound(i, checked))
            self.sound_radio_group.addButton(sound_radio, index)
            self.sound_radios.append(sound_radio)
            sound_row.addWidget(sound_radio)
            sound_row.addWidget(QLabel(f"Sound {index + 1}"))
            sound_input = QLineEdit(self.approval_sounds[index] if index < len(self.approval_sounds) else '')
            self.sound_inputs.append(sound_input)
            sound_row.addWidget(sound_input)
            
            browse_sound_btn = QPushButton("Select")
            browse_sound_btn.clicked.connect(lambda checked=False, i=index: self.browse_approval_sound(i))
            sound_row.addWidget(browse_sound_btn)
            
            delete_sound_btn = QPushButton("Delete")
            delete_sound_btn.clicked.connect(lambda checked=False, i=index: self.delete_approval_sound(i))
            sound_row.addWidget(delete_sound_btn)
            layout.addLayout(sound_row)
            
        for index, path in enumerate(self.approval_sounds[:5]):
            if path:
                self.sound_radios[index].setChecked(True)
                break
        self.update_sound_button_text()
        layout.addStretch()

    def browse_approval_sound(self, index):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Approval Alert Sound", self.sound_inputs[index].text(),
            "Wave files (*.wav);;All files (*.*)"
        )
        if path:
            try:
                os.makedirs(self.approval_sound_dir, exist_ok=True)
                target_name = os.path.basename(path)
                target_path = os.path.join(self.approval_sound_dir, target_name)
                if os.path.abspath(path) != os.path.abspath(target_path):
                    shutil.copy2(path, target_path)
                self.sound_inputs[index].setText(target_path)
                self.sound_radios[index].setEnabled(True)
                self.sound_radios[index].setChecked(True)
                self.update_sound_button_text()
            except OSError as exc:
                QMessageBox.warning(self, "Sound copy failed", str(exc))

    def delete_approval_sound(self, index):
        current_path = self.sound_inputs[index].text().strip()
        try:
            if current_path and os.path.isfile(current_path):
                sound_root = os.path.abspath(self.approval_sound_dir)
                if os.path.commonpath([sound_root, os.path.abspath(current_path)]) == sound_root:
                    os.remove(current_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Sound deletion failed", str(exc))
        self.sound_inputs[index].clear()
        self.sound_radios[index].setChecked(False)
        self.sound_radios[index].setEnabled(False)
        self.update_sound_button_text()

    def select_approval_sound(self, index, checked):
        if checked:
            self.selected_sound_index = index
            self.update_sound_button_text()

    def update_sound_button_text(self):
        index = self.selected_sound_index
        path = self.sound_inputs[index].text().strip() if 0 <= index < len(self.sound_inputs) else ''
        self.play_sound_button.setText(f"Play: {os.path.basename(path)}" if path else "Play Sound")
        self.play_sound_button.setEnabled(bool(path and os.path.isfile(path)))

    def play_selected_approval_sound(self):
        index = self.selected_sound_index
        if not (0 <= index < len(self.sound_inputs)):
            return
        path = self.sound_inputs[index].text().strip()
        if winsound is not None and os.path.isfile(path):
            play_notification_sound(path)

    def save_to_config(self):
        self.config.set('approval_sound_enabled', self.approval_sound_checkbox.isChecked())
        sounds = [input_widget.text().strip() for input_widget in self.sound_inputs]
        if 0 <= self.selected_sound_index < len(sounds) and sounds[self.selected_sound_index]:
            selected = sounds.pop(self.selected_sound_index)
            sounds.insert(0, selected)
        self.config.set('approval_sounds', sounds)

register_settings_tab('linkbox.approval-sound-settings', 'Approval Alerts', ApprovalSoundTab, order=25)