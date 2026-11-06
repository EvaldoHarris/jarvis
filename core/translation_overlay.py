"""Qt-only caption window. Construct and update exclusively on the UI thread."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QCheckBox, QVBoxLayout, QApplication


class TranslationOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Jarvis — tradução ao vivo")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background:#131923; color:white; font-size:20px;")
        layout = QVBoxLayout(self)
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.audio = QCheckBox("Ouvir tradução ao vivo")
        self.audio.setChecked(True)
        self.audio.toggled.connect(self._audio_toggled)
        layout.addWidget(self.audio)
        button = QPushButton("Parar tradução")
        button.clicked.connect(self.close)
        layout.addWidget(button)
        self.resize(780, 170)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - 220)
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.caption.clear)

    def update_caption(self, text):
        if not text:
            self.hide()
            self.expiry.stop()
            return
        self.caption.setText(text)
        from core.live_translation import translation
        self.audio.blockSignals(True)
        self.audio.setChecked(translation.speech.enabled.is_set())
        self.audio.blockSignals(False)
        self.show()
        self.expiry.start(15000)

    def _audio_toggled(self, enabled):
        from core.live_translation import translation
        translation.set_audio(enabled)

    def closeEvent(self, event):
        from core.live_translation import translation
        translation.stop()
        self.expiry.stop()
        super().closeEvent(event)
