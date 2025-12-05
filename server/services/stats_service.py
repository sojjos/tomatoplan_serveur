"""
Service de statistiques et monitoring
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from server.models import Mission, Voyage, Chauffeur, User, ActivityLog, ApiRequestLog
from server.services.backup_service import BackupService


class StatsService:
    """Service de statistiques pour le dashboard admin"""

    @staticmethod
    async def get_dashboard_stats(db: AsyncSession) -> Dict[str, Any]:
        """Retourne les statistiques pour le dashboard"""

        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        # Statistiques des missions
        missions_today = await db.execute(
            select(func.count(Mission.id)).where(Mission.date_mission == today)
        )
        missions_today_count = missions_today.scalar() or 0

        # Missions créées aujourd'hui
        missions_created_today = await db.execute(
            select(func.count(Mission.id)).where(
                and_(
                    Mission.created_at >= today_start,
                    Mission.created_at <= today_end
                )
            )
        )
        missions_created_count = missions_created_today.scalar() or 0

        # Missions modifiées aujourd'hui
        missions_modified_today = await db.execute(
            select(func.count(Mission.id)).where(
                and_(
                    Mission.updated_at >= today_start,
                    Mission.updated_at <= today_end,
                    Mission.created_at < today_start  # Exclure les nouvelles créations
                )
            )
        )
        missions_modified_count = missions_modified_today.scalar() or 0

        # Nombre de voyages actifs
        voyages_actifs = await db.execute(
            select(func.count(Voyage.id)).where(Voyage.is_active == True)
        )
        voyages_count = voyages_actifs.scalar() or 0

        # Nombre de chauffeurs actifs
        chauffeurs_actifs = await db.execute(
            select(func.count(Chauffeur.id)).where(Chauffeur.is_active == True)
        )
        chauffeurs_count = chauffeurs_actifs.scalar() or 0

        # Nombre d'utilisateurs
        users_count_result = await db.execute(
            select(func.count(User.id))
        )
        users_count = users_count_result.scalar() or 0

        # Requêtes API aujourd'hui
        api_requests_today = await db.execute(
            select(func.count(ApiRequestLog.id)).where(
                ApiRequestLog.created_at >= today_start
            )
        )
        api_requests_count = api_requests_today.scalar() or 0

        # Erreurs aujourd'hui
        errors_today = await db.execute(
            select(func.count(ApiRequestLog.id)).where(
                and_(
                    ApiRequestLog.created_at >= today_start,
                    ApiRequestLog.status_code >= 400
                )
            )
        )
        errors_count = errors_today.scalar() or 0

        # Taille de la base de données
        db_size = BackupService.get_database_size()

        return {
            "missions": {
                "today": missions_today_count,
                "created_today": missions_created_count,
                "modified_today": missions_modified_count
            },
            "voyages": {
                "active": voyages_count
            },
            "chauffeurs": {
                "active": chauffeurs_count
            },
            "users": {
                "total": users_count
            },
            "api": {
                "requests_today": api_requests_count,
                "errors_today": errors_count
            },
            "database": {
                "size_bytes": db_size,
                "size_formatted": BackupService.format_size(db_size)
            },
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    async def get_table_counts(db: AsyncSession) -> Dict[str, int]:
        """Retourne le nombre d'enregistrements par table"""

        tables = {
            "users": User,
            "missions": Mission,
            "voyages": Voyage,
            "chauffeurs": Chauffeur,
            "activity_logs": ActivityLog,
            "api_request_logs": ApiRequestLog
        }

        counts = {}
        for name, model in tables.items():
            result = await db.execute(select(func.count(model.id)))
            counts[name] = result.scalar() or 0

        return counts

    @staticmethod
    async def get_activity_by_user(
        db: AsyncSession,
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Retourne l'activité par utilisateur sur les N derniers jours"""

        cutoff = datetime.now() - timedelta(days=days)

        result = await db.execute(
            select(
                ActivityLog.username,
                func.count(ActivityLog.id).label("action_count")
            )
            .where(ActivityLog.created_at >= cutoff)
            .group_by(ActivityLog.username)
            .order_by(func.count(ActivityLog.id).desc())
        )

        return [
            {"username": row.username, "action_count": row.action_count}
            for row in result
        ]

    @staticmethod
    async def get_api_stats(
        db: AsyncSession,
        days: int = 1
    ) -> Dict[str, Any]:
        """Retourne les statistiques API détaillées"""

        cutoff = datetime.now() - timedelta(days=days)

        # Requêtes par endpoint
        requests_by_path = await db.execute(
            select(
                ApiRequestLog.path,
                func.count(ApiRequestLog.id).label("count")
            )
            .where(ApiRequestLog.created_at >= cutoff)
            .group_by(ApiRequestLog.path)
            .order_by(func.count(ApiRequestLog.id).desc())
            .limit(20)
        )

        # Distribution des codes de statut
        status_distribution = await db.execute(
            select(
                ApiRequestLog.status_code,
                func.count(ApiRequestLog.id).label("count")
            )
            .where(ApiRequestLog.created_at >= cutoff)
            .group_by(ApiRequestLog.status_code)
            .order_by(ApiRequestLog.status_code)
        )

        # Temps de réponse moyen
        avg_response_time = await db.execute(
            select(func.avg(ApiRequestLog.response_time_ms))
            .where(
                and_(
                    ApiRequestLog.created_at >= cutoff,
                    ApiRequestLog.response_time_ms.isnot(None)
                )
            )
        )

        return {
            "by_endpoint": [
                {"path": row.path, "count": row.count}
                for row in requests_by_path
            ],
            "by_status": [
                {"status": row.status_code, "count": row.count}
                for row in status_distribution
            ],
            "avg_response_time_ms": round(avg_response_time.scalar() or 0, 2)
        }

    @staticmethod
    async def get_recent_activity(
        db: AsyncSession,
        limit: int = 50,
        username: Optional[str] = None,
        action_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retourne les activités récentes"""

        query = select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)

        if username:
            query = query.where(ActivityLog.username == username.upper())

        if action_type:
            query = query.where(ActivityLog.action_type == action_type)

        result = await db.execute(query)
        logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "username": log.username,
                "action_type": log.action_type,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "client_ip": log.client_ip,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]

    @staticmethod
    async def get_user_stats(
        db: AsyncSession,
        username: str
    ) -> Optional[Dict[str, Any]]:
        """Retourne les statistiques détaillées d'un utilisateur"""

        user_result = await db.execute(
            select(User).where(User.username == username.upper())
        )
        user = user_result.scalar_one_or_none()

        if not user:
            return None

        # Nombre total d'actions
        total_actions = await db.execute(
            select(func.count(ActivityLog.id))
            .where(ActivityLog.username == username.upper())
        )

        # Actions par type
        actions_by_type = await db.execute(
            select(
                ActivityLog.action_type,
                func.count(ActivityLog.id).label("count")
            )
            .where(ActivityLog.username == username.upper())
            .group_by(ActivityLog.action_type)
        )

        # Dernière activité
        last_activity = await db.execute(
            select(ActivityLog)
            .where(ActivityLog.username == username.upper())
            .order_by(ActivityLog.created_at.desc())
            .limit(1)
        )
        last_log = last_activity.scalar_one_or_none()

        return {
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.name if user.role else "viewer",
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "total_actions": total_actions.scalar() or 0,
            "actions_by_type": {
                row.action_type: row.count
                for row in actions_by_type
            },
            "last_activity": last_log.created_at.isoformat() if last_log else None
        }
