import threading
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog
from core import google_workspace as google


class GooglePanel(QDialog):
    result=pyqtSignal(str)
    def __init__(self,parent):
        super().__init__(parent)
        self.setFont(QFont('Segoe UI',10))
        self.setStyleSheet('QDialog{background:#030c13} QLabel{color:#b4e6eb} QPushButton{padding:10px;color:#00e5ff;background:#102c38}')
        self.setWindowTitle('JARVIS — Google Agenda e Gmail')
        self.resize(540,300)
        layout=QVBoxLayout(self)
        self.status=QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        for label,callback in [('Importar cliente OAuth Google (.json)',self.import_file),('Conectar minha conta Google',self.connect)]:
            button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
        info=QLabel('Use um cliente OAuth do tipo Desktop, com Gmail API e Google Calendar API ativadas. A autorizacao ocorre no navegador do Google. Senha e tokens nao sao enviados ao modelo. Envios de email e criacao de eventos pedem confirmacao no PC.')
        info.setWordWrap(True);layout.addWidget(info)
        guide=QLabel('<a href="https://developers.google.com/workspace/gmail/api/quickstart/python#authorize_credentials_for_a_desktop_application">Como criar o cliente OAuth (instrucoes oficiais)</a><br>Ative Gmail API e Google Calendar API no mesmo projeto, crie o cliente Desktop, baixe o JSON e importe acima. Em projeto externo de testes, inclua sua conta entre os usuarios de teste.')
        guide.setOpenExternalLinks(True);guide.setWordWrap(True);layout.addWidget(guide)
        self.result.connect(self.status.setText)
        self._connecting=False
        self.result.connect(lambda text:setattr(self,'_connecting',False))
        self.refresh()
    def refresh(self):
        state=google.status()
        self.status.setText(f"Cliente OAuth: {'configurado' if state['client_configured'] else 'necessario'}\nConta: {'token salvo (conexao ainda nao testada)' if state['token_saved'] else 'nao conectada'}")
    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Cliente Google Desktop','','JSON (*.json)')
        if not path:return
        try: google.import_client(path);self.refresh()
        except Exception as exc:self.status.setText(str(exc))
    def connect(self):
        if self._connecting:return
        self._connecting=True
        self.status.setText('Conclua a autorizacao na pagina oficial do Google…')
        def work():
            try:google.connect();self.result.emit('Conta autorizada. Agenda e Gmail estao prontos para consulta.')
            except Exception as exc:self.result.emit(str(exc))
        threading.Thread(target=work,daemon=True).start()
