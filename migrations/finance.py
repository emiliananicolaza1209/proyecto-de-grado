"""Migración 10, aditiva e idempotente. Conserva SQLite y datos de MOD02/03."""
import sqlite3

def upgrade(path):
    with sqlite3.connect(path) as c:
        if c.execute('SELECT 1 FROM schema_version WHERE version=10').fetchone():
            return
        with sqlite3.connect(str(path)+'.antes_MOD04.bak') as backup:
            c.backup(backup)
        c.execute('BEGIN')
        c.execute('''CREATE TABLE finance_day(id INTEGER PRIMARY KEY,date TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'Abierta',revision INTEGER NOT NULL DEFAULT 1,
          config JSON NOT NULL,snapshot JSON)''')
        c.execute('''CREATE TABLE finance_operation(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          token TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,description TEXT NOT NULL,seller TEXT NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>=0),minor_cost INTEGER NOT NULL DEFAULT 0 CHECK(minor_cost>=0),
          product_id INTEGER UNIQUE REFERENCES equipment(id),costs JSON NOT NULL,payments JSON NOT NULL,
          voided BOOLEAN NOT NULL DEFAULT 0)''')
        c.execute('CREATE INDEX ix_finance_operation_day_id ON finance_operation(day_id)')
        c.execute('''CREATE TABLE finance_supplier_payment(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          operation_id INTEGER NOT NULL REFERENCES finance_operation(id),cost_index INTEGER NOT NULL,
          amount INTEGER NOT NULL CHECK(amount>0),account TEXT NOT NULL,token TEXT NOT NULL UNIQUE)''')
        c.execute('''CREATE TABLE finance_audit(id INTEGER PRIMARY KEY,day_id INTEGER NOT NULL REFERENCES finance_day(id),
          action TEXT NOT NULL,reason TEXT NOT NULL,detail JSON NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('INSERT INTO schema_version(version) VALUES(10)')
