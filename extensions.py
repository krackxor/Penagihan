from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from flask_caching import Cache

# Inisialisasi objek tanpa mengikatnya ke aplikasi Flask dulu
db = SQLAlchemy()
celery = Celery()
cache = Cache()
