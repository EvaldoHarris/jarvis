"""Native task window; UI updates stay on the Qt thread."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
from core.task_control import panel_state, control


class TaskPanel(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFont(QFont('Segoe UI',10))
        self.setWindowTitle('JARVIS — Tarefas')
        self.resize(540, 480)
        self.setStyleSheet('QDialog{background:#030c13;color:#b4e6eb} QLabel,QTextEdit{color:#b4e6eb;background:#051a24} QPushButton{padding:10px;color:#00e5ff;background:#102c38}')
        layout = QVBoxLayout(self)
        self.title = QLabel('Tarefas')
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.steps = QTextEdit()
        self.steps.setReadOnly(True)
        layout.addWidget(self.steps)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.buttons = {}
        for action, text in [('pause', 'Pausar'), ('resume', 'Continuar'), ('cancel', 'Cancelar')]:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, value=action: self.act(value))
            self.buttons[action] = button
            row.addWidget(button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self):
        try:
            self.plan = panel_state()['plan']
            plan = self.plan
            states={'active':'Em andamento','paused':'Pausada','blocked':'Bloqueada','completed':'Concluida','cancelled':'Cancelada'}
            self.title.setText(f"{plan['objective']}\n{plan['completed']}/{plan['total']} — {states.get(plan['state'],plan['state'])}" if plan else 'Nenhuma tarefa registrada')
            self.steps.setPlainText('\n'.join(f"{'✓' if step['state']=='done' else '○'} {step['title']}" for step in plan['steps']) + '\n\n' + plan['reason'] if plan else '')
            for action, button in self.buttons.items():
                button.setEnabled(bool(plan) and (plan['state'] == 'active' if action == 'pause' else
                    plan['state'] in ('paused', 'blocked') if action == 'resume' else plan['state'] in ('active', 'paused', 'blocked')))
        except Exception as exc:
            self.title.setText(f'Nao foi possivel ler a tarefa: {exc}')

    def act(self, action):
        try:
            plan = control({'action': action, 'plan_id': self.plan['id'], 'revision': self.plan['revision']})
            parent = self.parent()
            if action in ('pause', 'cancel') and parent.on_interrupt:
                parent.on_interrupt()
            if action == 'resume' and parent.on_text_command:
                import threading
                threading.Thread(target=parent.on_text_command, args=(f"Continue o plano salvo {plan['id']}. Leia task_plan status e confira os aplicativos antes de prosseguir.",), daemon=True).start()
            self.refresh()
        except Exception as exc:
            self.title.setText(str(exc))

    def showEvent(self, event):
        self.timer.start(1000)
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
