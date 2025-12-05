"""
Modèles pour le logging des activités
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from server.database import Base


class ActivityLog(Base):
    """Journal des activités utilisateurs (équivalent au système SAURON)"""
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Utilisateur
    username: Mapped[str] = mapped_column(String(100), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Action
    action_type: Mapped[str] = mapped_column(String(50), index=True)  # CREATE, UPDATE, DELETE, VIEW, LOGIN, LOGOUT
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))  # mission, voyage, chauffeur, etc.
    entity_id: Mapped[Optional[str]] = mapped_column(String(50))

    # Détails
    details: Mapped[Optional[str]] = mapped_column(JSON)
    before_state: Mapped[Optional[str]] = mapped_column(JSON)  # État avant modification
    after_state: Mapped[Optional[str]] = mapped_column(JSON)   # État après modification

    # Contexte
    client_ip: Mapped[Optional[str]] = mapped_column(String(50))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Index composites pour les recherches fréquentes
    __table_args__ = (
        Index('ix_activity_user_date', 'username', 'created_at'),
        Index('ix_activity_type_date', 'action_type', 'created_at'),
    )

    def __repr__(self):
        return f"<ActivityLog(id={self.id}, user='{self.username}', action='{self.action_type}')>"


class ApiRequestLog(Base):
    """Journal des requêtes API (pour statistiques et monitoring)"""
    __tablename__ = "api_request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Requête
    method: Mapped[str] = mapped_column(String(10))  # GET, POST, PUT, DELETE
    path: Mapped[str] = mapped_column(String(500))
    query_params: Mapped[Optional[str]] = mapped_column(Text)

    # Utilisateur
    username: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50))

    # Réponse
    status_code: Mapped[int] = mapped_column(Integer)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Erreur éventuelle
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Index pour les stats
    __table_args__ = (
        Index('ix_api_path_date', 'path', 'created_at'),
        Index('ix_api_status_date', 'status_code', 'created_at'),
    )

    def __repr__(self):
        return f"<ApiRequestLog(id={self.id}, {self.method} {self.path} -> {self.status_code})>"
