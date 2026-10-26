import threading
from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QLineEdit,QListWidget
from core import continuity_runtime as shared
from core.continuity import store


class ContinuityPanel(QDialog):
    result=pyqtSignal(str)
    def __init__(self,parent):
        super().__init__(parent)
        self.setFont(QFont('Segoe UI',10));self.setWindowTitle('JARVIS — Um só assistente')
        self.setStyleSheet('QDialog{background:#030c13} QLabel{color:#b4e6eb} QPushButton,QLineEdit,QListWidget{padding:8px;color:#00e5ff;background:#102c38}')
        self.resize(620,650);layout=QVBoxLayout(self)
        info=QLabel('Este perfil compartilha memórias, tarefas pessoais e contexto de conversa. Cada dispositivo executa ações localmente; sincronizar não repete comandos. Use a VPN privada fora de casa. Arquivos, senhas, imagens e credenciais ficam em cada aparelho.');info.setWordWrap(True);layout.addWidget(info)
        cfg=shared.config()
        self.name=QLineEdit(cfg['name']);self.name.setPlaceholderText('Nome deste computador');layout.addWidget(self.name)
        self.url=QLineEdit(cfg.get('url',''));self.url.setPlaceholderText('http://IP-VPN-DO-PC-PRINCIPAL:8000');layout.addWidget(self.url)
        self.pin=QLineEdit();self.pin.setEchoMode(QLineEdit.EchoMode.Password);self.pin.setPlaceholderText('Chave de 8 caracteres mostrada no PC principal');layout.addWidget(self.pin)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.devices=QListWidget();layout.addWidget(self.devices)
        for label,callback in [('Este é meu PC principal',self.make_hub),('Conectar este PC ao meu principal',self.pair),('Sincronizar agora',lambda:self.work(shared.sync_once)),('Pausar sincronização neste PC',self.disable),('Revisar conflitos',self.conflicts)]:
            button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
        self.result.connect(self.message.setText)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(2000)
        self.refresh()
    def refresh(self):
        if not self.isVisible():return
        state=shared.status()
        self.devices.clear()
        for device in state['devices']:
            self.devices.addItem(f"{device['name']} • {device['platform']} • {'conectado recentemente' if device['online'] else 'offline'}")
        if not getattr(self,'working',False):self.message.setText(f"Perfil: {state['profile']}\nPapel: {state['role']} • {state['state']}\nPendências: {state['pending']} • conflitos: {state['conflicts']}")
    def work(self,fn):
        if getattr(self,'working',False):return
        self.working=True;self.message.setText('Conectando…')
        def run():
            try:fn();self.result.emit(shared.status()['state'])
            except Exception as exc:self.result.emit(str(exc))
            finally:self.working=False
        threading.Thread(target=run,daemon=True).start()
    def make_hub(self):
        cfg=shared.config()
        if cfg['role']=='replica' or store.pending():
            self.message.setText('Este PC já é uma réplica ou tem alterações pendentes. Não é possível promovê-lo automaticamente a outro perfil principal.');return
        shared.save_config({**cfg,'enabled':True,'role':'hub','name':self.name.text().strip() or cfg['name'],'profile':''})
        shared.start();self.work(shared.sync_once)
    def pair(self):
        url=self.url.text();pin=self.pin.text();name=self.name.text()
        self.pin.clear();shared.start();self.work(lambda:shared.pair(url,pin,name))
    def disable(self):
        cfg=shared.config();shared.save_config({**cfg,'enabled':False});self.refresh()
    def conflicts(self):
        dialog=QDialog(self);dialog.setWindowTitle('Conflitos — escolha uma versão');layout=QVBoxLayout(dialog)
        rows=QListWidget();layout.addWidget(rows)
        pending=[r for r in store.pending() if r['conflict']]
        for row in pending:rows.addItem(row['kind']+' / '+row['key']+' — local: '+str(row['value'])[:500]+' — principal: '+str(shared.remote_value(row['kind'],row['key']))[:500])
        def choose(choice):
            index=rows.currentRow()
            if index<0:return
            row=pending[index];self.work(lambda:shared.resolve(row['kind'],row['key'],choice));dialog.accept()
        for label,choice in [('Manter versão deste PC','local'),('Usar versão do PC principal','hub')]:
            button=QPushButton(label);button.clicked.connect(lambda _,c=choice:choose(c));layout.addWidget(button)
        dialog.resize(650,350);dialog.exec()
