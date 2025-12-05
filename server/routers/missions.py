"""
Routes pour la gestion des missions
"""

import uuid
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from server.database import get_db
from server.models import Mission, User, ActivityLog
from server.routers.auth import get_current_user, require_permission

router = APIRouter(prefix="/missions", tags=["Missions"])


# ============== Schémas Pydantic ==============

class MissionBase(BaseModel):
    """Données de base d'une mission"""
    date_mission: date
    heure_debut: Optional[str] = None
    heure_fin: Optional[str] = None
    voyage_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    sst_id: Optional[int] = None
    type_mission: Optional[str] = None
    destination: Optional[str] = None
    depart: Optional[str] = None
    pays: Optional[str] = None
    nb_palettes: Optional[int] = 0
    poids_kg: Optional[float] = None
    tracteur: Optional[str] = None
    remorque: Optional[str] = None
    statut: str = "planifie"
    commentaire: Optional[str] = None
    cout_sst: Optional[float] = None
    revenu: Optional[float] = None


class MissionCreate(MissionBase):
    """Création d'une mission"""
    pass


class MissionUpdate(BaseModel):
    """Mise à jour d'une mission (tous les champs optionnels)"""
    date_mission: Optional[date] = None
    heure_debut: Optional[str] = None
    heure_fin: Optional[str] = None
    voyage_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    sst_id: Optional[int] = None
    type_mission: Optional[str] = None
    destination: Optional[str] = None
    depart: Optional[str] = None
    pays: Optional[str] = None
    nb_palettes: Optional[int] = None
    poids_kg: Optional[float] = None
    tracteur: Optional[str] = None
    remorque: Optional[str] = None
    statut: Optional[str] = None
    commentaire: Optional[str] = None
    cout_sst: Optional[float] = None
    revenu: Optional[float] = None


class MissionResponse(MissionBase):
    """Réponse avec les données complètes d'une mission"""
    id: int
    uuid: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== Endpoints ==============

@router.get("/", response_model=List[MissionResponse])
async def list_missions(
    date_debut: Optional[date] = Query(None, description="Date de début"),
    date_fin: Optional[date] = Query(None, description="Date de fin"),
    chauffeur_id: Optional[int] = Query(None, description="ID du chauffeur"),
    voyage_id: Optional[int] = Query(None, description="ID du voyage"),
    statut: Optional[str] = Query(None, description="Statut de la mission"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """
    Liste les missions avec filtres optionnels.

    Filtres disponibles:
    - date_debut / date_fin: Plage de dates
    - chauffeur_id: Missions d'un chauffeur spécifique
    - voyage_id: Missions d'un voyage spécifique
    - statut: Statut de la mission (planifie, en_cours, termine, annule)
    """
    query = select(Mission).order_by(Mission.date_mission.desc(), Mission.heure_debut)

    # Appliquer les filtres
    conditions = []

    if date_debut:
        conditions.append(Mission.date_mission >= date_debut)
    if date_fin:
        conditions.append(Mission.date_mission <= date_fin)
    if chauffeur_id:
        conditions.append(Mission.chauffeur_id == chauffeur_id)
    if voyage_id:
        conditions.append(Mission.voyage_id == voyage_id)
    if statut:
        conditions.append(Mission.statut == statut)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    missions = result.scalars().all()

    return missions


@router.get("/by-date/{mission_date}", response_model=List[MissionResponse])
async def get_missions_by_date(
    mission_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Récupère toutes les missions d'une date spécifique"""
    result = await db.execute(
        select(Mission)
        .where(Mission.date_mission == mission_date)
        .order_by(Mission.heure_debut)
    )
    return result.scalars().all()


@router.get("/{mission_id}", response_model=MissionResponse)
async def get_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Récupère une mission par son ID"""
    result = await db.execute(
        select(Mission).where(Mission.id == mission_id)
    )
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} non trouvée"
        )

    return mission


@router.get("/uuid/{mission_uuid}", response_model=MissionResponse)
async def get_mission_by_uuid(
    mission_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_planning"))
):
    """Récupère une mission par son UUID"""
    result = await db.execute(
        select(Mission).where(Mission.uuid == mission_uuid)
    )
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission UUID {mission_uuid} non trouvée"
        )

    return mission


@router.post("/", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
async def create_mission(
    mission_data: MissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_planning"))
):
    """Crée une nouvelle mission"""

    # Créer la mission
    mission = Mission(
        uuid=str(uuid.uuid4()),
        created_by=current_user.username,
        updated_by=current_user.username,
        **mission_data.model_dump()
    )

    db.add(mission)
    await db.commit()
    await db.refresh(mission)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="mission",
        entity_id=str(mission.id),
        after_state=mission_data.model_dump_json()
    )
    db.add(log_entry)
    await db.commit()

    return mission


@router.put("/{mission_id}", response_model=MissionResponse)
async def update_mission(
    mission_id: int,
    mission_data: MissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_planning"))
):
    """Met à jour une mission existante"""

    result = await db.execute(
        select(Mission).where(Mission.id == mission_id)
    )
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} non trouvée"
        )

    # Sauvegarder l'état avant modification
    before_state = {
        "date_mission": str(mission.date_mission),
        "heure_debut": mission.heure_debut,
        "destination": mission.destination,
        "statut": mission.statut,
        "chauffeur_id": mission.chauffeur_id
    }

    # Appliquer les modifications
    update_data = mission_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mission, field, value)

    mission.updated_by = current_user.username

    await db.commit()
    await db.refresh(mission)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="UPDATE",
        entity_type="mission",
        entity_id=str(mission.id),
        before_state=before_state,
        after_state=update_data
    )
    db.add(log_entry)
    await db.commit()

    return mission


@router.delete("/{mission_id}")
async def delete_mission(
    mission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_planning"))
):
    """Supprime une mission"""

    result = await db.execute(
        select(Mission).where(Mission.id == mission_id)
    )
    mission = result.scalar_one_or_none()

    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} non trouvée"
        )

    # Sauvegarder les infos pour le log
    mission_info = {
        "id": mission.id,
        "uuid": mission.uuid,
        "date_mission": str(mission.date_mission),
        "destination": mission.destination
    }

    await db.delete(mission)
    await db.commit()

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="DELETE",
        entity_type="mission",
        entity_id=str(mission_id),
        before_state=mission_info
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": f"Mission {mission_id} supprimée"}


@router.post("/bulk", response_model=List[MissionResponse])
async def create_missions_bulk(
    missions_data: List[MissionCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("edit_planning"))
):
    """Crée plusieurs missions en une seule requête"""

    created_missions = []

    for mission_data in missions_data:
        mission = Mission(
            uuid=str(uuid.uuid4()),
            created_by=current_user.username,
            updated_by=current_user.username,
            **mission_data.model_dump()
        )
        db.add(mission)
        created_missions.append(mission)

    await db.commit()

    # Rafraîchir toutes les missions
    for mission in created_missions:
        await db.refresh(mission)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="BULK_CREATE",
        entity_type="mission",
        details={"count": len(created_missions)}
    )
    db.add(log_entry)
    await db.commit()

    return created_missions
