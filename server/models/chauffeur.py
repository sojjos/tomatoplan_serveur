"""
Modèle Chauffeur
"""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Date, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class Chauffeur(Base):
    """Chauffeurs de l'entreprise"""
    __tablename__ = "chauffeurs"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)

    # Identification
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # Code court (ex: JD01)
    nom: Mapped[str] = mapped_column(String(100))
    prenom: Mapped[str] = mapped_column(String(100))

    # Contact
    telephone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # Informations professionnelles
    type_contrat: Mapped[Optional[str]] = mapped_column(String(50))  # CDI, CDD, interim
    date_embauche: Mapped[Optional[date]] = mapped_column(Date)

    # Permis et habilitations
    permis: Mapped[Optional[str]] = mapped_column(String(50))  # C, CE, etc.
    adr: Mapped[bool] = mapped_column(Boolean, default=False)  # Formation ADR matières dangereuses
    fimo: Mapped[bool] = mapped_column(Boolean, default=True)  # Formation initiale minimale obligatoire

    # Véhicule attitré
    tracteur_attire: Mapped[Optional[str]] = mapped_column(String(50))

    # Compétences/Préférences (JSON)
    competences: Mapped[Optional[str]] = mapped_column(Text)  # JSON list des compétences
    zones_preferees: Mapped[Optional[str]] = mapped_column(Text)  # JSON list des zones

    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    commentaire: Mapped[Optional[str]] = mapped_column(Text)

    # Métadonnées
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    missions: Mapped[List["Mission"]] = relationship(back_populates="chauffeur")
    disponibilites: Mapped[List["ChauffeurDispo"]] = relationship(back_populates="chauffeur", cascade="all, delete-orphan")

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"

    def __repr__(self):
        return f"<Chauffeur(id={self.id}, code='{self.code}', nom='{self.nom_complet}')>"


class ChauffeurDispo(Base):
    """Disponibilités des chauffeurs"""
    __tablename__ = "chauffeur_dispo"

    id: Mapped[int] = mapped_column(primary_key=True)
    chauffeur_id: Mapped[int] = mapped_column(ForeignKey("chauffeurs.id"))
    chauffeur: Mapped["Chauffeur"] = relationship(back_populates="disponibilites")

    # Période
    date_debut: Mapped[date] = mapped_column(Date, index=True)
    date_fin: Mapped[date] = mapped_column(Date, index=True)

    # Type d'indisponibilité
    type_absence: Mapped[str] = mapped_column(String(50))  # conges, maladie, formation, autre
    motif: Mapped[Optional[str]] = mapped_column(String(255))

    # Métadonnées
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ChauffeurDispo(chauffeur_id={self.chauffeur_id}, du={self.date_debut} au={self.date_fin})>"


# Import pour éviter les imports circulaires
from server.models.mission import Mission
