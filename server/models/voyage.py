"""
Modèle Voyage (ligne régulière de transport)
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class Voyage(Base):
    """Voyages/Lignes de transport"""
    __tablename__ = "voyages"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Identification
    code: Mapped[str] = mapped_column(String(50), index=True)  # Code voyage (ex: V001, LUX-01)
    nom: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Trajet
    depart: Mapped[Optional[str]] = mapped_column(String(255))
    destination: Mapped[Optional[str]] = mapped_column(String(255))
    pays_destination: Mapped[Optional[str]] = mapped_column(String(100))

    # Horaires par défaut
    heure_depart_defaut: Mapped[Optional[str]] = mapped_column(String(5))
    heure_arrivee_defaut: Mapped[Optional[str]] = mapped_column(String(5))

    # Jours d'opération (JSON: ["lundi", "mardi", ...])
    jours_operation: Mapped[Optional[str]] = mapped_column(JSON)

    # Volumes moyens
    nb_palettes_moyen: Mapped[Optional[int]] = mapped_column(Integer)

    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Couleur pour l'affichage
    couleur: Mapped[Optional[str]] = mapped_column(String(20))

    # Métadonnées
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    missions: Mapped[List["Mission"]] = relationship(back_populates="voyage")

    def __repr__(self):
        return f"<Voyage(id={self.id}, code='{self.code}', nom='{self.nom}')>"


# Import pour éviter les imports circulaires
from server.models.mission import Mission
