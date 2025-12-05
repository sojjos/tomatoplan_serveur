"""
Service d'authentification sécurisé pour accès Internet
Inclut: mot de passe obligatoire, verrouillage de compte, validation
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from jose import jwt, JWTError
from passlib.context import CryptContext

from server.config import settings
from server.models.user import User, UserRole, UserSession


# Configuration du hachage de mot de passe (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service d'authentification et gestion des sessions"""

    ALGORITHM = "HS256"
    MAX_FAILED_ATTEMPTS = 5  # Tentatives avant verrouillage
    LOCKOUT_DURATION_MINUTES = 15  # Durée du verrouillage

    # ============== Gestion des mots de passe ==============

    @staticmethod
    def hash_password(password: str) -> str:
        """Hache un mot de passe avec bcrypt"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe contre son hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def generate_temp_password() -> str:
        """Génère un mot de passe temporaire sécurisé (12 caractères)"""
        return secrets.token_urlsafe(9)

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """
        Valide la force d'un mot de passe.
        Retourne (is_valid, message)
        """
        if len(password) < 8:
            return False, "Le mot de passe doit contenir au moins 8 caractères"
        if not any(c.isupper() for c in password):
            return False, "Le mot de passe doit contenir au moins une majuscule"
        if not any(c.islower() for c in password):
            return False, "Le mot de passe doit contenir au moins une minuscule"
        if not any(c.isdigit() for c in password):
            return False, "Le mot de passe doit contenir au moins un chiffre"
        return True, "OK"

    # ============== Normalisation ==============

    @staticmethod
    def normalize_username(username: str) -> str:
        """
        Normalise le nom d'utilisateur.
        Accepte: DOMAIN\\username, DOMAIN/username, username
        Retourne: USERNAME (majuscules, sans domaine)
        """
        username = username.strip()
        if "\\" in username:
            username = username.split("\\")[-1]
        elif "/" in username:
            username = username.split("/")[-1]
        return username.upper()

    # ============== Gestion des utilisateurs ==============

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Récupère un utilisateur par son nom"""
        normalized = AuthService.normalize_username(username)
        result = await db.execute(
            select(User).where(User.username == normalized)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(
        db: AsyncSession,
        username: str,
        password: Optional[str] = None,
        role_name: str = "viewer",
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        is_system_admin: bool = False
    ) -> tuple[User, Optional[str]]:
        """
        Crée un nouvel utilisateur avec mot de passe.
        Retourne (user, temp_password) - temp_password si aucun password fourni
        """
        normalized = AuthService.normalize_username(username)

        # Générer un mot de passe temporaire si non fourni
        temp_password = None
        if password:
            password_hash = AuthService.hash_password(password)
            must_change = False
        else:
            temp_password = AuthService.generate_temp_password()
            password_hash = AuthService.hash_password(temp_password)
            must_change = True

        # Récupérer le rôle
        role_result = await db.execute(
            select(UserRole).where(UserRole.name == role_name)
        )
        role = role_result.scalar_one_or_none()

        user = User(
            username=normalized,
            display_name=display_name or normalized,
            email=email,
            password_hash=password_hash,
            must_change_password=must_change,
            role=role,
            is_active=True,
            is_system_admin=is_system_admin
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return user, temp_password

    # ============== Verrouillage de compte ==============

    @staticmethod
    async def check_account_locked(db: AsyncSession, user: User) -> tuple[bool, str]:
        """
        Vérifie si le compte est verrouillé.
        Retourne (is_locked, message)
        """
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            return True, f"Compte verrouillé. Réessayez dans {remaining + 1} minutes."

        # Réinitialiser si le verrouillage est expiré
        if user.locked_until and user.locked_until <= datetime.utcnow():
            user.locked_until = None
            user.failed_login_attempts = 0
            await db.commit()

        return False, ""

    @staticmethod
    async def record_failed_login(db: AsyncSession, user: User):
        """Enregistre une tentative de connexion échouée"""
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= AuthService.MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(
                minutes=AuthService.LOCKOUT_DURATION_MINUTES
            )

        await db.commit()

    @staticmethod
    async def reset_failed_attempts(db: AsyncSession, user: User):
        """Réinitialise le compteur de tentatives échouées"""
        if user.failed_login_attempts > 0:
            user.failed_login_attempts = 0
            user.locked_until = None
            await db.commit()

    # ============== Authentification ==============

    @staticmethod
    async def authenticate(
        db: AsyncSession,
        username: str,
        password: str,
        client_ip: Optional[str] = None,
        client_hostname: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authentifie un utilisateur avec username + mot de passe.
        Retourne les infos de session ou lève une exception.
        """
        user = await AuthService.get_user_by_username(db, username)

        if not user:
            raise ValueError("Identifiants invalides")

        if not user.is_active:
            raise ValueError("Compte désactivé. Contactez l'administrateur.")

        # Vérifier le verrouillage
        is_locked, lock_message = await AuthService.check_account_locked(db, user)
        if is_locked:
            raise ValueError(lock_message)

        # Vérifier le mot de passe
        if not user.password_hash:
            raise ValueError("Compte non configuré. Contactez l'administrateur.")

        if not AuthService.verify_password(password, user.password_hash):
            await AuthService.record_failed_login(db, user)
            remaining = AuthService.MAX_FAILED_ATTEMPTS - user.failed_login_attempts
            if remaining > 0:
                raise ValueError(f"Mot de passe incorrect. {remaining} tentative(s) restante(s).")
            else:
                raise ValueError(f"Compte verrouillé pour {AuthService.LOCKOUT_DURATION_MINUTES} minutes.")

        # Connexion réussie - réinitialiser les tentatives
        await AuthService.reset_failed_attempts(db, user)

        # Créer la session
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

        # Charger le rôle
        await db.refresh(user, ["role"])

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expires_at.isoformat(),
            "must_change_password": user.must_change_password,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.name if user.role else "viewer",
                "is_system_admin": user.is_system_admin,
                "permissions": AuthService.get_user_permissions(user)
            }
        }

    # ============== Gestion des mots de passe ==============

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        current_password: str,
        new_password: str
    ) -> bool:
        """Change le mot de passe d'un utilisateur"""
        # Vérifier l'ancien mot de passe
        if not AuthService.verify_password(current_password, user.password_hash):
            raise ValueError("Mot de passe actuel incorrect")

        # Valider le nouveau mot de passe
        is_valid, message = AuthService.validate_password_strength(new_password)
        if not is_valid:
            raise ValueError(message)

        # Ne pas réutiliser l'ancien mot de passe
        if AuthService.verify_password(new_password, user.password_hash):
            raise ValueError("Le nouveau mot de passe doit être différent de l'ancien")

        # Mettre à jour
        user.password_hash = AuthService.hash_password(new_password)
        user.must_change_password = False
        await db.commit()

        return True

    @staticmethod
    async def admin_reset_password(db: AsyncSession, user: User) -> str:
        """
        Réinitialise le mot de passe d'un utilisateur (admin).
        Retourne le nouveau mot de passe temporaire.
        """
        temp_password = AuthService.generate_temp_password()
        user.password_hash = AuthService.hash_password(temp_password)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()

        return temp_password

    # ============== Permissions ==============

    @staticmethod
    def get_user_permissions(user: User) -> Dict[str, bool]:
        """Retourne les permissions de l'utilisateur"""
        if user.is_system_admin:
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
            return {"view_planning": True}

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

    # ============== Validation de token ==============

    @staticmethod
    async def validate_token(db: AsyncSession, token: str) -> Optional[User]:
        """Valide un token JWT et retourne l'utilisateur"""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[AuthService.ALGORITHM])
            username = payload.get("sub")
            session_id = payload.get("session_id")

            if not username or not session_id:
                return None

            # Vérifier la session
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

            # Mettre à jour l'activité
            session.last_activity = datetime.utcnow()
            await db.commit()

            user = await AuthService.get_user_by_username(db, username)
            if user:
                await db.refresh(user, ["role"])

            return user

        except JWTError:
            return None

    # ============== Sessions ==============

    @staticmethod
    async def logout(db: AsyncSession, token: str) -> bool:
        """Déconnecte un utilisateur"""
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
        """Force la déconnexion d'un utilisateur"""
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
