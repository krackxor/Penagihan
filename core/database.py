import sqlite3
import os
from flask import g

DATABASE_PATH = 'sunter.db'

def get_db_connection():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db(app):
    with app.app_context():
        db = get_db_connection()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
