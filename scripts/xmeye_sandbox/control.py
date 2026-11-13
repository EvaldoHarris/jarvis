"""Local setup form for the shared iCSee cloud runtime."""
import argparse
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from core.xmeye_runtime import (load_devices, validate, command, run_probe, sanitize, STATUSES,
                                save_device_credentials)
STATUS = ROOT / '.codex-attachments' / 'xmeye-probe-status.json'

def record(result):
    STATUS.parent.mkdir(exist_ok=True)
    # A diagnostic record, never camera credentials or images.
    safe = sanitize(result)
    STATUS.write_text(json.dumps(safe, indent=2), encoding='utf-8')
    return safe


def show_form():
    import tkinter as tk
    from tkinter import ttk
    from PIL import Image, ImageTk

    window = tk.Tk()
    record({'status': 'awaiting_credentials'})
    window.title('JARVIS — teste isolado iCSee')
    window.geometry('800x800')
    panel = ttk.Frame(window, padding=18)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='Teste de uma câmera pelo Cloud ID', font=('Segoe UI', 14)).pack(anchor='w')
    ttk.Label(panel, wraplength=750, text=(
        'Use as credenciais do DISPOSITIVO, não a senha da conta iCSee. '
        'Ao testar, elas serão enviadas ao SDK de nuvem dentro do contêiner. '
        'Ao clicar em Salvar no Jarvis e testar, as credenciais serão gravadas nas configurações locais do Jarvis. '
        'Não serão colocadas na linha de comando ou nos logs. '
        'O SDK tem acesso à rede; Docker limita o acesso ao PC, mas não comprova sua segurança.'
    )).pack(anchor='w', pady=10)
    devices = load_devices()
    ttk.Label(panel, text='Câmera cadastrada no portal').pack(anchor='w')
    labels = ['Informar manualmente'] + [
        f"{device['name']} (…{device['cloud_id'][-4:]})" for device in devices]
    chooser = ttk.Combobox(panel, state='readonly', values=labels, width=62)
    chooser.current(0)
    chooser.pack(anchor='w', pady=(0, 8))
    values = {}
    for key, label, default in [('cloud_id', 'Número de série / Cloud ID', ''),
                                 ('username', 'Usuário do dispositivo', 'admin'),
                                 ('password', 'Senha do dispositivo', '')]:
        ttk.Label(panel, text=label).pack(anchor='w')
        entry = ttk.Entry(panel, show='●' if key == 'password' else '', width=65)
        entry.insert(0, default)
        entry.pack(anchor='w', pady=(0, 8))
        values[key] = entry
    message = tk.StringVar(value='Pronto. Nenhuma conexão com câmera foi iniciada.')
    ttk.Label(panel, textvariable=message, wraplength=750).pack(anchor='w', pady=10)
    preview = ttk.Label(panel)
    preview.pack()
    completed = []
    active = [False]

    def select_camera(_event=None):
        if active[0]:
            return
        index = chooser.current() - 1
        values['password'].delete(0, 'end')
        for key in ('cloud_id', 'username'):
            values[key].delete(0, 'end')
            if index >= 0:
                values[key].insert(0, devices[index][key])
        if index < 0:
            values['username'].insert(0, 'admin')
        preview.config(image='')
        preview.image = None
        message.set('Câmera selecionada. Informe a senha do dispositivo para testar.')

    chooser.bind('<<ComboboxSelected>>', select_camera)
    if devices:
        message.set(f'{len(devices)} câmeras importadas do portal. Escolha pelo nome.')

    def start():
        if active[0]:
            return
        try:
            request = validate(dict(action='probe', **{k: e.get() for k, e in values.items()}))
        except ValueError as exc:
            message.set(str(exc))
            return
        values['password'].delete(0, 'end')
        active[0] = True
        record({'status': 'testing'})
        button.config(state='disabled')
        chooser.config(state='disabled')
        for entry in values.values():
            entry.config(state='disabled')
        preview.config(image='')
        preview.image = None
        message.set('Conectando dentro do contêiner; pode levar até 100 segundos...')

        def work():
            try:
                save_device_credentials(request)
                completed.append(run_probe(request))
            except Exception:
                completed.append({'status': 'controller_failed'})
            finally:
                request.clear()
        threading.Thread(target=work, daemon=True).start()

    def poll():
        if completed:
            result = completed.pop()
            safe = record(result)
            message.set(json.dumps(safe, ensure_ascii=False))
            encoded = result.get('jpeg_base64', '')
            if encoded and len(encoded) < 2_800_000:
                try:
                    image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
                    image.thumbnail((740, 300))
                    preview.image = ImageTk.PhotoImage(image)
                    preview.config(image=preview.image)
                except Exception:
                    message.set('Vídeo recebido, mas não foi possível exibir a imagem.')
            active[0] = False
            button.config(state='normal')
            chooser.config(state='readonly')
            for entry in values.values():
                entry.config(state='normal')
        window.after(250, poll)

    def close():
        if active[0]:
            message.set('Aguarde o teste terminar para fechar; há um limite de 100 segundos.')
            return
        window.destroy()

    button = ttk.Button(panel, text='Salvar no Jarvis e testar', command=start)
    button.pack(anchor='w', pady=8)
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(250, poll)
    window.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', choices=('load', 'init'))
    args = parser.parse_args()
    if args.check:
        print(json.dumps(record(run_probe({'action': args.check}))))
    else:
        show_form()
