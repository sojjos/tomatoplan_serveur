"""
Routes pour la gestion financiere (revenus palettes)
"""

from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from server.database import get_db
from server.models import RevenuPalette, Mission, User, ActivityLog
from server.routers.auth import get_current_user, require_permission

router = APIRouter(prefix="/finance", tags=["Finance"])


# ============== Schemas Pydantic ==============

class RevenuPaletteBase(BaseModel):
    """Donnees de base d'un revenu palette"""
    destination: str
    pays: Optional[str] = None
    revenu_par_palette: float
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None


class RevenuPaletteCreate(RevenuPaletteBase):
    """Creation d'un revenu palette"""
    pass


class RevenuPaletteUpdate(BaseModel):
    """Mise a jour d'un revenu palette"""
    destination: Optional[str] = None
    pays: Optional[str] = None
    revenu_par_palette: Optional[float] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None


class RevenuPaletteResponse(RevenuPaletteBase):
    """Reponse revenu palette"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FinanceStats(BaseModel):
    """Statistiques financieres"""
    total_missions: int
    total_palettes: int
    total_revenus: float
    total_couts_sst: float
    marge_brute: float
    missions_par_pays: dict


# ============== Endpoints Revenus Palettes ==============

@router.get("/revenus", response_model=List[RevenuPaletteResponse])
async def list_revenus_palettes(
    pays: Optional[str] = None,
    destination: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Liste tous les revenus par palette"""

    query = select(RevenuPalette).order_by(RevenuPalette.destination)

    if pays:
        query = query.where(RevenuPalette.pays == pays)

    if destination:
        query = query.where(RevenuPalette.destination.ilike(f"%{destination}%"))

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/revenus/{revenu_id}", response_model=RevenuPaletteResponse)
async def get_revenu_palette(
    revenu_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere un revenu palette par ID"""

    result = await db.execute(
        select(RevenuPalette).where(RevenuPalette.id == revenu_id)
    )
    revenu = result.scalar_one_or_none()

    if not revenu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revenu palette {revenu_id} non trouve"
        )

    return revenu


@router.get("/revenus/destination/{destination}", response_model=RevenuPaletteResponse)
async def get_revenu_by_destination(
    destination: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere le revenu palette pour une destination"""

    result = await db.execute(
        select(RevenuPalette)
        .where(RevenuPalette.destination.ilike(destination))
        .order_by(RevenuPalette.date_debut.desc())
    )
    revenu = result.scalars().first()

    if not revenu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revenu pour destination '{destination}' non trouve"
        )

    return revenu


@router.post("/revenus", response_model=RevenuPaletteResponse, status_code=status.HTTP_201_CREATED)
async def create_revenu_palette(
    revenu_data: RevenuPaletteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Cree un nouveau revenu palette"""

    revenu = RevenuPalette(**revenu_data.model_dump())

    db.add(revenu)
    await db.commit()
    await db.refresh(revenu)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="revenu_palette",
        entity_id=str(revenu.id)
    )
    db.add(log_entry)
    await db.commit()

    return revenu


@router.put("/revenus/{revenu_id}", response_model=RevenuPaletteResponse)
async def update_revenu_palette(
    revenu_id: int,
    revenu_data: RevenuPaletteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Met a jour un revenu palette"""

    result = await db.execute(
        select(RevenuPalette).where(RevenuPalette.id == revenu_id)
    )
    revenu = result.scalar_one_or_none()

    if not revenu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revenu palette {revenu_id} non trouve"
        )

    # Appliquer les modifications
    update_data = revenu_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(revenu, field, value)

    await db.commit()
    await db.refresh(revenu)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="UPDATE",
        entity_type="revenu_palette",
        entity_id=str(revenu.id)
    )
    db.add(log_entry)
    await db.commit()

    return revenu


@router.delete("/revenus/{revenu_id}")
async def delete_revenu_palette(
    revenu_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Supprime un revenu palette"""

    result = await db.execute(
        select(RevenuPalette).where(RevenuPalette.id == revenu_id)
    )
    revenu = result.scalar_one_or_none()

    if not revenu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revenu palette {revenu_id} non trouve"
        )

    await db.delete(revenu)
    await db.commit()

    return {"success": True, "message": f"Revenu palette {revenu_id} supprime"}


# ============== Statistiques financieres ==============

@router.get("/stats")
async def get_finance_stats(
    date_debut: date = Query(..., description="Date de debut"),
    date_fin: date = Query(..., description="Date de fin"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """
    Calcule les statistiques financieres pour une periode.

    Retourne:
    - Total des missions
    - Total des palettes
    - Revenus estimes
    - Couts SST
    - Marge brute
    - Repartition par pays
    """

    # Recuperer les missions de la periode
    missions_result = await db.execute(
        select(Mission).where(
            and_(
                Mission.date_mission >= date_debut,
                Mission.date_mission <= date_fin
            )
        )
    )
    missions = missions_result.scalars().all()

    total_missions = len(missions)
    total_palettes = sum(m.nb_palettes or 0 for m in missions)
    total_revenus = sum(m.revenu or 0 for m in missions)
    total_couts_sst = sum(m.cout_sst or 0 for m in missions)
    marge_brute = total_revenus - total_couts_sst

    # Repartition par pays
    missions_par_pays = {}
    for m in missions:
        pays = m.pays or "Non defini"
        if pays not in missions_par_pays:
            missions_par_pays[pays] = {
                "count": 0,
                "palettes": 0,
                "revenus": 0,
                "couts_sst": 0
            }
        missions_par_pays[pays]["count"] += 1
        missions_par_pays[pays]["palettes"] += m.nb_palettes or 0
        missions_par_pays[pays]["revenus"] += m.revenu or 0
        missions_par_pays[pays]["couts_sst"] += m.cout_sst or 0

    return {
        "periode": {
            "debut": str(date_debut),
            "fin": str(date_fin)
        },
        "total_missions": total_missions,
        "total_palettes": total_palettes,
        "total_revenus": round(total_revenus, 2),
        "total_couts_sst": round(total_couts_sst, 2),
        "marge_brute": round(marge_brute, 2),
        "missions_par_pays": missions_par_pays
    }


@router.get("/stats/mensuel")
async def get_monthly_stats(
    annee: int = Query(..., description="Annee"),
    mois: int = Query(..., description="Mois (1-12)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Statistiques financieres mensuelles"""

    from calendar import monthrange

    # Premier et dernier jour du mois
    premier_jour = date(annee, mois, 1)
    dernier_jour = date(annee, mois, monthrange(annee, mois)[1])

    # Recuperer les missions du mois
    missions_result = await db.execute(
        select(Mission).where(
            and_(
                Mission.date_mission >= premier_jour,
                Mission.date_mission <= dernier_jour
            )
        )
    )
    missions = missions_result.scalars().all()

    # Stats par jour
    stats_par_jour = {}
    for m in missions:
        jour = str(m.date_mission)
        if jour not in stats_par_jour:
            stats_par_jour[jour] = {
                "missions": 0,
                "palettes": 0,
                "revenus": 0,
                "couts_sst": 0
            }
        stats_par_jour[jour]["missions"] += 1
        stats_par_jour[jour]["palettes"] += m.nb_palettes or 0
        stats_par_jour[jour]["revenus"] += m.revenu or 0
        stats_par_jour[jour]["couts_sst"] += m.cout_sst or 0

    total_palettes = sum(m.nb_palettes or 0 for m in missions)
    total_revenus = sum(m.revenu or 0 for m in missions)
    total_couts = sum(m.cout_sst or 0 for m in missions)

    return {
        "annee": annee,
        "mois": mois,
        "total_missions": len(missions),
        "total_palettes": total_palettes,
        "total_revenus": round(total_revenus, 2),
        "total_couts_sst": round(total_couts, 2),
        "marge_brute": round(total_revenus - total_couts, 2),
        "stats_par_jour": stats_par_jour
    }


@router.get("/stats/annuel")
async def get_yearly_stats(
    annee: int = Query(..., description="Annee"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Statistiques financieres annuelles"""

    # Recuperer les missions de l'annee
    missions_result = await db.execute(
        select(Mission).where(
            and_(
                Mission.date_mission >= date(annee, 1, 1),
                Mission.date_mission <= date(annee, 12, 31)
            )
        )
    )
    missions = missions_result.scalars().all()

    # Stats par mois
    stats_par_mois = {m: {"missions": 0, "palettes": 0, "revenus": 0, "couts_sst": 0} for m in range(1, 13)}

    for m in missions:
        mois = m.date_mission.month
        stats_par_mois[mois]["missions"] += 1
        stats_par_mois[mois]["palettes"] += m.nb_palettes or 0
        stats_par_mois[mois]["revenus"] += m.revenu or 0
        stats_par_mois[mois]["couts_sst"] += m.cout_sst or 0

    total_palettes = sum(m.nb_palettes or 0 for m in missions)
    total_revenus = sum(m.revenu or 0 for m in missions)
    total_couts = sum(m.cout_sst or 0 for m in missions)

    return {
        "annee": annee,
        "total_missions": len(missions),
        "total_palettes": total_palettes,
        "total_revenus": round(total_revenus, 2),
        "total_couts_sst": round(total_couts, 2),
        "marge_brute": round(total_revenus - total_couts, 2),
        "stats_par_mois": stats_par_mois
    }
