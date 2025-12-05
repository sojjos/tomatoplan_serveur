"""
Configuration du serveur TomatoPlan
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    """Configuration principale du serveur"""

    # Serveur
    app_name: str = "TomatoPlan Server"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Base de données
    database_path: str = "./data/tomatoplan.db"

    # Sécurité
    secret_key: str = secrets.token_urlsafe(32)
    access_token_expire_minutes: int = 480  # 8 heures

    # Admin par défaut (utilisé uniquement à l'initialisation)
    default_admin_username: str = "ADMIN"
    default_admin_enabled: bool = True

    # Logs
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    log_file: str = "./logs/server.log"

    # Backup
    backup_dir: str = "./backups"
    backup_retention_days: int = 30
    auto_backup_enabled: bool = True
    auto_backup_hour: int = 2  # Heure du backup automatique (2h du matin)

    # Import de données JSON existantes
    json_import_dir: Optional[str] = None

    class Config:
        env_file = ".env"
        env_prefix = "TOMATOPLAN_"


# Instance globale de configuration
settings = Settings()


def get_database_url() -> str:
    """Retourne l'URL de connexion SQLite"""
    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def get_log_path() -> Path:
    """Retourne le chemin du fichier de logs"""
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def get_backup_path() -> Path:
    """Retourne le chemin du dossier de backups"""
    backup_path = Path(settings.backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path
