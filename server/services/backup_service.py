"""
Service de sauvegarde et restauration de la base de données
"""

import os
import shutil
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

from server.config import settings, get_backup_path


class BackupService:
    """Service de gestion des backups"""

    @staticmethod
    def get_backup_filename(prefix: str = "backup") -> str:
        """Génère un nom de fichier de backup avec timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.db"

    @staticmethod
    async def create_backup(description: str = "") -> Dict[str, Any]:
        """
        Crée une sauvegarde de la base de données.
        Retourne les informations sur le backup créé.
        """
        backup_dir = get_backup_path()
        db_path = Path(settings.database_path)

        if not db_path.exists():
            raise FileNotFoundError(f"Base de données non trouvée: {db_path}")

        # Générer le nom du backup
        backup_filename = BackupService.get_backup_filename()
        backup_path = backup_dir / backup_filename

        # Créer le backup (copie du fichier SQLite)
        # Note: Pour une copie cohérente en production, utiliser sqlite3 .backup
        shutil.copy2(db_path, backup_path)

        # Créer un fichier de métadonnées
        meta_path = backup_path.with_suffix(".json")
        meta = {
            "filename": backup_filename,
            "created_at": datetime.now().isoformat(),
            "description": description,
            "size_bytes": backup_path.stat().st_size,
            "original_db": str(db_path)
        }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "backup_file": backup_filename,
            "backup_path": str(backup_path),
            "size_bytes": meta["size_bytes"],
            "created_at": meta["created_at"]
        }

    @staticmethod
    async def list_backups() -> List[Dict[str, Any]]:
        """Liste tous les backups disponibles"""
        backup_dir = get_backup_path()
        backups = []

        for backup_file in backup_dir.glob("backup_*.db"):
            meta_file = backup_file.with_suffix(".json")
            meta = {}

            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    pass

            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size_bytes": backup_file.stat().st_size,
                "created_at": meta.get("created_at", datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()),
                "description": meta.get("description", "")
            })

        # Trier par date (plus récent en premier)
        backups.sort(key=lambda x: x["created_at"], reverse=True)

        return backups

    @staticmethod
    async def restore_backup(backup_filename: str) -> Dict[str, Any]:
        """
        Restaure la base de données depuis un backup.
        ATTENTION: Cette opération écrase la base actuelle!
        """
        backup_dir = get_backup_path()
        backup_path = backup_dir / backup_filename

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup non trouvé: {backup_filename}")

        db_path = Path(settings.database_path)

        # Créer un backup de sécurité avant restauration
        if db_path.exists():
            safety_backup = BackupService.get_backup_filename("pre_restore")
            shutil.copy2(db_path, backup_dir / safety_backup)

        # Restaurer le backup
        shutil.copy2(backup_path, db_path)

        return {
            "success": True,
            "restored_from": backup_filename,
            "restored_at": datetime.now().isoformat(),
            "safety_backup": safety_backup if db_path.exists() else None
        }

    @staticmethod
    async def delete_backup(backup_filename: str) -> bool:
        """Supprime un backup"""
        backup_dir = get_backup_path()
        backup_path = backup_dir / backup_filename

        if not backup_path.exists():
            return False

        # Supprimer le fichier de backup
        backup_path.unlink()

        # Supprimer le fichier de métadonnées s'il existe
        meta_path = backup_path.with_suffix(".json")
        if meta_path.exists():
            meta_path.unlink()

        return True

    @staticmethod
    async def cleanup_old_backups(retention_days: Optional[int] = None) -> int:
        """
        Supprime les backups plus anciens que retention_days.
        Retourne le nombre de backups supprimés.
        """
        if retention_days is None:
            retention_days = settings.backup_retention_days

        backup_dir = get_backup_path()
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0

        for backup_file in backup_dir.glob("backup_*.db"):
            # Extraire la date du nom de fichier ou utiliser mtime
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)

            if file_mtime < cutoff_date:
                await BackupService.delete_backup(backup_file.name)
                deleted_count += 1

        return deleted_count

    @staticmethod
    def get_database_size() -> int:
        """Retourne la taille de la base de données en octets"""
        db_path = Path(settings.database_path)
        if db_path.exists():
            return db_path.stat().st_size
        return 0

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Formate une taille en octets en format lisible"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
