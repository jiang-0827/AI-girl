"""设置面板 - API Key、模型、角色图片、大小、透明度、热键、开机自启"""
import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QSlider, QPushButton, QCheckBox, QFileDialog, QDialogButtonBox,
    QMessageBox, QTabWidget, QWidget, QSpinBox
)

from core.tts_engine import VOICES


class SettingsDialog(QDialog):
    """应用设置对话框，编辑一个 config 字典副本，确定后回写"""

    def __init__(self, cfg: dict, parent=None, memory=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.memory = memory
        self.setWindowTitle("桌面小助手 · 设置")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(460, 420)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # --- AI 标签页 ---
        ai_tab = QWidget()
        form = QFormLayout(ai_tab)
        self.api_key_edit = QLineEdit(self.cfg.get("api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-... （在 dashscope.console.aliyun.com 申请）")
        show_btn = QPushButton("显示")
        show_btn.setCheckable(True)
        show_btn.toggled.connect(lambda c: self.api_key_edit.setEchoMode(
            QLineEdit.Normal if c else QLineEdit.Password))
        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key_edit)
        key_row.addWidget(show_btn)
        form.addRow("API Key:", self._wrap(key_row))

        self.model_combo = QComboBox()
        self.model_combo.addItems(["qwen-turbo", "qwen-plus", "qwen-max"])
        cur_model = self.cfg.get("model", "qwen-turbo")
        if cur_model in ["qwen-turbo", "qwen-plus", "qwen-max"]:
            self.model_combo.setCurrentText(cur_model)
        form.addRow("模型:", self.model_combo)

        from PySide6.QtWidgets import QTextEdit
        self.sys_prompt_edit = QTextEdit()
        self.sys_prompt_edit.setPlainText(self.cfg.get("system_prompt", ""))
        self.sys_prompt_edit.setFixedHeight(80)
        form.addRow("人设提示:", self.sys_prompt_edit)

        form.addRow(QLabel("提示：qwen-turbo 响应快、qwen-plus 效果更好、qwen-max 最强。"))
        tabs.addTab(ai_tab, "AI")

        # --- 外观标签页 ---
        view_tab = QWidget()
        vform = QFormLayout(view_tab)

        img_row = QHBoxLayout()
        self.img_edit = QLineEdit(self.cfg.get("character_image", ""))
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_img)
        img_row.addWidget(self.img_edit)
        img_row.addWidget(browse)
        vform.addRow("角色图片:", self._wrap(img_row))

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(96, 320)
        self.size_slider.setValue(int(self.cfg.get("pet_size", 160)))
        self.size_lbl = QLabel(f"{self.size_slider.value()} px")
        self.size_slider.valueChanged.connect(lambda v: self.size_lbl.setText(f"{v} px"))
        size_row = QHBoxLayout()
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_lbl)
        vform.addRow("角色大小:", self._wrap(size_row))

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(120, 255)
        self.opacity_slider.setValue(int(self.cfg.get("opacity", 255)))
        self.opacity_lbl = QLabel(f"{self.opacity_slider.value()}")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v}"))
        op_row = QHBoxLayout()
        op_row.addWidget(self.opacity_slider)
        op_row.addWidget(self.opacity_lbl)
        vform.addRow("不透明度:", self._wrap(op_row))

        self.hotkey_edit = QLineEdit(self.cfg.get("hotkey", "<ctrl>+<shift>+<space>"))
        self.hotkey_edit.setPlaceholderText("例: <ctrl>+<shift>+<space>")
        vform.addRow("全局热键:", self.hotkey_edit)
        vform.addRow(QLabel("热键格式参考 pynput，如 <ctrl>+<alt>+h"))
        tabs.addTab(view_tab, "外观与交互")

        # --- 语音标签页 ---
        voice_tab = QWidget()
        wform = QFormLayout(voice_tab)

        self.tts_chk = QCheckBox("启用语音播报（AI 回复读出来）")
        self.tts_chk.setChecked(bool(self.cfg.get("enable_tts", True)))
        wform.addRow(self.tts_chk)

        self.voice_combo = QComboBox()
        for label in VOICES.keys():
            self.voice_combo.addItem(label)
        cur_voice = self.cfg.get("tts_voice", "Cherry")
        for i, (label, val) in enumerate(VOICES.items()):
            if val == cur_voice:
                self.voice_combo.setCurrentIndex(i)
                break
        wform.addRow("音色:", self.voice_combo)

        self.asr_chk = QCheckBox("启用语音输入（对着麦克风说话）")
        self.asr_chk.setChecked(bool(self.cfg.get("enable_asr", True)))
        wform.addRow(self.asr_chk)

        self.voice_hotkey_edit = QLineEdit(self.cfg.get("voice_hotkey", "<ctrl>+<shift>+v"))
        self.voice_hotkey_edit.setPlaceholderText("例: <ctrl>+<shift>+v")
        wform.addRow("语音输入热键:", self.voice_hotkey_edit)
        wform.addRow(QLabel("按下语音热键开始录音，再按一次停止并识别；也可点输入条的 🎤 按钮。"))
        tabs.addTab(voice_tab, "语音")

        # --- 管家与自动化标签页 ---
        butler_tab = QWidget()
        bform = QFormLayout(butler_tab)

        self.tools_chk = QCheckBox("启用系统操作（打开应用/文件、音量、亮度、窗口、提醒等）")
        self.tools_chk.setChecked(bool(self.cfg.get("enable_tools", True)))
        bform.addRow(self.tools_chk)
        bform.addRow(QLabel("安全：关机/删除/格式化等有害操作已永久禁止；"
                            "所有会改动电脑的操作每次都会弹窗向你确认。"))

        self.proactive_chk = QCheckBox("启用主动关怀（空闲时主动问候）")
        self.proactive_chk.setChecked(bool(self.cfg.get("proactive_enabled", True)))
        bform.addRow(self.proactive_chk)

        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(5, 240)
        self.idle_spin.setValue(int(self.cfg.get("proactive_idle_min", 30)))
        self.idle_spin.setSuffix(" 分钟")
        bform.addRow("空闲多久后关怀:", self.idle_spin)

        self.hourly_chk = QCheckBox("整点报时")
        self.hourly_chk.setChecked(bool(self.cfg.get("proactive_hourly", False)))
        bform.addRow(self.hourly_chk)

        self.sit_chk = QCheckBox("久坐提醒")
        self.sit_chk.setChecked(bool(self.cfg.get("proactive_sit_enabled", False)))
        bform.addRow(self.sit_chk)

        self.sit_spin = QSpinBox()
        self.sit_spin.setRange(20, 240)
        self.sit_spin.setValue(int(self.cfg.get("proactive_sit_min", 60)))
        self.sit_spin.setSuffix(" 分钟")
        bform.addRow("久坐多久提醒:", self.sit_spin)

        tabs.addTab(butler_tab, "管家")

        # --- 记忆标签页 ---
        mem_tab = QWidget()
        mform = QFormLayout(mem_tab)

        self.memory_chk = QCheckBox("启用长期记忆（跨会话记住你的信息）")
        self.memory_chk.setChecked(bool(self.cfg.get("enable_memory", True)))
        mform.addRow(self.memory_chk)

        self.mem_topk_spin = QSpinBox()
        self.mem_topk_spin.setRange(1, 10)
        self.mem_topk_spin.setValue(int(self.cfg.get("memory_topk", 4)))
        mform.addRow("每次注入记忆条数:", self.mem_topk_spin)
        mform.addRow(QLabel("记忆只存在本地 memory.db，不会上传；可随时查看或清空。"))

        mrow = QHBoxLayout()
        self.btn_view_mem = QPushButton("查看记忆…")
        self.btn_view_mem.clicked.connect(self._view_memories)
        self.btn_clear_mem = QPushButton("清空所有记忆")
        self.btn_clear_mem.clicked.connect(self._clear_memories)
        mrow.addWidget(self.btn_view_mem)
        mrow.addWidget(self.btn_clear_mem)
        mw = QWidget(); mw.setLayout(mrow)
        mform.addRow(mw)

        tabs.addTab(mem_tab, "记忆")

        # --- 通用标签页 ---
        gen_tab = QWidget()
        gform = QFormLayout(gen_tab)
        self.autostart_chk = QCheckBox("开机自动启动")
        self.autostart_chk.setChecked(bool(self.cfg.get("auto_start", False)))
        gform.addRow(self.autostart_chk)
        tabs.addTab(gen_tab, "通用")

        # --- 按钮 ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _wrap(self, layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _browse_img(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择角色图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            self.img_edit.setText(path)

    def _on_accept(self):
        self.cfg["api_key"] = self.api_key_edit.text().strip()
        self.cfg["model"] = self.model_combo.currentText()
        self.cfg["system_prompt"] = self.sys_prompt_edit.toPlainText().strip()
        self.cfg["character_image"] = self.img_edit.text().strip() or "assets/character.png"
        self.cfg["pet_size"] = self.size_slider.value()
        self.cfg["opacity"] = self.opacity_slider.value()
        self.cfg["hotkey"] = self.hotkey_edit.text().strip() or "<ctrl>+<shift>+<space>"
        self.cfg["enable_tts"] = self.tts_chk.isChecked()
        self.cfg["tts_voice"] = list(VOICES.values())[self.voice_combo.currentIndex()]
        self.cfg["enable_asr"] = self.asr_chk.isChecked()
        self.cfg["voice_hotkey"] = self.voice_hotkey_edit.text().strip() or "<ctrl>+<shift>+v"
        self.cfg["enable_tools"] = self.tools_chk.isChecked()
        self.cfg["proactive_enabled"] = self.proactive_chk.isChecked()
        self.cfg["proactive_idle_min"] = self.idle_spin.value()
        self.cfg["proactive_hourly"] = self.hourly_chk.isChecked()
        self.cfg["proactive_sit_enabled"] = self.sit_chk.isChecked()
        self.cfg["proactive_sit_min"] = self.sit_spin.value()
        self.cfg["enable_memory"] = self.memory_chk.isChecked()
        self.cfg["memory_topk"] = self.mem_topk_spin.value()
        self.cfg["auto_start"] = self.autostart_chk.isChecked()
        self.accept()

    def _view_memories(self):
        if self.memory is None:
            QMessageBox.information(self, "长期记忆", "记忆功能未就绪。")
            return
        rows = self.memory.all_memories()
        if not rows:
            QMessageBox.information(self, "长期记忆", "目前还没有记住任何信息。")
            return
        lines = "\n".join(f"#{i} [{t}]  {txt}" for i, txt, t in rows)
        box = QMessageBox(self)
        box.setWindowTitle(f"长期记忆（共 {len(rows)} 条）")
        box.setText(lines)
        box.exec()

    def _clear_memories(self):
        if self.memory is None:
            return
        if QMessageBox.question(self, "清空记忆", "确定删除所有长期记忆吗？此操作不可恢复。") == QMessageBox.Yes:
            self.memory.clear()
            QMessageBox.information(self, "已清空", "所有长期记忆已删除。")

    def result_config(self) -> dict:
        return self.cfg
