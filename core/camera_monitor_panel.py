"""Local monitoring group editor. No connection starts until the user asks."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QComboBox, QPushButton, QListWidget, QListWidgetItem,
                             QSpinBox, QDoubleSpinBox, QFormLayout, QGroupBox, QDialog, QSlider)
from core.camera_monitor import hub, load_groups, save_groups, group_config, camera_catalog, ready_camera


class MonitorPanel(QWidget):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player, self.groups = player, load_groups()
        self.current_id = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet('''
            MonitorPanel {background:#000b13;border:1px solid #26859b;border-radius:12px;}
            QLabel,QGroupBox {color:#abd4e0;background:transparent;}
            QLineEdit,QComboBox,QListWidget,QSpinBox,QDoubleSpinBox {
                background:#00151e;color:#d8edf4;border:1px solid #245165;
                border-radius:6px;padding:6px;}
            QPushButton {background:#001820;color:#59e1ff;border:1px solid #286a80;
                border-radius:6px;padding:8px;}
            QPushButton:hover {background:#073340;}
            QComboBox QAbstractItemView {background:#00151e;color:#d8edf4;}
            QListWidget::indicator,QGroupBox::indicator {width:15px;height:15px;
                border:1px solid #4c8093;background:#00131e;}
            QListWidget::indicator:checked,QGroupBox::indicator:checked {background:#36d6ed;}
        ''')
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.addWidget(QLabel('MONITORAMENTO DE CÂMERAS'))
        hint = QLabel('Crie grupos e escolha as câmeras. Até três grupos simultâneos, em rodízio. Só detecções de pessoas e veículos vão à IA para análise e aviso. Iniciar fecha a prévia de vídeo para evitar conexões duplicadas.')
        hint.setWordWrap(True)
        root.addWidget(hint)
        row = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.setMinimumHeight(36)
        row.addWidget(self.selector, 1)
        new = QPushButton('NOVO GRUPO')
        new.clicked.connect(self.new_group)
        row.addWidget(new)
        root.addLayout(row)
        self.name = QLineEdit()
        self.name.setPlaceholderText('Nome do grupo: Sítio, Casa, Entrada…')
        root.addWidget(self.name)
        root.addWidget(QLabel('CÂMERAS DO GRUPO'))
        self.cameras = QListWidget()
        for camera in camera_catalog():
            text = camera['name'] + ('' if ready_camera(camera) else ' — sem credenciais')
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, camera['_settings_group'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.cameras.addItem(item)
        root.addWidget(self.cameras, 1)
        advanced = QGroupBox('AJUSTES DO MONITORAMENTO')
        advanced.setCheckable(True)
        advanced.setChecked(False)
        controls = QWidget()
        form = QFormLayout(controls)
        self.dwell = QSpinBox(); self.dwell.setRange(15, 300); self.dwell.setSuffix(' s')
        self.interval = QDoubleSpinBox(); self.interval.setRange(1., 10.); self.interval.setSuffix(' s')
        self.cooldown = QSpinBox(); self.cooldown.setRange(30, 3600); self.cooldown.setSuffix(' s')
        self.confidence = QDoubleSpinBox(); self.confidence.setRange(.3, .95); self.confidence.setSingleStep(.05)
        self.person_confidence = QDoubleSpinBox(); self.person_confidence.setRange(.60, .95); self.person_confidence.setSingleStep(.05)
        for title, widget in [('Tempo por câmera no rodízio', self.dwell), ('Intervalo entre análises locais', self.interval),
                              ('Intervalo mínimo de avisos', self.cooldown), ('Confiança mínima do detector', self.confidence),
                              ('Confiança mínima para pessoas', self.person_confidence)]:
            form.addRow(title, widget)
        layout = QVBoxLayout(advanced); layout.addWidget(controls)
        controls.setVisible(False)
        advanced.toggled.connect(controls.setVisible)
        root.addWidget(advanced)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(65)
        root.addWidget(self.status)
        row = QHBoxLayout()
        for title, callback in [('SALVAR', self.save), ('INICIAR GRUPO', self.start),
                                 ('PARAR GRUPO', self.stop), ('EXCLUIR', self.delete)]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        root.addLayout(row)
        row = QHBoxLayout()
        follow = QPushButton('ACOMPANHAR MONITORAMENTO')
        follow.clicked.connect(self.follow)
        root.addWidget(follow)
        recordings = QPushButton('GRAVAÇÕES DOS ALERTAS · 24 HORAS')
        recordings.clicked.connect(self.open_recordings)
        root.addWidget(recordings)
        stop_all = QPushButton('PARAR TODOS'); stop_all.clicked.connect(lambda: hub.stop())
        close = QPushButton('FECHAR'); close.clicked.connect(self.hide)
        row.addWidget(stop_all); row.addWidget(close); root.addLayout(row)
        self.selector.currentIndexChanged.connect(self.select)
        self.refresh_groups()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_status); self.timer.start(1000)

    def follow(self):
        if not getattr(self, 'viewer', None):
            self.viewer = MonitorViewer(self)
        self.viewer.preferred = self.current_id
        self.viewer.refresh()
        self.viewer.show()
        self.viewer.raise_()

    def open_recordings(self):
        if not getattr(self, 'recordings', None):
            self.recordings = RecordingsWindow(self)
        self.recordings.refresh()
        self.recordings.show()
        self.recordings.raise_()

    def refresh_groups(self, selected=None):
        self.selector.blockSignals(True)
        self.selector.clear()
        for group in self.groups:
            self.selector.addItem(group['name'], group['id'])
        self.selector.blockSignals(False)
        index = self.selector.findData(selected) if selected else 0
        if self.groups:
            self.selector.setCurrentIndex(max(0, index)); self.select(max(0, index))
        else:
            self.new_group()

    def new_group(self):
        self.current_id = None
        self.name.setText('')
        self.dwell.setValue(30); self.interval.setValue(1.5)
        self.cooldown.setValue(180); self.confidence.setValue(.55)
        self.person_confidence.setValue(.70)
        for index in range(self.cameras.count()):
            self.cameras.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.status.setText('Novo grupo. Dê um nome, marque as câmeras e salve.')

    def select(self, index):
        if not 0 <= index < len(self.groups):
            return
        group = self.groups[index]
        self.current_id = group['id']; self.name.setText(group['name'])
        for key in ('dwell', 'interval', 'cooldown', 'confidence', 'person_confidence'):
            getattr(self, key).setValue(group[key])
        for index in range(self.cameras.count()):
            item = self.cameras.item(index)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in group['cameras']
                               else Qt.CheckState.Unchecked)
        self.status.setText('Grupo salvo. Inicie para observar as câmeras em rodízio.')

    def save(self):
        try:
            selected = [self.cameras.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.cameras.count())
                        if self.cameras.item(i).checkState() == Qt.CheckState.Checked]
            group = group_config(dict(id=self.current_id or '', name=self.name.text(), cameras=selected,
                                      **{key: getattr(self, key).value() for key in ('dwell', 'interval', 'cooldown', 'confidence', 'person_confidence')}))
            groups = [g for g in self.groups if g['id'] != self.current_id] + [group]
            self.groups = save_groups(groups)
            self.refresh_groups(group['id'])
            self.status.setText('Grupo salvo. Alterações passam a valer ao iniciar novamente o grupo.')
            return group
        except ValueError as exc:
            self.status.setText(str(exc))

    def start(self):
        group = self.save()
        if group:
            try:
                result = hub.start(group, self.player)
                self.status.setText(f"Iniciando {len(result['monitored'])} câmera(s). Sem credenciais: {result['skipped']}.")
            except ValueError as exc:
                self.status.setText(str(exc))

    def stop(self):
        if self.current_id:
            hub.stop(self.current_id)
            self.status.setText('Grupo parado.')

    def delete(self):
        if self.current_id:
            hub.stop(self.current_id)
            self.groups = save_groups([g for g in self.groups if g['id'] != self.current_id])
            self.refresh_groups()

    def refresh_status(self):
        statuses = hub.status()
        selected = next((s for s in statuses if s['group_id'] == self.current_id), None)
        if selected:
            text = (f"{selected['state'].upper()} · {selected['current_camera'] or 'aguardando'}\n"
                    f"Quadros verificados: {selected['checked_frames']} · Avisos: {selected['alerts']}")
            if selected.get('last_error'):
                text += '\n' + selected['last_error']
            if selected['events']:
                text += '\nÚltimo evento: ' + selected['events'][-1]['summary']
            self.status.setText(text)


class MonitorAlertWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(800, 540)
        self.alert_id = None
        self.frames = []
        self.frame_bytes = 0
        self.position = 0.
        self.follow_live = True
        self.playing = True
        self.ended = False
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.image = QLabel()
        self.image.setMinimumSize(320, 180)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel()
        layout.addWidget(self.title)
        layout.addWidget(self.image, 1)
        layout.addWidget(self.status)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setAccessibleName('Posição na gravação')
        self.timeline.valueChanged.connect(self.scrub)
        layout.addWidget(self.timeline)
        row = QHBoxLayout()
        for label, callback in [('VOLTAR 5 s', lambda: self.seek(self.position - 5)),
                                ('PAUSAR / REPRODUZIR', self.toggle),
                                ('AVANÇAR 5 s', lambda: self.seek(self.position + 5)),
                                ('ÚLTIMA IMAGEM', self.latest)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        close = QPushButton('FECHAR ALERTA')
        close.clicked.connect(self.hide)
        layout.addWidget(close)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(250)

    def clear_image(self):
        self.image.clear()
        self.status.setText('Imagem expirada.')

    def begin(self, packet):
        self.alert_id = packet['alert_id']
        self.frames = []
        self.frame_bytes = 0
        self.position = 0.
        self.follow_live, self.playing, self.ended = True, True, False
        self.setWindowTitle('Jarvis — alerta de monitoramento')
        self.title.setText(f"{packet['group']} / {packet['camera']} · {', '.join(packet['labels'])}\n{packet['time']}")
        self.image.clear()
        self.show()
        self.raise_()
        self.activateWindow()

    def receive(self, packet):
        if packet['alert_id'] != self.alert_id:
            return
        if packet['final']:
            self.ended = True
        else:
            if packet['image'] and self.frame_bytes + len(packet['image']) <= 50_000_000:
                self.frames.append((float(packet['offset']), packet['image']))
                self.frame_bytes += len(packet['image'])
                if self.follow_live or len(self.frames) == 1:
                    self.position = float(packet['offset'])
        self.render()

    def render(self):
        if not self.frames:
            return
        self.position = max(self.frames[0][0], min(self.frames[-1][0], self.position))
        offset, jpeg = next((f for f in reversed(self.frames) if f[0] <= self.position), self.frames[0])
        pixmap = QPixmap()
        if pixmap.loadFromData(jpeg):
            self.image.setPixmap(pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        self.timeline.blockSignals(True)
        self.timeline.setRange(0, max(0, round((self.frames[-1][0] - self.frames[0][0]) * 1000)))
        self.timeline.setValue(round((self.position - self.frames[0][0]) * 1000))
        self.timeline.blockSignals(False)
        state = 'Pausado' if not self.playing else 'Reproduzindo'
        suffix = ' · captura encerrada' if self.ended else ' · recebendo imagens'
        self.status.setText(f'{state} · {self.position:+.1f} s / {self.frames[-1][0]:+.1f} s em relação à detecção{suffix}')

    def seek(self, position):
        self.follow_live = False
        self.position = position
        self.render()

    def scrub(self, value):
        if self.frames:
            self.playing = False
            self.seek(self.frames[0][0] + value / 1000)

    def toggle(self):
        self.follow_live = False
        self.playing = not self.playing
        if self.playing and self.ended and self.frames and self.position >= self.frames[-1][0]:
            self.position = self.frames[0][0]
        self.render()

    def latest(self):
        self.follow_live, self.playing = True, True
        if self.frames:
            self.position = self.frames[-1][0]
        self.render()

    def tick(self):
        if self.isVisible() and self.playing and not self.follow_live and self.frames:
            self.position += .25
            self.render()
            if self.ended and self.position >= self.frames[-1][0]:
                self.playing = False
                self.render()

    def hideEvent(self, event):
        self.playing = False
        super().hideEvent(event)


class RecordingsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Jarvis — gravações dos alertas')
        self.resize(650, 450)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Alertas salvos por até 24 horas · limite total de 1 GB · os mais antigos são removidos primeiro.'))
        self.items = QListWidget()
        self.items.itemDoubleClicked.connect(self.open_selected)
        layout.addWidget(self.items)
        open_button = QPushButton('ABRIR GRAVAÇÃO')
        open_button.clicked.connect(self.open_selected)
        layout.addWidget(open_button)
        refresh = QPushButton('ATUALIZAR LISTA')
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.message = QLabel()
        layout.addWidget(self.message)
        self.viewer = MonitorAlertWindow(self)

    def refresh(self):
        from core.monitor_recordings import list_recordings
        self.items.clear()
        for row in list_recordings():
            item = QListWidgetItem(f"{row['time']} · {row['group']} / {row['camera']} · {', '.join(row['labels'])}")
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.items.addItem(item)
        self.message.setText('Escolha uma gravação para assistir.' if self.items.count() else 'Nenhuma gravação disponível.')

    def open_selected(self, *_):
        from core.monitor_recordings import load
        item = self.items.currentItem()
        if item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        try:
            frames = load(row['alert_id'])
            if not frames:
                raise ValueError('Sem quadros disponíveis.')
            self.viewer.begin(row)
            self.viewer.frames = frames
            self.viewer.frame_bytes = sum(len(image) for _, image in frames)
            self.viewer.ended = True
            self.viewer.playing = True
            self.viewer.seek(frames[0][0])
        except (OSError, ValueError):
            self.message.setText('Gravação indisponível ou expirada. Atualize a lista.')


class MonitorViewer(QDialog):
    """Observe the existing feed without opening another camera connection."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Jarvis — acompanhar monitoramento')
        self.resize(860, 700)
        self.preferred = None
        self.setStyleSheet('QDialog {background:#000b13;} QLabel,QListWidget,QComboBox {background:#00151e;color:#d8edf4;}')
        layout = QVBoxLayout(self)
        self.selector = QComboBox()
        layout.addWidget(self.selector)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.image = QLabel('Nenhum grupo ativo.')
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(320, 180)
        layout.addWidget(self.image, 1)
        hint = QLabel('Exibe a câmera atual do rodízio. Fechar esta janela mantém o monitoramento ativo.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.events = QListWidget()
        self.events.setMaximumHeight(160)
        self.events.setWordWrap(True)
        layout.addWidget(self.events)
        close = QPushButton('FECHAR ACOMPANHAMENTO')
        close.clicked.connect(self.hide)
        layout.addWidget(close)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)

    def refresh(self):
        if not self.isVisible() and self.preferred is None:
            return
        statuses = hub.status()
        selected = self.preferred or self.selector.currentData()
        self.preferred = None
        choices = [(s['group'], s['group_id']) for s in statuses]
        existing = [(self.selector.itemText(i), self.selector.itemData(i)) for i in range(self.selector.count())]
        if choices != existing:
            self.selector.clear()
            for name, key in choices:
                self.selector.addItem(name, key)
        index = self.selector.findData(selected)
        if index >= 0:
            self.selector.setCurrentIndex(index)
        state = next((s for s in statuses if s['group_id'] == self.selector.currentData()), None)
        self.events.clear()
        if state is None:
            self.status.setText('Inicie um grupo no painel de monitoramento.')
            self.image.clear()
            self.image.setText('Nenhum grupo ativo.')
            return
        text = (f"{state['group']} · {state['state']} · {state['current_camera'] or 'aguardando câmera'}\n"
                f"Quadros verificados: {state['checked_frames']} · Avisos: {state['alerts']}")
        if state.get('last_error'):
            text += '\n' + state['last_error']
        self.status.setText(text)
        packet = hub.preview(state['group_id'])
        pixmap = QPixmap()
        if packet and pixmap.loadFromData(packet['jpeg']):
            self.image.setPixmap(pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        else:
            self.image.clear()
            self.image.setText('Aguardando imagem recente…' if state['running'] else 'Monitoramento parado.')
        for event in reversed(state['events']):
            self.events.addItem(f"{event['time']} · {event['camera']}\n{event['summary']}")
