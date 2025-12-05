"""
Modèles pour la gestion financière
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from server.database import Base


class RevenuPalette(Base):
    """Revenus par palette selon destination"""
    __tablename__ = "revenus_palettes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Destination
    destination: Mapped[str] = mapped_column(String(255), index=True)
    pays: Mapped[Optional[str]] = mapped_column(String(100))

    # Revenu
    revenu_par_palette: Mapped[float] = mapped_column(Float)

    # Validité
    date_debut: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_fin: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Métadonnées
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<RevenuPalette(destination='{self.destination}', revenu={self.revenu_par_palette})>"
