"""
Modèles utilisateurs et authentification
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class UserRole(Base):
    """Rôles disponibles dans le système"""
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    # Permissions (basées sur l'application originale)
    view_planning: Mapped[bool] = mapped_column(Boolean, default=True)
    edit_planning: Mapped[bool] = mapped_column(Boolean, default=False)
    view_drivers: Mapped[bool] = mapped_column(Boolean, default=True)
    manage_drivers: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_driver_planning: Mapped[bool] = mapped_column(Boolean, default=False)
    manage_rights: Mapped[bool] = mapped_column(Boolean, default=False)
    manage_voyages: Mapped[bool] = mapped_column(Boolean, default=False)
    generate_planning: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_past_planning: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_past_planning_advanced: Mapped[bool] = mapped_column(Boolean, default=False)
    view_finance: Mapped[bool] = mapped_column(Boolean, default=False)
    manage_finance: Mapped[bool] = mapped_column(Boolean, default=False)
    view_analyse: Mapped[bool] = mapped_column(Boolean, default=False)
    view_sauron: Mapped[bool] = mapped_column(Boolean, default=False)
    send_announcements: Mapped[bool] = mapped_column(Boolean, default=False)
    manage_announcements_config: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_access: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    users: Mapped[List["User"]] = relationship(back_populates="role")


class User(Base):
    """Utilisateurs du système"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # ex: DOMAIN\username ou username
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # Authentification par mot de passe (obligatoire pour accès Internet)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)  # Forcer changement au 1er login
    failed_login_attempts: Mapped[int] = mapped_column(default=0)  # Compteur tentatives échouées
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)  # Verrouillage temporaire

    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # Admin système (peut tout faire)

    # Rôle
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_roles.id"))
    role: Mapped[Optional["UserRole"]] = relationship(back_populates="users")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relations
    sessions: Mapped[List["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class UserSession(Base):
    """Sessions utilisateurs actives"""
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="sessions")

    # Informations de connexion
    client_ip: Mapped[Optional[str]] = mapped_column(String(50))
    client_hostname: Mapped[Optional[str]] = mapped_column(String(255))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    # Statut
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, active={self.is_active})>"
