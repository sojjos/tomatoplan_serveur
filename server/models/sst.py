"""
Modèles pour les sous-traitants (SST)
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class SST(Base):
    """Sous-traitants"""
    __tablename__ = "sst"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Identification
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(255))
    raison_sociale: Mapped[Optional[str]] = mapped_column(String(255))

    # Contact
    telephone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    adresse: Mapped[Optional[str]] = mapped_column(Text)

    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    commentaire: Mapped[Optional[str]] = mapped_column(Text)

    # Métadonnées
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    tarifs: Mapped[List["TarifSST"]] = relationship(back_populates="sst", cascade="all, delete-orphan")
    emails: Mapped[List["SSTEmail"]] = relationship(back_populates="sst", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SST(id={self.id}, code='{self.code}', nom='{self.nom}')>"


class TarifSST(Base):
    """Tarifs des sous-traitants par destination"""
    __tablename__ = "tarifs_sst"

    id: Mapped[int] = mapped_column(primary_key=True)
    sst_id: Mapped[int] = mapped_column(ForeignKey("sst.id"))
    sst: Mapped["SST"] = relationship(back_populates="tarifs")

    # Destination
    destination: Mapped[str] = mapped_column(String(255), index=True)
    pays: Mapped[Optional[str]] = mapped_column(String(100))

    # Tarif
    prix: Mapped[float] = mapped_column(Float)
    unite: Mapped[str] = mapped_column(String(20), default="voyage")  # voyage, palette, km

    # Validité
    date_debut: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_fin: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Métadonnées
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TarifSST(sst_id={self.sst_id}, destination='{self.destination}', prix={self.prix})>"


class SSTEmail(Base):
    """Emails des contacts SST"""
    __tablename__ = "sst_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    sst_id: Mapped[int] = mapped_column(ForeignKey("sst.id"))
    sst: Mapped["SST"] = relationship(back_populates="emails")

    email: Mapped[str] = mapped_column(String(255))
    nom_contact: Mapped[Optional[str]] = mapped_column(String(100))
    fonction: Mapped[Optional[str]] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SSTEmail(sst_id={self.sst_id}, email='{self.email}')>"
