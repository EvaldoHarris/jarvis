import io
import ipaddress
import json
import socket
from pathlib import Path

from PyQt6.QtCore import pyqtSignal,Qt,QTimer
import threading
from PyQt6.QtGui import QFont,QPixmap
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,QListWidget,QFileDialog,QScrollArea,QWidget
from core import direct_secure as direct


def addresses():
    import psutil
    result=[]
    for rows in psutil.net_if_addrs().values():
        for row in rows:
            try:ip=ipaddress.ip_address(row.address.split('%')[0])
            except ValueError:continue
            if not ip.is_loopback and not ip.is_link_local and not ip.is_multicast:
                result.append(str(ip))
    return list(dict.fromkeys(result))


class DirectPanel(QDialog):
    result=pyqtSignal(str)
    def __init__(self,parent):
        super().__init__(parent);self.setFont(QFont('Segoe UI',10));self.setWindowTitle('JARVIS — Canal direto protegido')
        self.setStyleSheet('QDialog,QWidget#direct-content{background:#030c13} QLabel{color:#b4e6eb} QPushButton,QLineEdit,QComboBox,QListWidget{padding:7px;color:#00e5ff;background:#102c38}')
        self.resize(670,780)
        root=QVBoxLayout(self);self.scroll=QScrollArea();self.scroll.setWidgetResizable(True)
        content=QWidget();content.setObjectName('direct-content');layout=QVBoxLayout(content)
        self.scroll.setWidget(content);root.addWidget(self.scroll)
        text=QLabel('Teste local primeiro. Esta porta oferece somente sincronização com certificado por dispositivo. Não expõe o painel, login, arquivos ou execução de comandos. As regras de roteador/firewall não são alteradas por esta tela.');text.setWordWrap(True);layout.addWidget(text)
        ips=addresses();private=next((ip for ip in ips if ':' not in ip),'127.0.0.1')
        self.bind=QComboBox();self.bind.addItem('Apenas este PC — 127.0.0.1','127.0.0.1')
        for ip in ips:self.bind.addItem(('Rede local — ' if ':' not in ip else 'IPv6 — ')+ip,ip)
        if private!='127.0.0.1':self.bind.setCurrentIndex(1+ips.index(private))
        layout.addWidget(self.bind)
        label=QLabel('Endereço HTTPS usado pelos aparelhos (pode ser diferente da interface local):');label.setWordWrap(True);layout.addWidget(label)
        self.endpoint=QLineEdit(f'https://{private}:9443');layout.addWidget(self.endpoint)
        self.info=QLabel('Escolha a interface, prepare o listener e reinicie o Jarvis. Depois gere o convite.');self.info.setWordWrap(True);layout.addWidget(self.info)
        self.qr=QLabel();self.qr.setMinimumSize(1,1);self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter);self.qr.hide();layout.addWidget(self.qr)
        self.devices=QListWidget();layout.addWidget(self.devices)
        for name,fn in [('Preparar listener na interface escolhida',self.enable),('Gerar convite de 10 minutos',self.invite),('Salvar convite .jarvis',self.export),('Revogar aparelho selecionado',self.revoke),('Desativar listener no próximo reinício',self.disable)]:
            button=QPushButton(name);button.clicked.connect(fn);layout.addWidget(button)
        from core import direct_client
        self.client_url=QLineEdit(direct_client.endpoint());self.client_url.setPlaceholderText('Destino HTTPS do PC principal, se este for um PC cliente');layout.addWidget(self.client_url)
        for label,callback in [('Conectar este PC usando convite .jarvis',self.join),('Salvar destino HTTPS do PC cliente',self.client_endpoint)]:
            button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
        self.result.connect(self.info.setText)
        self.ticket='';self.ips=ips;self.private=private;self.refresh()
        self.timer=QTimer(self);self.timer.timeout.connect(lambda:self.refresh() if self.isVisible() else None);self.timer.start(2000)
    def refresh(self):
        selected=self.devices.currentRow()
        ident=self.rows[selected]['id'] if hasattr(self,'rows') and 0<=selected<len(self.rows) else None
        self.devices.clear()
        self.rows=direct.authority.devices()
        for i,row in enumerate(self.rows):
            self.devices.addItem(row['name']+' — '+('revogado' if row['revoked'] else 'autorizado'))
            if row['id']==ident:self.devices.setCurrentRow(i)
    def enable(self):
        try:
            host=self.bind.currentData()
            from urllib.parse import urlparse
            target=urlparse(self.endpoint.text().strip())
            if target.scheme!='https' or not target.hostname or target.port!=9443:
                raise ValueError('Use https://IP:9443 ou https://[IPv6]:9443')
            direct.authority.initialize(self.ips+[target.hostname])
            direct.ROOT.mkdir(parents=True,exist_ok=True)
            (direct.ROOT/'listener.json').write_text(json.dumps({'enabled':True,'host':host,'port':9443}))
            self.info.setText('Listener preparado. Reinicie o Jarvis para escutar nesta interface. Acesso externo ainda depende de teste fora de casa e regras específicas de firewall/roteador. A porta HTTP 8000 não deve ser publicada.')
        except Exception as exc:self.info.setText(str(exc))
    def invite(self):
        try:
            from dashboard.server import PORT
            host=self.bind.currentData()
            if host in ('127.0.0.1','::1'):host=self.private
            host=f'[{host}]' if ':' in host else host
            self.ticket=direct.authority.ticket(f'http://{host}:{PORT}/api/direct/enroll',self.endpoint.text().strip())
            import qrcode
            code=qrcode.QRCode(box_size=7,border=4,error_correction=qrcode.constants.ERROR_CORRECT_M)
            code.add_data(direct.compact_invitation(self.ticket));code.make(fit=True)
            image=code.make_image(fill_color='black',back_color='white');buffer=io.BytesIO();image.save(buffer,format='PNG')
            picture=QPixmap();picture.loadFromData(buffer.getvalue());self.qr.setFixedSize(picture.size());self.qr.setPixmap(picture);self.qr.show()
            QTimer.singleShot(0,lambda:self.scroll.ensureWidgetVisible(self.qr))
            self.info.setText('No Android: Configurações → Canal direto protegido. Escaneie este QR ou importe o arquivo .jarvis. Faça o primeiro pareamento na rede local. O convite é secreto, expira em 10 minutos e só aceita um aparelho.')
        except Exception as exc:self.info.setText(str(exc))
    def export(self):
        if not self.ticket:self.invite()
        if not self.ticket:return
        filename,_=QFileDialog.getSaveFileName(self,'Convite de pareamento','','Convite Jarvis (*.jarvis)')
        if filename:Path(filename).write_text(self.ticket,encoding='utf-8')
    def revoke(self):
        index=self.devices.currentRow()
        if index>=0:
            direct.authority.revoke(self.rows[index]['id']);self.refresh();self.info.setText('Revogado: os próximos pedidos deste aparelho serão recusados, inclusive em conexão TLS já aberta.')
    def disable(self):
        cfg=direct.settings();cfg['enabled']=False
        direct.ROOT.mkdir(parents=True,exist_ok=True);(direct.ROOT/'listener.json').write_text(json.dumps(cfg));self.info.setText('Listener será desativado ao reiniciar o Jarvis.')

    def join(self):
        filename,_=QFileDialog.getOpenFileName(self,'Convite do PC principal','','Convite Jarvis (*.jarvis)')
        if not filename:return
        if Path(filename).stat().st_size>16000:self.info.setText('Convite inválido');return
        ticket=Path(filename).read_text(encoding='utf-8')
        self.info.setText('Pareando por TLS…')
        def run():
            try:
                from core.continuity_runtime import join_direct
                join_direct(ticket,socket.gethostname());self.result.emit('Este PC entrou no perfil pelo canal direto. O destino externo pode ser atualizado no campo abaixo.')
            except Exception as exc:self.result.emit(str(exc))
        threading.Thread(target=run,daemon=True).start()
    def client_endpoint(self):
        try:
            from core import direct_client
            direct_client.set_endpoint(self.client_url.text().strip());self.info.setText('Destino salvo. O certificado continuará sendo verificado; não há troca automática para HTTP.')
        except Exception as exc:self.info.setText(str(exc))
