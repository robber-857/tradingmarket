"""Durable, expiring AI conversation history, independent of hosting vendor."""
from collections.abc import MutableMapping
import json
import time
from .database import database_url


class SessionStore(MutableMapping):
    def __init__(self, namespace):
        self.namespace, self.local = namespace, {}

    def __getitem__(self, key):
        if not database_url():
            return self.local[key]
        from .membership import database
        with database() as db:
            row = db.execute('SELECT payload FROM ai_sessions WHERE namespace=? AND id=? AND updated>?',
                             (self.namespace, key, time.time()-3600)).fetchone()
        if not row:
            raise KeyError(key)
        return json.loads(row['payload'])

    def __setitem__(self, key, value):
        if not database_url():
            self.local[key] = value
            return
        from .membership import database
        with database() as db:
            db.execute('DELETE FROM ai_sessions WHERE updated<?', (time.time()-3600,))
            db.execute('INSERT INTO ai_sessions VALUES (?,?,?,?) ON CONFLICT(namespace,id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated',
                       (self.namespace, key, json.dumps(value), time.time()))

    def __delitem__(self, key):
        if not database_url():
            del self.local[key]
            return
        from .membership import database
        with database() as db:
            db.execute('DELETE FROM ai_sessions WHERE namespace=? AND id=?', (self.namespace, key))

    def __iter__(self):
        if not database_url():
            return iter(self.local)
        # PostgreSQL expiry is handled on read/write, not a per-request full scan.
        return iter(())

    def __len__(self):
        return len(self.local) if not database_url() else 0

    def clear(self):
        if not database_url():
            self.local.clear()
            return
        from .membership import database
        with database() as db:
            db.execute('DELETE FROM ai_sessions WHERE namespace=?', (self.namespace,))
