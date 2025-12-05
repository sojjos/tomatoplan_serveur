"""
Routes pour la gestion des sous-traitants (SST)
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from server.database import get_db
from server.models import SST, TarifSST, SSTEmail, User, ActivityLog
from server.routers.auth import get_current_user, require_permission

router = APIRouter(prefix="/sst", tags=["Sous-traitants"])


# ============== Schemas Pydantic ==============

class SSTBase(BaseModel):
    """Donnees de base d'un SST"""
    code: str
    nom: str
    raison_sociale: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    adresse: Optional[str] = None
    is_active: bool = True
    commentaire: Optional[str] = None


class SSTCreate(SSTBase):
    """Creation d'un SST"""
    pass


class SSTUpdate(BaseModel):
    """Mise a jour d'un SST"""
    code: Optional[str] = None
    nom: Optional[str] = None
    raison_sociale: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    adresse: Optional[str] = None
    is_active: Optional[bool] = None
    commentaire: Optional[str] = None


class SSTResponse(SSTBase):
    """Reponse avec les donnees completes d'un SST"""
    id: int
    uuid: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TarifSSTBase(BaseModel):
    """Donnees de base d'un tarif SST"""
    destination: str
    pays: Optional[str] = None
    prix: float
    unite: str = "voyage"
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    is_active: bool = True


class TarifSSTCreate(TarifSSTBase):
    """Creation d'un tarif"""
    sst_id: int


class TarifSSTUpdate(BaseModel):
    """Mise a jour d'un tarif"""
    destination: Optional[str] = None
    pays: Optional[str] = None
    prix: Optional[float] = None
    unite: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    is_active: Optional[bool] = None


class TarifSSTResponse(TarifSSTBase):
    """Reponse tarif"""
    id: int
    sst_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SSTEmailBase(BaseModel):
    """Donnees email SST"""
    email: str
    nom_contact: Optional[str] = None
    fonction: Optional[str] = None
    is_primary: bool = False


class SSTEmailCreate(SSTEmailBase):
    """Creation email"""
    sst_id: int


class SSTEmailResponse(SSTEmailBase):
    """Reponse email"""
    id: int
    sst_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============== Endpoints SST ==============

@router.get("/", response_model=List[SSTResponse])
async def list_sst(
    active_only: bool = Query(True, description="Afficher uniquement les SST actifs"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Liste tous les sous-traitants"""
    query = select(SST).order_by(SST.nom)

    if active_only:
        query = query.where(SST.is_active == True)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{sst_id}", response_model=SSTResponse)
async def get_sst(
    sst_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere un SST par son ID"""
    result = await db.execute(select(SST).where(SST.id == sst_id))
    sst = result.scalar_one_or_none()

    if not sst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST {sst_id} non trouve"
        )

    return sst


@router.get("/code/{code}", response_model=SSTResponse)
async def get_sst_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere un SST par son code"""
    result = await db.execute(select(SST).where(SST.code == code.upper()))
    sst = result.scalar_one_or_none()

    if not sst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST avec code '{code}' non trouve"
        )

    return sst


@router.post("/", response_model=SSTResponse, status_code=status.HTTP_201_CREATED)
async def create_sst(
    sst_data: SSTCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Cree un nouveau SST"""

    # Verifier que le code n'existe pas
    existing = await db.execute(
        select(SST).where(SST.code == sst_data.code.upper())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Un SST avec le code '{sst_data.code}' existe deja"
        )

    sst = SST(
        uuid=str(uuid.uuid4()),
        **sst_data.model_dump()
    )
    sst.code = sst.code.upper()

    db.add(sst)
    await db.commit()
    await db.refresh(sst)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="sst",
        entity_id=str(sst.id)
    )
    db.add(log_entry)
    await db.commit()

    return sst


@router.put("/{sst_id}", response_model=SSTResponse)
async def update_sst(
    sst_id: int,
    sst_data: SSTUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Met a jour un SST"""

    result = await db.execute(select(SST).where(SST.id == sst_id))
    sst = result.scalar_one_or_none()

    if not sst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST {sst_id} non trouve"
        )

    # Appliquer les modifications
    update_data = sst_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "code" and value:
            value = value.upper()
        setattr(sst, field, value)

    await db.commit()
    await db.refresh(sst)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="UPDATE",
        entity_type="sst",
        entity_id=str(sst.id)
    )
    db.add(log_entry)
    await db.commit()

    return sst


@router.delete("/{sst_id}")
async def delete_sst(
    sst_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Desactive un SST"""

    result = await db.execute(select(SST).where(SST.id == sst_id))
    sst = result.scalar_one_or_none()

    if not sst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST {sst_id} non trouve"
        )

    sst.is_active = False
    await db.commit()

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="DEACTIVATE",
        entity_type="sst",
        entity_id=str(sst_id)
    )
    db.add(log_entry)
    await db.commit()

    return {"success": True, "message": f"SST {sst_id} desactive"}


# ============== Endpoints Tarifs ==============

@router.get("/{sst_id}/tarifs", response_model=List[TarifSSTResponse])
async def get_sst_tarifs(
    sst_id: int,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere les tarifs d'un SST"""

    query = select(TarifSST).where(TarifSST.sst_id == sst_id)

    if active_only:
        query = query.where(TarifSST.is_active == True)

    query = query.order_by(TarifSST.destination)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tarifs/all", response_model=List[TarifSSTResponse])
async def get_all_tarifs(
    sst_code: Optional[str] = None,
    destination: Optional[str] = None,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere tous les tarifs avec filtres optionnels"""

    query = select(TarifSST)

    if active_only:
        query = query.where(TarifSST.is_active == True)

    if destination:
        query = query.where(TarifSST.destination.ilike(f"%{destination}%"))

    if sst_code:
        # Joindre avec SST pour filtrer par code
        query = query.join(SST).where(SST.code == sst_code.upper())

    query = query.order_by(TarifSST.destination)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/tarifs", response_model=TarifSSTResponse, status_code=status.HTTP_201_CREATED)
async def create_tarif(
    tarif_data: TarifSSTCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Cree un nouveau tarif SST"""

    # Verifier que le SST existe
    sst_result = await db.execute(select(SST).where(SST.id == tarif_data.sst_id))
    if not sst_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST {tarif_data.sst_id} non trouve"
        )

    tarif = TarifSST(**tarif_data.model_dump())

    db.add(tarif)
    await db.commit()
    await db.refresh(tarif)

    # Logger l'action
    log_entry = ActivityLog(
        username=current_user.username,
        action_type="CREATE",
        entity_type="tarif_sst",
        entity_id=str(tarif.id)
    )
    db.add(log_entry)
    await db.commit()

    return tarif


@router.put("/tarifs/{tarif_id}", response_model=TarifSSTResponse)
async def update_tarif(
    tarif_id: int,
    tarif_data: TarifSSTUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Met a jour un tarif"""

    result = await db.execute(select(TarifSST).where(TarifSST.id == tarif_id))
    tarif = result.scalar_one_or_none()

    if not tarif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarif {tarif_id} non trouve"
        )

    # Appliquer les modifications
    update_data = tarif_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tarif, field, value)

    await db.commit()
    await db.refresh(tarif)

    return tarif


@router.delete("/tarifs/{tarif_id}")
async def delete_tarif(
    tarif_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Supprime un tarif"""

    result = await db.execute(select(TarifSST).where(TarifSST.id == tarif_id))
    tarif = result.scalar_one_or_none()

    if not tarif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarif {tarif_id} non trouve"
        )

    await db.delete(tarif)
    await db.commit()

    return {"success": True, "message": f"Tarif {tarif_id} supprime"}


# ============== Endpoints Emails ==============

@router.get("/{sst_id}/emails", response_model=List[SSTEmailResponse])
async def get_sst_emails(
    sst_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("view_finance"))
):
    """Recupere les emails d'un SST"""

    result = await db.execute(
        select(SSTEmail)
        .where(SSTEmail.sst_id == sst_id)
        .order_by(SSTEmail.is_primary.desc(), SSTEmail.email)
    )
    return result.scalars().all()


@router.post("/emails", response_model=SSTEmailResponse, status_code=status.HTTP_201_CREATED)
async def create_sst_email(
    email_data: SSTEmailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Ajoute un email a un SST"""

    # Verifier que le SST existe
    sst_result = await db.execute(select(SST).where(SST.id == email_data.sst_id))
    if not sst_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SST {email_data.sst_id} non trouve"
        )

    sst_email = SSTEmail(**email_data.model_dump())

    db.add(sst_email)
    await db.commit()
    await db.refresh(sst_email)

    return sst_email


@router.delete("/emails/{email_id}")
async def delete_sst_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("manage_finance"))
):
    """Supprime un email"""

    result = await db.execute(select(SSTEmail).where(SSTEmail.id == email_id))
    email = result.scalar_one_or_none()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email {email_id} non trouve"
        )

    await db.delete(email)
    await db.commit()

    return {"success": True, "message": f"Email {email_id} supprime"}
