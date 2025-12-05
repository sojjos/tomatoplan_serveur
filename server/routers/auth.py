"""
Routes d'authentification
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.services.auth_service import AuthService
from server.models import User, ActivityLog

router = APIRouter(prefix="/auth", tags=["Authentification"])


class LoginRequest(BaseModel):
    """Requête de connexion"""
    username: str  # Identifiant Windows (DOMAIN\username ou username)
    hostname: Optional[str] = None  # Nom de la machine cliente


class LoginResponse(BaseModel):
    """Réponse de connexion"""
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: dict


class CurrentUser(BaseModel):
    """Informations de l'utilisateur courant"""
    id: int
    username: str
    display_name: Optional[str]
    role: str
    is_system_admin: bool
    permissions: dict


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


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authentification par identifiant Windows.

    Le client envoie son identifiant Windows (récupéré via %USERNAME% ou getpass).
    Le serveur vérifie si l'utilisateur est autorisé et retourne un token JWT.
    """
    client_ip = request.client.host if request.client else None

    result = await AuthService.authenticate_windows_user(
        db=db,
        username=login_data.username,
        client_ip=client_ip,
        client_hostname=login_data.hostname,
        user_agent=request.headers.get("User-Agent")
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non autorisé ou compte désactivé"
        )

    # Logger la connexion
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
        # Logger la déconnexion
        log_entry = ActivityLog(
            username=current_user.username,
            action_type="LOGOUT"
        )
        db.add(log_entry)
        await db.commit()

    return {"success": success, "message": "Déconnecté" if success else "Erreur lors de la déconnexion"}


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


@router.post("/refresh")
async def refresh_token(
    request: Request,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rafraîchit le token (prolonge la session).
    Retourne un nouveau token avec une nouvelle date d'expiration.
    """
    # D'abord déconnecter la session actuelle
    token = authorization.replace("Bearer ", "")
    await AuthService.logout(db, token)

    # Puis créer une nouvelle session
    client_ip = request.client.host if request.client else None

    result = await AuthService.authenticate_windows_user(
        db=db,
        username=current_user.username,
        client_ip=client_ip,
        user_agent=request.headers.get("User-Agent")
    )

    return result
