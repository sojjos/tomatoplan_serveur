"""
Service d'authentification basé sur l'utilisateur Windows
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from jose import jwt, JWTError

from server.config import settings
from server.models.user import User, UserRole, UserSession


class AuthService:
    """Service d'authentification et gestion des sessions"""

    ALGORITHM = "HS256"

    @staticmethod
    def normalize_username(username: str) -> str:
        """
        Normalise le nom d'utilisateur Windows.
        Accepte: DOMAIN\\username, DOMAIN/username, username
        Retourne: USERNAME (majuscules, sans domaine)
        """
        # Nettoyer le nom
        username = username.strip()

        # Extraire le nom sans le domaine
        if "\\" in username:
            username = username.split("\\")[-1]
        elif "/" in username:
            username = username.split("/")[-1]

        return username.upper()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Récupère un utilisateur par son nom"""
        normalized = AuthService.normalize_username(username)
        result = await db.execute(
            select(User).where(User.username == normalized)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_user(
        db: AsyncSession,
        username: str,
        client_info: Optional[Dict[str, Any]] = None
    ) -> tuple[User, bool]:
        """
        Récupère ou crée un utilisateur.
        Retourne (user, created) où created indique si l'utilisateur a été créé.
        """
        normalized = AuthService.normalize_username(username)
        user = await AuthService.get_user_by_username(db, normalized)

        if user:
            # Mettre à jour last_login
            user.last_login = datetime.utcnow()
            await db.commit()
            return user, False

        # Créer le nouvel utilisateur avec le rôle par défaut (viewer)
        default_role = await db.execute(
            select(UserRole).where(UserRole.name == "viewer")
        )
        role = default_role.scalar_one_or_none()

        user = User(
            username=normalized,
            display_name=normalized,
            role=role,
            is_active=True,
            last_login=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return user, True

    @staticmethod
    async def authenticate_windows_user(
        db: AsyncSession,
        username: str,
        client_ip: Optional[str] = None,
        client_hostname: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Authentifie un utilisateur Windows.
        Vérifie que l'utilisateur existe et est actif.
        Crée une session et retourne un token JWT.
        """
        user = await AuthService.get_user_by_username(db, username)

        if not user:
            # En mode strict, refuser les utilisateurs non enregistrés
            # Pour le setup initial, on peut permettre la création automatique
            if settings.default_admin_enabled:
                user, _ = await AuthService.get_or_create_user(db, username)
            else:
                return None

        if not user.is_active:
            return None

        # Créer une nouvelle session
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

        session = UserSession(
            session_id=session_id,
            user_id=user.id,
            client_ip=client_ip,
            client_hostname=client_hostname,
            user_agent=user_agent,
            expires_at=expires_at
        )
        db.add(session)

        # Mettre à jour last_login
        user.last_login = datetime.utcnow()

        await db.commit()

        # Générer le token JWT
        token_data = {
            "sub": user.username,
            "session_id": session_id,
            "exp": expires_at
        }
        token = jwt.encode(token_data, settings.secret_key, algorithm=AuthService.ALGORITHM)

        # Charger le rôle pour les permissions
        await db.refresh(user, ["role"])

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expires_at.isoformat(),
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.name if user.role else "viewer",
                "is_system_admin": user.is_system_admin,
                "permissions": AuthService.get_user_permissions(user)
            }
        }

    @staticmethod
    def get_user_permissions(user: User) -> Dict[str, bool]:
        """Retourne les permissions de l'utilisateur"""
        if user.is_system_admin:
            # Admin système a toutes les permissions
            return {
                "view_planning": True,
                "edit_planning": True,
                "view_drivers": True,
                "manage_drivers": True,
                "edit_driver_planning": True,
                "manage_rights": True,
                "manage_voyages": True,
                "generate_planning": True,
                "edit_past_planning": True,
                "edit_past_planning_advanced": True,
                "view_finance": True,
                "manage_finance": True,
                "view_analyse": True,
                "view_sauron": True,
                "send_announcements": True,
                "manage_announcements_config": True,
                "admin_access": True
            }

        if not user.role:
            return {"view_planning": True}  # Permissions minimales

        return {
            "view_planning": user.role.view_planning,
            "edit_planning": user.role.edit_planning,
            "view_drivers": user.role.view_drivers,
            "manage_drivers": user.role.manage_drivers,
            "edit_driver_planning": user.role.edit_driver_planning,
            "manage_rights": user.role.manage_rights,
            "manage_voyages": user.role.manage_voyages,
            "generate_planning": user.role.generate_planning,
            "edit_past_planning": user.role.edit_past_planning,
            "edit_past_planning_advanced": user.role.edit_past_planning_advanced,
            "view_finance": user.role.view_finance,
            "manage_finance": user.role.manage_finance,
            "view_analyse": user.role.view_analyse,
            "view_sauron": user.role.view_sauron,
            "send_announcements": user.role.send_announcements,
            "manage_announcements_config": user.role.manage_announcements_config,
            "admin_access": user.role.admin_access
        }

    @staticmethod
    async def validate_token(db: AsyncSession, token: str) -> Optional[User]:
        """Valide un token JWT et retourne l'utilisateur"""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[AuthService.ALGORITHM])
            username = payload.get("sub")
            session_id = payload.get("session_id")

            if not username or not session_id:
                return None

            # Vérifier que la session est encore active
            result = await db.execute(
                select(UserSession).where(
                    and_(
                        UserSession.session_id == session_id,
                        UserSession.is_active == True,
                        UserSession.expires_at > datetime.utcnow()
                    )
                )
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            # Mettre à jour l'activité de la session
            session.last_activity = datetime.utcnow()
            await db.commit()

            # Récupérer l'utilisateur
            user = await AuthService.get_user_by_username(db, username)
            if user:
                await db.refresh(user, ["role"])

            return user

        except JWTError:
            return None

    @staticmethod
    async def logout(db: AsyncSession, token: str) -> bool:
        """Déconnecte un utilisateur (invalide la session)"""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[AuthService.ALGORITHM])
            session_id = payload.get("session_id")

            if session_id:
                result = await db.execute(
                    select(UserSession).where(UserSession.session_id == session_id)
                )
                session = result.scalar_one_or_none()

                if session:
                    session.is_active = False
                    await db.commit()
                    return True

        except JWTError:
            pass

        return False

    @staticmethod
    async def get_active_sessions(db: AsyncSession) -> list[Dict[str, Any]]:
        """Retourne la liste des sessions actives"""
        result = await db.execute(
            select(UserSession, User)
            .join(User)
            .where(
                and_(
                    UserSession.is_active == True,
                    UserSession.expires_at > datetime.utcnow()
                )
            )
            .order_by(UserSession.last_activity.desc())
        )

        sessions = []
        for session, user in result:
            sessions.append({
                "session_id": session.session_id[:8] + "...",
                "username": user.username,
                "display_name": user.display_name,
                "client_ip": session.client_ip,
                "client_hostname": session.client_hostname,
                "connected_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "expires_at": session.expires_at.isoformat()
            })

        return sessions

    @staticmethod
    async def force_disconnect_user(db: AsyncSession, username: str) -> int:
        """Force la déconnexion d'un utilisateur (invalide toutes ses sessions)"""
        user = await AuthService.get_user_by_username(db, username)
        if not user:
            return 0

        result = await db.execute(
            select(UserSession).where(
                and_(
                    UserSession.user_id == user.id,
                    UserSession.is_active == True
                )
            )
        )
        sessions = result.scalars().all()

        count = 0
        for session in sessions:
            session.is_active = False
            count += 1

        await db.commit()
        return count
