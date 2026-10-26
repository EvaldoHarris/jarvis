"""One user's shared context. Stores data only; synchronization never executes actions."""
import json
import hashlib
import math
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from memory.config_manager import get_base_dir
ROOT = get_base_dir()
KINDS = {'memory', 'task', 'turn'}


class _Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class SharedStore:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'memory' / 'continuity.db')
        self.lock = threading.RLock()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10, factory=_Connection)
        db.executescript('''CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
            CREATE TABLE IF NOT EXISTS records(kind TEXT,key TEXT,value TEXT,revision INTEGER,PRIMARY KEY(kind,key));
            CREATE TABLE IF NOT EXISTS pending(kind TEXT,key TEXT,id TEXT,base INTEGER,value TEXT,conflict INTEGER DEFAULT 0,PRIMARY KEY(kind,key));
            CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY,result TEXT);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT,platform TEXT,last REAL);''')
        for key in ('profile', 'device'):
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', (key, str(uuid.uuid4())))
        db.commit()
        return db

    def identity(self):
        with self.lock, self.connect() as db:
            return dict(db.execute('SELECT k,v FROM meta'))

    @staticmethod
    def validate(kind, key, value):
        if kind not in KINDS or not isinstance(key, str) or not 1 <= len(key) <= 180:
            raise ValueError('Invalid shared record')
        if value is not None and not isinstance(value, dict):
            raise ValueError('Shared value must be an object or tombstone')
        if value is not None:
            if kind == 'memory' and (not isinstance(value.get('value'),str) or len(value['value']) > 2000):
                raise ValueError('Invalid shared memory text')
            if kind == 'task' and (not isinstance(value.get('title'),str) or not 1 <= len(value['title']) <= 500):
                raise ValueError('Invalid shared task title')
            if kind == 'turn' and (value.get('role') not in ('user','jarvis') or not isinstance(value.get('text'),str)
                                   or not isinstance(value.get('at'),(int,float)) or not math.isfinite(value['at'])):
                raise ValueError('Invalid conversation turn')
        if len(json.dumps(value)) > 16000:
            raise ValueError('Shared record too large')

    def rows(self, kind=None):
        with self.lock, self.connect() as db:
            sql, args = ('SELECT kind,key,value,revision FROM records', ())
            if kind:
                sql += ' WHERE kind=?'; args = (kind,)
            return [{'kind': k, 'key': key, 'value': json.loads(v), 'revision': rev}
                    for k, key, v, rev in db.execute(sql, args)]

    def put(self, kind, key, value, replica=False):
        self.validate(kind, key, value)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.lock, self.connect() as db:
            old = db.execute('SELECT value,revision FROM records WHERE kind=? AND key=?', (kind,key)).fetchone()
            if old and json.loads(old[0]) == value:
                return
            base = old[1] if old else 0
            if replica:
                previous = db.execute('SELECT base FROM pending WHERE kind=? AND key=?', (kind,key)).fetchone()
                db.execute('INSERT OR REPLACE INTO pending VALUES (?,?,?,?,?,0)', (kind,key,str(uuid.uuid4()),previous[0] if previous else base,encoded))
                rev = base
            else:
                rev = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM records').fetchone()[0]
            db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (kind,key,encoded,rev))

    def pending(self):
        with self.lock, self.connect() as db:
            return [{'kind':k,'key':key,'id':op,'base':base,'value':json.loads(v),'conflict':bool(c)}
                    for k,key,op,base,v,c in db.execute('SELECT * FROM pending')]

    def sync(self, body):
        ops = body.get('updates', [])
        if not isinstance(ops, list) or len(ops) > 250:
            raise ValueError('At most 250 mutations per sync')
        device = body.get('device', {})
        if not isinstance(device, dict) or not isinstance(device.get('id'), str) or not 1 <= len(device['id']) <= 80:
            raise ValueError('Device identity required')
        for op in ops:
            self.validate(op.get('kind'),op.get('key'),op.get('value'))
            if not isinstance(op.get('id'), str) or not 1 <= len(op['id']) <= 80 or type(op.get('base')) is not int or op['base'] < 0:
                raise ValueError('Mutation ID and revision required')
        results = []
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            profile = db.execute("SELECT v FROM meta WHERE k='profile'").fetchone()[0]
            if body.get('profile') not in (None, '', profile):
                raise ValueError('This is another Jarvis profile; reconnect explicitly')
            db.execute('INSERT OR REPLACE INTO devices VALUES (?,?,?,?)', (device['id'], str(device.get('name',''))[:100], str(device.get('platform',''))[:20], time.time()))
            for op in ops:
                fingerprint = hashlib.sha256(json.dumps(op,sort_keys=True).encode()).hexdigest()
                seen = db.execute('SELECT result FROM seen WHERE id=?', (op['id'],)).fetchone()
                if seen:
                    if json.loads(seen[0]).get('fingerprint') != fingerprint:
                        raise ValueError('Mutation ID reused with different content')
                    results.append(json.loads(seen[0])); continue
                old = db.execute('SELECT revision FROM records WHERE kind=? AND key=?', (op['kind'],op['key'])).fetchone()
                revision = old[0] if old else 0
                result = {'id':op['id'],'conflict':revision != op['base'],'fingerprint':fingerprint}
                if not result['conflict']:
                    revision = db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM records').fetchone()[0]
                    db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (op['kind'],op['key'],json.dumps(op['value'],ensure_ascii=False),revision))
                result['revision'] = revision
                db.execute('INSERT INTO seen VALUES (?,?)', (op['id'],json.dumps(result)))
                results.append(result)
            db.execute("DELETE FROM records WHERE kind='turn' AND key NOT IN (SELECT key FROM records WHERE kind='turn' ORDER BY revision DESC LIMIT 400)")
            records = [{'kind':k,'key':key,'value':json.loads(v),'revision':r} for k,key,v,r in db.execute('SELECT * FROM records')]
            devices = [{'id':d,'name':n,'platform':p,'online':time.time()-t<90} for d,n,p,t in db.execute('SELECT * FROM devices')]
            return {'ok':True,'profile':profile,'results':results,'records':records,'devices':devices}

    def apply(self, response):
        with self.lock, self.connect() as db:
            for result in response['results']:
                if result['conflict']:
                    db.execute('UPDATE pending SET conflict=1 WHERE id=?', (result['id'],))
                else:
                    db.execute('DELETE FROM pending WHERE id=?', (result['id'],))
            for row in response['records']:
                self.validate(row['kind'],row['key'],row['value'])
                waiting = db.execute('SELECT 1 FROM pending WHERE kind=? AND key=?', (row['kind'],row['key'])).fetchone()
                if not waiting:
                    db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (row['kind'],row['key'],json.dumps(row['value'],ensure_ascii=False),row['revision']))

    def resolve(self, kind, key, choice, hub_row):
        if choice not in ('local', 'hub'):
            raise ValueError('Choose local or hub explicitly')
        with self.lock, self.connect() as db:
            old = db.execute('SELECT value FROM pending WHERE kind=? AND key=? AND conflict=1', (kind,key)).fetchone()
            if not old:
                raise ValueError('No conflict for this record')
            if choice == 'local':
                db.execute('UPDATE pending SET id=?,base=?,conflict=0 WHERE kind=? AND key=?', (str(uuid.uuid4()),hub_row['revision'],kind,key))
            else:
                db.execute('DELETE FROM pending WHERE kind=? AND key=?', (kind,key))
                db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (kind,key,json.dumps(hub_row['value']),hub_row['revision']))


store = SharedStore()
