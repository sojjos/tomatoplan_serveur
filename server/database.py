"""
Configuration de la base de données SQLite
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from server.config import get_database_url

# Moteur de base de données asynchrone
engine = create_async_engine(
    get_database_url(),
    echo=False,
    future=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy"""
    pass


async def get_db() -> AsyncSession:
    """Dépendance FastAPI pour obtenir une session de base de données"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialiser la base de données (créer les tables)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Fermer proprement la connexion à la base de données"""
    await engine.dispose()
