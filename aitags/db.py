import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from .config import DEFAULTS


class Database:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS videos(
              path TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, identity TEXT NOT NULL DEFAULT '',
              size INTEGER NOT NULL, modified TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              result TEXT NOT NULL DEFAULT '{}', manual TEXT NOT NULL DEFAULT '[]',
              removed TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS identity_idx ON videos(identity);
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, root TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'running', created REAL NOT NULL, error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS directories(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL,
              path TEXT NOT NULL, page INTEGER NOT NULL DEFAULT 1, depth INTEGER NOT NULL DEFAULT 0,
              state TEXT NOT NULL DEFAULT 'queued', UNIQUE(run_id,path));
            CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL,
              path TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
              attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created REAL NOT NULL,
              UNIQUE(run_id,path));
            CREATE UNIQUE INDEX IF NOT EXISTS one_live_task ON tasks(path) WHERE state IN ('queued','running');
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, path TEXT NOT NULL,
              created REAL NOT NULL, state TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS aliases(alias TEXT PRIMARY KEY, canonical TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS favorites(tag TEXT PRIMARY KEY);
            PRAGMA user_version=1;
            ''')
            if 'content_type' not in {row['name'] for row in c.execute('PRAGMA table_info(runs)')}:
                c.execute("ALTER TABLE runs ADD COLUMN content_type TEXT NOT NULL DEFAULT 'auto'")
            if 'use_subtitles' not in {row['name'] for row in c.execute('PRAGMA table_info(runs)')}:
                c.execute("ALTER TABLE runs ADD COLUMN use_subtitles INTEGER NOT NULL DEFAULT 0")

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE tasks SET state='queued' WHERE state='running'")
            c.execute("UPDATE directories SET state='queued' WHERE state='running'")

    @contextmanager
    def connect(self):
        with self.lock:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

    def all(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as c:
            return c.execute(sql, args).lastrowid

    def settings(self):
        return {**DEFAULTS, **{r['key']: json.loads(r['value']) for r in self.all('SELECT * FROM settings')}}

    def save_settings(self, values):
        with self.connect() as c:
            for key, value in values.items():
                c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def event(self, path, state, message):
        self.execute('INSERT INTO history(path,created,state,message) VALUES (?,?,?,?)', (path, time.time(), state, message[:1000]))

    def public_video(self, row):
        result = json.loads(row['result'])
        aliases = {r['alias']: r['canonical'] for r in self.all('SELECT * FROM aliases')}
        manual = json.loads(row['manual'])
        removed = set(json.loads(row['removed']))
        ai = [t for t in result.get('tags', []) if t not in removed]
        def norm(tags):
            return list(dict.fromkeys(aliases.get(t, t) for t in tags))
        return {"path": row['path'], "status": row['status'], "result": result,
                "ai_tags": norm(ai), "manual_tags": norm(manual), "tags": norm(ai + manual),
                "removed": list(removed), "error": row['error'], "updated": row['updated']}
