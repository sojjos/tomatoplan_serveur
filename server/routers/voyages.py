"""
Routes pour la gestion des voyages
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from server.database import get_db
from server.models import Voyage, User, ActivityLog
from server.routers.auth import get_current_user, require_permission

router = APIRouter(prefix="/voyages", tags=["Voyages"])


# ============== Schémas Pydantic ==============

class VoyageBase(BaseModel):
    """Données de base d'un voyage"""
    code: str
    nom: str
    description: Optional[str] = None
    depart: Optional[str] = None
    destination: Optional[str] = None
    pays_destination: Optional[str] = None
    heure_depart_defaut: Optional[str] = None
    heure_arrivee_defaut: Optional[str] = None
    jours_operation: Optional[List[str]] = None
    nb_palettes_moyen: Optional[int] = None
    is_active: bool = True
    couleur: Optional[str] = None


class VoyageCreate(VoyageBase):
    """Création d'un voyage"""
    pass


class VoyageUpdate(BaseModel):
    """Mise à jour d'un voyage"""
    code: Optional[str] = None
    nom: Optional[str] = None
    description: Optional[str] = None
    depart: Optional[str] = None
    destination: Optional[str] = None
    pays_destination: Optional[str] = None
    heure_depart_defaut: Optional[str] = None
    heure_arrivee_defaut: Optional[str] = None
    jours_operation: Optional[List[str]] = None
    nb_palettes_moyen: Optional[int] = None
    is_active: Optional[bool] = None
    couleur: Optional[str] = None


class VoyageResponse(VoyageBase):
    """Réponse avec les données complètes d'un voyage"""
    id: int
    uuid: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== Endpoints ==============

@router.get("/", response_model=List[VoyageResponse])
async def list_voyages(
    active_only: bool = Query(True, description="Afficher uniquement les voyages actifs"),
    pays: Optional[str] = Query(None, description="Filtrer par pays de destination"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Liste tous les voyages"""
    query = select(Voyage).order_by(Voyage.code)

    if active_only:
        query = query.where(Voyage.is_active == True)

    if pays:
        query = query.where(Voyage.pays_destination == pays)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{voyage_id}", response_model=VoyageResponse)
async def get_voyage(
    voyage_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Récupère un voyage par son ID"""
    result = await db.execute(
        select(Voyage).where(Voyage.id == voyage_id)
    )
    voyage = result.scalar_one_or_none()

    if not voyage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voyage {voyage_id} non trouvé"
        )

    return voyage


@router.get("/code/{code}", response_model=VoyageResponse)
async def get_voyage_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Récupère un voyage par son code"""
    result = await db.execute(
        select(Voyage).where(Voyage.code == code.upper())
    )
    voyage = result.scalar_one_or_none()

    if not voyage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voyage avec code '{code}' non trouvé"
        )

    return voyage


@router.post("/", response_model=VoyageResponse, status_code=status.HTTP_201_CREATED)
async def create_voyage(
    voyage_data: VoyageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_voyages"))
):
    """Crée un nouveau voyage"""

    # Vérifier que le code n'existe pas déjà
    existing = await db.execute(
        select(Voyage).where(Voyage.code == voyage_data.code.upper())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Un voyage avec le code '{voyage_data.code}' existe déjà"
        )

    voyage = Voyage(
        uuid=str(uuid.uuid4()),
        created_by=current_user.username,
        updated_by=current_user.username,
        **voyage_data.model_dump()
    )
    voyage.code = voyage.code.upper()

    db.add(voyage)
    await db.commit()
    await db.refresh(voyage)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="voyage",
        entity_id=str(voyage.id)
    )
    db.add(log_entry)
    await db.commit()

    return voyage


@router.put("/{voyage_id}", response_model=VoyageResponse)
async def update_voyage(
    voyage_id: int,
    voyage_data: VoyageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_voyages"))
):
    """Met à jour un voyage existant"""

    result = await db.execute(
        select(Voyage).where(Voyage.id == voyage_id)
    )
    voyage = result.scalar_one_or_none()

    if not voyage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voyage {voyage_id} non trouvé"
        )

    # Appliquer les modifications
    update_data = voyage_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "code" and value:
            value = value.upper()
        setattr(voyage, field, value)

    voyage.updated_by = current_user.username

    await db.commit()
    await db.refresh(voyage)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="UPDATE",
        entity_type="voyage",
        entity_id=str(voyage.id)
    )
    db.add(log_entry)
    await db.commit()

    return voyage


@router.delete("/{voyage_id}")
async def delete_voyage(
    voyage_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_voyages"))
):
    """Supprime un voyage (ou le désactive)"""

    result = await db.execute(
        select(Voyage).where(Voyage.id == voyage_id)
    )
    voyage = result.scalar_one_or_none()

    if not voyage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voyage {voyage_id} non trouvé"
        )

    # Désactiver plutôt que supprimer pour garder l'historique
    voyage.is_active = False
    voyage.updated_by = current_user.username

    await db.commit()

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="DEACTIVATE",
        entity_type="voyage",
        entity_id=str(voyage_id)
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": f"Voyage {voyage_id} désactivé"}
