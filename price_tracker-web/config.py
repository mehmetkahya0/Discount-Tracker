# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///price_tracker.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    USER_AGENTS = {
        'default': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
    }