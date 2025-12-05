"""
Routes pour les statistiques et le monitoring
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.models import User
from server.services.stats_service import StatsService
from server.routers.auth import get_current_user, require_permission

router = APIRouter(prefix="/stats", tags=["Statistiques"])


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_analyse"))
):
    """
    Retourne les statistiques pour le dashboard.

    Inclut:
    - Missions (aujourd'hui, créées, modifiées)
    - Voyages actifs
    - Chauffeurs actifs
    - Utilisateurs
    - Requêtes API et erreurs
    - Taille de la base de données
    """
    return await StatsService.get_dashboard_stats(db)


@router.get("/tables")
async def get_table_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Retourne le nombre d'enregistrements par table"""
    return await StatsService.get_table_counts(db)


@router.get("/activity/users")
async def get_activity_by_user(
    days: int = Query(7, description="Nombre de jours à analyser"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_sauron"))
):
    """Retourne l'activité par utilisateur sur les N derniers jours"""
    return await StatsService.get_activity_by_user(db, days)


@router.get("/api")
async def get_api_stats(
    days: int = Query(1, description="Nombre de jours à analyser"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Retourne les statistiques API détaillées"""
    return await StatsService.get_api_stats(db, days)


@router.get("/activity/recent")
async def get_recent_activity(
    limit: int = Query(50, le=500),
    username: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_sauron"))
):
    """
    Retourne les activités récentes.

    Filtres optionnels:
    - username: Filtrer par utilisateur
    - action_type: Filtrer par type d'action (LOGIN, CREATE, UPDATE, DELETE, etc.)
    """
    return await StatsService.get_recent_activity(db, limit, username, action_type)


@router.get("/users/{username}")
async def get_user_stats(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_sauron"))
):
    """Retourne les statistiques détaillées d'un utilisateur"""
    stats = await StatsService.get_user_stats(db, username)

    if not stats:
        return {"error": f"Utilisateur '{username}' non trouvé"}

    return stats
