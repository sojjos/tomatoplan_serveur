"""
Modèle Mission de transport
"""

from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Date, Time, Float, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class Mission(Base):
    """Missions de transport"""
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)  # UUID pour sync client

    # Informations de base
    date_mission: Mapped[date] = mapped_column(Date, index=True)
    heure_debut: Mapped[Optional[str]] = mapped_column(String(5))  # Format HH:MM
    heure_fin: Mapped[Optional[str]] = mapped_column(String(5))

    # Voyage associé
    voyage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("voyages.id"))
    voyage: Mapped[Optional["Voyage"]] = relationship(back_populates="missions")

    # Chauffeur assigné
    chauffeur_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chauffeurs.id"))
    chauffeur: Mapped[Optional["Chauffeur"]] = relationship(back_populates="missions")

    # Sous-traitant (si applicable)
    sst_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sst.id"))
    sst: Mapped[Optional["SST"]] = relationship()

    # Détails mission
    type_mission: Mapped[Optional[str]] = mapped_column(String(50))  # livraison, ramasse, etc.
    destination: Mapped[Optional[str]] = mapped_column(String(255))
    depart: Mapped[Optional[str]] = mapped_column(String(255))
    pays: Mapped[Optional[str]] = mapped_column(String(100))

    # Volumes
    nb_palettes: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    poids_kg: Mapped[Optional[float]] = mapped_column(Float)

    # Véhicule
    tracteur: Mapped[Optional[str]] = mapped_column(String(50))
    remorque: Mapped[Optional[str]] = mapped_column(String(50))

    # Statut
    statut: Mapped[str] = mapped_column(String(50), default="planifie")  # planifie, en_cours, termine, annule
    commentaire: Mapped[Optional[str]] = mapped_column(Text)

    # Finances
    cout_sst: Mapped[Optional[float]] = mapped_column(Float)
    revenu: Mapped[Optional[float]] = mapped_column(Float)

    # Métadonnées
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Mission(id={self.id}, date={self.date_mission}, destination='{self.destination}')>"


# Import nécessaire pour les relations
from server.models.voyage import Voyage
from server.models.chauffeur import Chauffeur
from server.models.sst import SST
