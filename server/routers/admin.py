"""
Routes d'administration du serveur
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from server.database import get_db
from server.models import User, UserRole, UserSession, ActivityLog
from server.services.auth_service import AuthService
from server.services.backup_service import BackupService
from server.services.stats_service import StatsService
from server.routers.auth import get_current_user, require_permission
from server.config import settings

router = APIRouter(prefix="/admin", tags=["Administration"])


# ============== Schémas Pydantic ==============

class UserCreate(BaseModel):
    """Création d'un utilisateur"""
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    role_name: str = "viewer"
    is_active: bool = True


class UserUpdate(BaseModel):
    """Mise à jour d'un utilisateur"""
    display_name: Optional[str] = None
    email: Optional[str] = None
    role_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_system_admin: Optional[bool] = None


class UserResponse(BaseModel):
    """Réponse utilisateur"""
    id: int
    username: str
    display_name: Optional[str]
    email: Optional[str]
    role: Optional[str]
    is_active: bool
    is_system_admin: bool
    last_login: Optional[datetime]
    created_at: datetime


class RoleResponse(BaseModel):
    """Réponse rôle"""
    id: int
    name: str
    description: Optional[str]


class BackupInfo(BaseModel):
    """Informations sur un backup"""
    filename: str
    size_bytes: int
    created_at: str
    description: str


# ============== Gestion des utilisateurs ==============

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Liste tous les utilisateurs"""
    query = select(User).order_by(User.username)

    if active_only:
        query = query.where(User.is_active == True)

    result = await db.execute(query)
    users = result.scalars().all()

    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role.name if u.role else None,
            "is_active": u.is_active,
            "is_system_admin": u.is_system_admin,
            "last_login": u.last_login,
            "created_at": u.created_at
        }
        for u in users
    ]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Crée un nouvel utilisateur"""

    # Normaliser le username
    normalized = AuthService.normalize_username(user_data.username)

    # Vérifier que l'utilisateur n'existe pas
    existing = await AuthService.get_user_by_username(db, normalized)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"L'utilisateur '{normalized}' existe déjà"
        )

    # Récupérer le rôle
    role_result = await db.execute(
        select(UserRole).where(UserRole.name == user_data.role_name)
    )
    role = role_result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle '{user_data.role_name}' non trouvé"
        )

    user = User(
        username=normalized,
        display_name=user_data.display_name or normalized,
        email=user_data.email,
        role=role,
        is_active=user_data.is_active
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="user",
        entity_id=str(user.id),
        details={"created_user": normalized}
    )
    db.add(log_entry)
    await db.commit()

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": role.name,
        "is_active": user.is_active,
        "is_system_admin": user.is_system_admin,
        "last_login": user.last_login,
        "created_at": user.created_at
    }


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Met à jour un utilisateur"""

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Utilisateur {user_id} non trouvé"
        )

    # Appliquer les modifications
    if user_data.display_name is not None:
        user.display_name = user_data.display_name
    if user_data.email is not None:
        user.email = user_data.email
    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    # Seul un admin système peut promouvoir un autre admin système
    if user_data.is_system_admin is not None:
        if not current_user.is_system_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seul un admin système peut modifier ce privilège"
            )
        user.is_system_admin = user_data.is_system_admin

    # Changer le rôle
    if user_data.role_name is not None:
        role_result = await db.execute(
            select(UserRole).where(UserRole.name == user_data.role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rôle '{user_data.role_name}' non trouvé"
            )
        user.role = role

    await db.commit()
    await db.refresh(user, ["role"])

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role.name if user.role else None,
        "is_active": user.is_active,
        "is_system_admin": user.is_system_admin,
        "last_login": user.last_login,
        "created_at": user.created_at
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Désactive un utilisateur"""

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas vous désactiver vous-même"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Utilisateur {user_id} non trouvé"
        )

    user.is_active = False
    await db.commit()

    # Forcer la déconnexion
    await AuthService.force_disconnect_user(db, user.username)

    return {"success": True, "message": f"Utilisateur {user.username} désactivé"}


# ============== Gestion des rôles ==============

@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Liste tous les rôles disponibles"""
    result = await db.execute(select(UserRole).order_by(UserRole.name))
    roles = result.scalars().all()

    return [
        {"id": r.id, "name": r.name, "description": r.description}
        for r in roles
    ]


# ============== Sessions ==============

@router.get("/sessions")
async def get_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_sauron"))
):
    """Liste les sessions actives"""
    return await AuthService.get_active_sessions(db)


@router.post("/sessions/disconnect/{username}")
async def force_disconnect(
    username: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Force la déconnexion d'un utilisateur"""
    count = await AuthService.force_disconnect_user(db, username)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="FORCE_DISCONNECT",
        entity_type="user",
        details={"disconnected_user": username, "sessions_closed": count}
    )
    db.add(log_entry)
    await db.commit()

    return {
        "success": True,
        "message": f"{count} session(s) fermée(s) pour {username}"
    }


# ============== Backups ==============

@router.get("/backups", response_model=List[BackupInfo])
async def list_backups(
    current_user: User = Depends(require_permission("admin_access"))
):
    """Liste les backups disponibles"""
    backups = await BackupService.list_backups()
    return [
        BackupInfo(
            filename=b["filename"],
            size_bytes=b["size_bytes"],
            created_at=b["created_at"],
            description=b.get("description", "")
        )
        for b in backups
    ]


@router.post("/backups")
async def create_backup(
    description: str = Query("", description="Description du backup"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Crée un nouveau backup"""
    result = await BackupService.create_backup(description)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="BACKUP_CREATE",
        details={"filename": result["backup_file"]}
    )
    db.add(log_entry)
    await db.commit()

    return result


@router.post("/backups/restore/{filename}")
async def restore_backup(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """
    Restaure un backup.
    ATTENTION: Cette opération redémarrera le serveur!
    """
    if not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un admin système peut restaurer un backup"
        )

    try:
        result = await BackupService.restore_backup(filename)

        # Logger l'action (sera dans le backup de sécurité)
        log_entry = ActivityLog(
            username=current_user.username,
            action_type="BACKUP_RESTORE",
            details={"filename": filename}
        )
        db.add(log_entry)
        await db.commit()

        return result
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete("/backups/{filename}")
async def delete_backup(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Supprime un backup"""
    success = await BackupService.delete_backup(filename)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup '{filename}' non trouvé"
        )

    return {"success": True, "message": f"Backup '{filename}' supprimé"}


@router.post("/backups/cleanup")
async def cleanup_old_backups(
    retention_days: int = Query(30, description="Nombre de jours de rétention"),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Supprime les backups plus anciens que N jours"""
    deleted = await BackupService.cleanup_old_backups(retention_days)
    return {
        "success": True,
        "deleted_count": deleted,
        "message": f"{deleted} backup(s) supprimé(s)"
    }


# ============== Configuration ==============

@router.get("/config")
async def get_server_config(
    current_user: User = Depends(require_permission("admin_access"))
):
    """Retourne la configuration actuelle du serveur"""
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "host": settings.host,
        "port": settings.port,
        "database_path": settings.database_path,
        "log_level": settings.log_level,
        "backup_dir": settings.backup_dir,
        "backup_retention_days": settings.backup_retention_days,
        "auto_backup_enabled": settings.auto_backup_enabled,
        "auto_backup_hour": settings.auto_backup_hour
    }


# ============== Sessions avancées ==============

@router.post("/sessions/{session_id}/kick")
async def kick_session_by_id(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Déconnecte une session spécifique par son ID"""
    result = await db.execute(
        select(UserSession).where(UserSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session non trouvée"
        )

    username = session.user.username if session.user else "unknown"
    await db.delete(session)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="SESSION_KICK",
        details={"kicked_user": username, "session_id": session_id}
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": f"Session de {username} terminée"}


@router.post("/sessions/kick-all")
async def kick_all_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin_access"))
):
    """Déconnecte toutes les sessions (sauf l'admin actuel)"""
    if not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un admin système peut déconnecter tout le monde"
        )

    # Supprimer toutes les sessions
    result = await db.execute(select(UserSession))
    sessions = result.scalars().all()
    count = len(sessions)

    for session in sessions:
        await db.delete(session)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="SESSION_KICK_ALL",
        details={"sessions_closed": count}
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": f"{count} session(s) fermée(s)"}


# ============== Reset password ==============

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_rights"))
):
    """Réinitialise le mot de passe d'un utilisateur"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    # Générer un nouveau mot de passe temporaire
    temp_password = AuthService.generate_temp_password()
    user.password_hash = AuthService.hash_password(temp_password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="PASSWORD_RESET",
        entity_type="user",
        entity_id=user_id,
        details={"target_user": user.username}
    )
    db.add(log_entry)
    await db.commit()

    return {
        "success": True,
        "temp_password": temp_password,
        "message": f"Mot de passe de {user.username} réinitialisé"
    }


# ============== Logs ==============

@router.get("/logs")
async def get_activity_logs(
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    username: Optional[str] = None,
    action_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_sauron"))
):
    """Récupère les logs d'activité avec filtres"""
    from datetime import datetime

    query = select(ActivityLog).order_by(ActivityLog.created_at.desc())

    if username:
        query = query.where(ActivityLog.username.ilike(f"%{username}%"))
    if action_type:
        query = query.where(ActivityLog.action_type == action_type)
    if date_start:
        start = datetime.fromisoformat(date_start)
        query = query.where(ActivityLog.created_at >= start)
    if date_end:
        end = datetime.fromisoformat(date_end + "T23:59:59")
        query = query.where(ActivityLog.created_at <= end)

    # Total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(ActivityLog)
    if username:
        count_query = count_query.where(ActivityLog.username.ilike(f"%{username}%"))
    if action_type:
        count_query = count_query.where(ActivityLog.action_type == action_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginated results
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "logs": [
            {
                "id": log.id,
                "username": log.username,
                "action_type": log.action_type,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "client_ip": log.client_ip,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }
