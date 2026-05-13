import os
from dotenv import load_dotenv

# Memuat variabel dari file .env
load_dotenv()

class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Celery
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND')
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY')
    
    # Storage (Secure Storage di luar folder static)
    # [cite: 1692, 1730]
    STORAGE_TMP = os.path.join(os.getcwd(), 'storage', 'tmp')
    STORAGE_ARCHIVE = os.path.join(os.getcwd(), 'storage', 'archive')
    
    # Max Upload Size (1GB)
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
