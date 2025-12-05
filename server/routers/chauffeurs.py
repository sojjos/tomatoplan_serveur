"""
Routes pour la gestion des chauffeurs
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from server.database import get_db
from server.models import Chauffeur, ChauffeurDispo, User, ActivityLog
from server.routers.auth import get_current_user, require_permission
from server.services.websocket_manager import notify_change

router = APIRouter(prefix="/chauffeurs", tags=["Chauffeurs"])


# ============== Schémas Pydantic ==============

class ChauffeurBase(BaseModel):
    """Données de base d'un chauffeur"""
    code: str
    nom: str
    prenom: str
    telephone: Optional[str] = None
    email: Optional[str] = None
    type_contrat: Optional[str] = None
    date_embauche: Optional[date] = None
    permis: Optional[str] = None
    adr: bool = False
    fimo: bool = True
    tracteur_attire: Optional[str] = None
    is_active: bool = True
    commentaire: Optional[str] = None


class ChauffeurCreate(ChauffeurBase):
    """Création d'un chauffeur"""
    pass


class ChauffeurUpdate(BaseModel):
    """Mise à jour d'un chauffeur"""
    code: Optional[str] = None
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    type_contrat: Optional[str] = None
    date_embauche: Optional[date] = None
    permis: Optional[str] = None
    adr: Optional[bool] = None
    fimo: Optional[bool] = None
    tracteur_attire: Optional[str] = None
    is_active: Optional[bool] = None
    commentaire: Optional[str] = None


class ChauffeurResponse(ChauffeurBase):
    """Réponse avec les données complètes d'un chauffeur"""
    id: int
    uuid: str
    nom_complet: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DispoBase(BaseModel):
    """Données de disponibilité"""
    date_debut: date
    date_fin: date
    type_absence: str
    motif: Optional[str] = None


class DispoCreate(DispoBase):
    """Création d'une indisponibilité"""
    chauffeur_id: int


class DispoResponse(DispoBase):
    """Réponse disponibilité"""
    id: int
    chauffeur_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============== Endpoints Chauffeurs ==============

@router.get("/", response_model=List[ChauffeurResponse])
async def list_chauffeurs(
    active_only: bool = Query(True, description="Afficher uniquement les chauffeurs actifs"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_drivers"))
):
    """Liste tous les chauffeurs"""
    query = select(Chauffeur).order_by(Chauffeur.nom, Chauffeur.prenom)

    if active_only:
        query = query.where(Chauffeur.is_active == True)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{chauffeur_id}", response_model=ChauffeurResponse)
async def get_chauffeur(
    chauffeur_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_drivers"))
):
    """Récupère un chauffeur par son ID"""
    result = await db.execute(
        select(Chauffeur).where(Chauffeur.id == chauffeur_id)
    )
    chauffeur = result.scalar_one_or_none()

    if not chauffeur:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chauffeur {chauffeur_id} non trouvé"
        )

    return chauffeur


@router.get("/code/{code}", response_model=ChauffeurResponse)
async def get_chauffeur_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_drivers"))
):
    """Récupère un chauffeur par son code"""
    result = await db.execute(
        select(Chauffeur).where(Chauffeur.code == code.upper())
    )
    chauffeur = result.scalar_one_or_none()

    if not chauffeur:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chauffeur avec code '{code}' non trouvé"
        )

    return chauffeur


@router.post("/", response_model=ChauffeurResponse, status_code=status.HTTP_201_CREATED)
async def create_chauffeur(
    chauffeur_data: ChauffeurCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_drivers"))
):
    """Crée un nouveau chauffeur"""

    # Vérifier que le code n'existe pas déjà
    existing = await db.execute(
        select(Chauffeur).where(Chauffeur.code == chauffeur_data.code.upper())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Un chauffeur avec le code '{chauffeur_data.code}' existe déjà"
        )

    chauffeur = Chauffeur(
        uuid=str(uuid.uuid4()),
        created_by=current_user.username,
        updated_by=current_user.username,
        **chauffeur_data.model_dump()
    )
    chauffeur.code = chauffeur.code.upper()

    db.add(chauffeur)
    await db.commit()
    await db.refresh(chauffeur)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="chauffeur",
        entity_id=str(chauffeur.id)
    )
    db.add(log_entry)
    await db.commit()

    # Notifier tous les clients
    await notify_change("chauffeurs", "created", chauffeur.id, changed_by=current_user.username)

    return chauffeur


@router.put("/{chauffeur_id}", response_model=ChauffeurResponse)
async def update_chauffeur(
    chauffeur_id: int,
    chauffeur_data: ChauffeurUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_drivers"))
):
    """Met à jour un chauffeur existant"""

    result = await db.execute(
        select(Chauffeur).where(Chauffeur.id == chauffeur_id)
    )
    chauffeur = result.scalar_one_or_none()

    if not chauffeur:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chauffeur {chauffeur_id} non trouvé"
        )

    # Appliquer les modifications
    update_data = chauffeur_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "code" and value:
            value = value.upper()
        setattr(chauffeur, field, value)

    chauffeur.updated_by = current_user.username

    await db.commit()
    await db.refresh(chauffeur)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="UPDATE",
        entity_type="chauffeur",
        entity_id=str(chauffeur.id)
    )
    db.add(log_entry)
    await db.commit()

    # Notifier tous les clients
    await notify_change("chauffeurs", "updated", chauffeur.id, changed_by=current_user.username)

    return chauffeur


@router.delete("/{chauffeur_id}")
async def delete_chauffeur(
    chauffeur_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_drivers"))
):
    """Désactive un chauffeur"""

    result = await db.execute(
        select(Chauffeur).where(Chauffeur.id == chauffeur_id)
    )
    chauffeur = result.scalar_one_or_none()

    if not chauffeur:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chauffeur {chauffeur_id} non trouvé"
        )

    chauffeur.is_active = False
    chauffeur.updated_by = current_user.username

    await db.commit()

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="DEACTIVATE",
        entity_type="chauffeur",
        entity_id=str(chauffeur_id)
    )
    db.add(log_entry)
    await db.commit()

    # Notifier tous les clients
    await notify_change("chauffeurs", "deleted", chauffeur_id, changed_by=current_user.username)

    return {"success": True, "message": f"Chauffeur {chauffeur_id} désactivé"}


# ============== Endpoints Disponibilités ==============

@router.get("/{chauffeur_id}/disponibilites", response_model=List[DispoResponse])
async def get_chauffeur_disponibilites(
    chauffeur_id: int,
    date_debut: Optional[date] = Query(None),
    date_fin: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_drivers"))
):
    """Récupère les indisponibilités d'un chauffeur"""

    query = select(ChauffeurDispo).where(ChauffeurDispo.chauffeur_id == chauffeur_id)

    if date_debut:
        query = query.where(ChauffeurDispo.date_fin >= date_debut)
    if date_fin:
        query = query.where(ChauffeurDispo.date_debut <= date_fin)

    query = query.order_by(ChauffeurDispo.date_debut)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/disponibilites", response_model=DispoResponse, status_code=status.HTTP_201_CREATED)
async def create_disponibilite(
    dispo_data: DispoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_driver_planning"))
):
    """Crée une nouvelle indisponibilité pour un chauffeur"""

    # Vérifier que le chauffeur existe
    chauffeur_result = await db.execute(
        select(Chauffeur).where(Chauffeur.id == dispo_data.chauffeur_id)
    )
    if not chauffeur_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chauffeur {dispo_data.chauffeur_id} non trouvé"
        )

    dispo = ChauffeurDispo(
        created_by=current_user.username,
        **dispo_data.model_dump()
    )

    db.add(dispo)
    await db.commit()
    await db.refresh(dispo)

    # Notifier tous les clients
    await notify_change("disponibilites", "created", dispo.id, changed_by=current_user.username)

    return dispo


@router.delete("/disponibilites/{dispo_id}")
async def delete_disponibilite(
    dispo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_driver_planning"))
):
    """Supprime une indisponibilité"""

    result = await db.execute(
        select(ChauffeurDispo).where(ChauffeurDispo.id == dispo_id)
    )
    dispo = result.scalar_one_or_none()

    if not dispo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Indisponibilité {dispo_id} non trouvée"
        )

    await db.delete(dispo)
    await db.commit()

    # Notifier tous les clients
    await notify_change("disponibilites", "deleted", dispo_id, changed_by=current_user.username)

    return {"success": True, "message": f"Indisponibilité {dispo_id} supprimée"}


@router.get("/disponibles/{check_date}")
async def get_chauffeurs_disponibles(
    check_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_drivers"))
):
    """
    Retourne la liste des chauffeurs disponibles pour une date donnée.
    Exclut les chauffeurs ayant une indisponibilité couvrant cette date.
    """

    # Récupérer tous les chauffeurs actifs
    all_chauffeurs = await db.execute(
        select(Chauffeur).where(Chauffeur.is_active == True)
    )
    chauffeurs = all_chauffeurs.scalars().all()

    # Récupérer les indisponibilités pour cette date
    indispo = await db.execute(
        select(ChauffeurDispo.chauffeur_id).where(
            and_(
                ChauffeurDispo.date_debut <= check_date,
                ChauffeurDispo.date_fin >= check_date
            )
        )
    )
    indispo_ids = set(row[0] for row in indispo)

    disponibles = [c for c in chauffeurs if c.id not in indispo_ids]
    indisponibles = [c for c in chauffeurs if c.id in indispo_ids]

    return {
        "date": str(check_date),
        "disponibles": [
            {"id": c.id, "code": c.code, "nom_complet": c.nom_complet}
            for c in disponibles
        ],
        "indisponibles": [
            {"id": c.id, "code": c.code, "nom_complet": c.nom_complet}
            for c in indisponibles
        ]
    }
