import threading
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QComboBox
from core import mail_accounts as mail


class MailPanel(QDialog):
    message = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setFont(QFont('Segoe UI', 10))
        self.setStyleSheet('QDialog{background:#030c13} QLabel{color:#b4e6eb} QComboBox{padding:6px;color:#e0f7fa;background:#0a1d26} '
                           'QPushButton{padding:10px;color:#00e5ff;background:#102c38}')
        self.setWindowTitle('JARVIS — Contas de email')
        self.resize(480, 320)
        layout = QVBoxLayout(self)
        self.status = QLabel(); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        for label, provider in [('Entrar com Google (Gmail)', 'gmail'), ('Entrar com Microsoft (Hotmail / Outlook)', 'outlook')]:
            button = QPushButton(label); button.clicked.connect(lambda _, p=provider: self.login(p)); layout.addWidget(button)
        self.accounts = QComboBox(); layout.addWidget(self.accounts)
        remove = QPushButton('Desconectar conta selecionada'); remove.clicked.connect(self.remove_account); layout.addWidget(remove)
        info = QLabel('O login abre no site oficial do Google ou da Microsoft. Sua senha nunca passa pelo Jarvis; '
                      'o acesso autorizado fica criptografado neste PC e pode ser revogado na sua conta. Envios pedem confirmacao.')
        info.setWordWrap(True); layout.addWidget(info)
        self.message.connect(self._show)
        self._busy = False
        self.refresh()

    def _show(self, text):
        self._busy = False
        self.refresh()
        self.status.setText(text)

    def refresh(self):
        try:
            rows = mail.status()['accounts']
        except Exception as exc:
            rows = []; self.status.setText(str(exc))
        self.accounts.clear()
        for row in rows:
            self.accounts.addItem(f"{row['address']} ({row['provider']})", row['address'])
        self.status.setText(f'{len(rows)} conta(s) conectada(s).' if rows else 'Nenhuma conta conectada.')

    def remove_account(self):
        address = self.accounts.currentData()
        if address:
            mail.remove(address); self.refresh()

    def login(self, provider):
        if self._busy:
            return
        self._busy = True
        self.status.setText('Conclua o login na janela do navegador…')

        def work():
            try: self.message.emit(f"{mail.login(provider)['connected']} conectado.")
            except Exception as exc: self.message.emit(str(exc))
        threading.Thread(target=work, daemon=True).start()
