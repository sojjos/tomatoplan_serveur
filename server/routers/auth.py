"""
Routes d'authentification sécurisée (avec mot de passe)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.services.auth_service import AuthService
from server.models import User, ActivityLog

router = APIRouter(prefix="/auth", tags=["Authentification"])


# ============== Schémas ==============

class LoginRequest(BaseModel):
    """Requête de connexion avec mot de passe"""
    username: str  # Identifiant (DOMAIN\username ou username)
    password: str  # Mot de passe
    hostname: Optional[str] = None  # Nom de la machine cliente


class LoginResponse(BaseModel):
    """Réponse de connexion"""
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    must_change_password: bool = False
    user: dict


class ChangePasswordRequest(BaseModel):
    """Requête de changement de mot de passe"""
    current_password: str
    new_password: str


class CurrentUser(BaseModel):
    """Informations de l'utilisateur courant"""
    id: int
    username: str
    display_name: Optional[str]
    role: str
    is_system_admin: bool
    permissions: dict


# ============== Dépendances ==============

async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dépendance pour récupérer l'utilisateur courant depuis le token.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification manquant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Format de token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "")
    user = await AuthService.validate_token(db, token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur désactivé"
        )

    return user


def require_permission(permission: str):
    """Décorateur pour vérifier une permission spécifique"""
    async def check_permission(current_user: User = Depends(get_current_user)):
        permissions = AuthService.get_user_permissions(current_user)
        if not permissions.get(permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' requise"
            )
        return current_user
    return check_permission


# ============== Endpoints ==============

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authentification avec identifiant et mot de passe.

    - **username**: Identifiant utilisateur (ex: JEAN.DUPONT)
    - **password**: Mot de passe
    - **hostname**: (optionnel) Nom de la machine cliente

    Retourne un token JWT valide 8 heures.

    Sécurité:
    - Verrouillage après 5 tentatives échouées (15 min)
    - Mot de passe hashé avec bcrypt
    """
    client_ip = request.client.host if request.client else None

    try:
        result = await AuthService.authenticate(
            db=db,
            username=login_data.username,
            password=login_data.password,
            client_ip=client_ip,
            client_hostname=login_data.hostname,
            user_agent=request.headers.get("User-Agent")
        )
    except ValueError as e:
        # Logger la tentative échouée
        log_entry = ActivityLog(
            username=AuthService.normalize_username(login_data.username),
            action_type="LOGIN_FAILED",
            details={"reason": str(e), "client_ip": client_ip},
            client_ip=client_ip
        )
        db.add(log_entry)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

    # Logger la connexion réussie
    log_entry = ActivityLog(
        username=result["user"]["username"],
        action_type="LOGIN",
        details={"client_ip": client_ip, "hostname": login_data.hostname},
        client_ip=client_ip
    )
    db.add(log_entry)
    await db.commit()

    return result


@router.post("/logout")
async def logout(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Déconnexion - invalide le token courant"""

    token = authorization.replace("Bearer ", "")
    success = await AuthService.logout(db, token)

    if success:
        log_entry = ActivityLog(
            username=current_user.username,
            action_type="LOGOUT"
        )
        db.add(log_entry)
        await db.commit()

    return {"success": success, "message": "Déconnecté" if success else "Erreur"}


@router.get("/me", response_model=CurrentUser)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    """Retourne les informations de l'utilisateur courant"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role.name if current_user.role else "viewer",
        "is_system_admin": current_user.is_system_admin,
        "permissions": AuthService.get_user_permissions(current_user)
    }


@router.post("/change-password")
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Change le mot de passe de l'utilisateur courant.

    Le nouveau mot de passe doit contenir:
    - Au moins 8 caractères
    - Au moins une majuscule
    - Au moins une minuscule
    - Au moins un chiffre
    """
    try:
        await AuthService.change_password(
            db=db,
            user=current_user,
            current_password=password_data.current_password,
            new_password=password_data.new_password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Logger le changement
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="PASSWORD_CHANGED",
        client_ip=request.client.host if request.client else None
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": "Mot de passe modifié avec succès"}


@router.post("/refresh")
async def refresh_token(
    request: Request,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rafraîchit le token sans redemander le mot de passe.
    Prolonge la session de 8 heures supplémentaires.
    """
    import secrets
    from datetime import datetime, timedelta
    from jose import jwt
    from server.config import settings
    from server.models import UserSession

    # Invalider l'ancienne session
    old_token = authorization.replace("Bearer ", "")
    await AuthService.logout(db, old_token)

    # Créer une nouvelle session
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

    session = UserSession(
        session_id=session_id,
        user_id=current_user.id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        expires_at=expires_at
    )
    db.add(session)
    await db.commit()

    # Générer le nouveau token
    token_data = {
        "sub": current_user.username,
        "session_id": session_id,
        "exp": expires_at
    }
    token = jwt.encode(token_data, settings.secret_key, algorithm="HS256")

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat()
    }
