# config.py
import os
from datetime import timedelta

class Config:
    # Flask Settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    DEBUG = os.environ.get('FLASK_DEBUG', True)
    
    # Database Settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///price_tracker.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # User Agents for different sites
    USER_AGENTS = {
        'default': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'amazon': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
        'trendyol': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'hepsiburada': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
    }
    
    # Price Check Settings
    PRICE_CHECK_INTERVAL = timedelta(minutes=5)
    REQUEST_TIMEOUT = 10  # seconds
    
    # Logging Configuration
    LOG_FILE = 'price_tracker.log'
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_LEVEL = 'INFO'
    
    # Site-specific settings
    SUPPORTED_SITES = ['amazon', 'trendyol', 'hepsiburada']
    
    # Notification Settings
    ENABLE_NOTIFICATIONS = True
    NOTIFICATION_SOUND = True