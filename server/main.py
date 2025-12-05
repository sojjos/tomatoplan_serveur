"""
TomatoPlan Server - Application principale FastAPI

Point d'entrée du serveur API REST pour la gestion de planning transport.
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, time as dt_time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from server.config import settings, get_log_path
from server.database import init_db, close_db, async_session_maker, Base, engine
from server.middleware.logging import LoggingMiddleware
from server.routers import (
    auth_router,
    missions_router,
    voyages_router,
    chauffeurs_router,
    admin_router,
    stats_router,
)
from server.models import UserRole, User
from server.services.backup_service import BackupService

# ============== Configuration du logging ==============

def setup_logging():
    """Configure le système de logging"""
    log_path = get_log_path()

    # Créer le formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler fichier
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    # Handler console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configurer le logger principal
    logger = logging.getLogger("tomatoplan")
    logger.setLevel(getattr(logging, settings.log_level.upper()))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Réduire le bruit des autres loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return logger


logger = setup_logging()


# ============== Initialisation des données ==============

async def init_default_roles():
    """Crée les rôles par défaut s'ils n'existent pas"""
    async with async_session_maker() as db:
        # Vérifier si les rôles existent
        result = await db.execute(select(UserRole).limit(1))
        if result.scalar_one_or_none():
            return  # Rôles déjà créés

        logger.info("Création des rôles par défaut...")

        roles = [
            UserRole(
                name="viewer",
                description="Consultation uniquement",
                view_planning=True,
                view_drivers=True,
            ),
            UserRole(
                name="planner",
                description="Planificateur - peut modifier le planning",
                view_planning=True,
                edit_planning=True,
                view_drivers=True,
                manage_voyages=True,
                send_announcements=True,
            ),
            UserRole(
                name="planner_advanced",
                description="Planificateur avancé - accès étendu",
                view_planning=True,
                edit_planning=True,
                view_drivers=True,
                manage_voyages=True,
                edit_past_planning=True,
                edit_past_planning_advanced=True,
                view_finance=True,
                send_announcements=True,
                manage_announcements_config=True,
            ),
            UserRole(
                name="driver_admin",
                description="Gestionnaire des chauffeurs",
                view_planning=True,
                view_drivers=True,
                manage_drivers=True,
                edit_driver_planning=True,
            ),
            UserRole(
                name="finance",
                description="Accès aux données financières",
                view_planning=True,
                view_finance=True,
                manage_finance=True,
            ),
            UserRole(
                name="analyse",
                description="Accès aux analyses et statistiques",
                view_planning=True,
                view_drivers=True,
                view_finance=True,
                view_analyse=True,
            ),
            UserRole(
                name="admin",
                description="Administrateur complet",
                view_planning=True,
                edit_planning=True,
                view_drivers=True,
                manage_drivers=True,
                edit_driver_planning=True,
                manage_rights=True,
                manage_voyages=True,
                generate_planning=True,
                edit_past_planning=True,
                edit_past_planning_advanced=True,
                view_finance=True,
                manage_finance=True,
                view_analyse=True,
                view_sauron=True,
                send_announcements=True,
                manage_announcements_config=True,
                admin_access=True,
            ),
        ]

        for role in roles:
            db.add(role)

        await db.commit()
        logger.info(f"  {len(roles)} rôles créés")


async def init_default_admin():
    """Crée l'utilisateur admin par défaut si configuré"""
    if not settings.default_admin_enabled:
        return

    async with async_session_maker() as db:
        # Vérifier si des utilisateurs existent
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            return  # Des utilisateurs existent déjà

        logger.info("Création de l'utilisateur admin par défaut...")

        # Récupérer le rôle admin
        role_result = await db.execute(
            select(UserRole).where(UserRole.name == "admin")
        )
        admin_role = role_result.scalar_one_or_none()

        admin_user = User(
            username=settings.default_admin_username.upper(),
            display_name="Administrateur",
            role=admin_role,
            is_active=True,
            is_system_admin=True,
        )

        db.add(admin_user)
        await db.commit()
        logger.info(f"  Admin créé: {admin_user.username}")


# ============== Tâches de fond ==============

class BackgroundTasks:
    """Gestionnaire des tâches de fond"""

    def __init__(self):
        self._task = None
        self._stop = False

    async def start(self):
        """Démarre les tâches de fond"""
        self._stop = False
        self._task = asyncio.create_task(self._run())
        logger.info("Tâches de fond démarrées")

    async def stop(self):
        """Arrête les tâches de fond"""
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Tâches de fond arrêtées")

    async def _run(self):
        """Boucle principale des tâches de fond"""
        while not self._stop:
            try:
                now = datetime.now()

                # Backup automatique quotidien
                if (
                    settings.auto_backup_enabled
                    and now.hour == settings.auto_backup_hour
                    and now.minute == 0
                ):
                    logger.info("Démarrage du backup automatique...")
                    try:
                        result = await BackupService.create_backup("Backup automatique")
                        logger.info(f"Backup créé: {result['backup_file']}")

                        # Nettoyage des anciens backups
                        deleted = await BackupService.cleanup_old_backups()
                        if deleted > 0:
                            logger.info(f"Nettoyage: {deleted} ancien(s) backup(s) supprimé(s)")
                    except Exception as e:
                        logger.error(f"Erreur backup automatique: {e}")

                # Attendre 1 minute avant la prochaine vérification
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur dans les tâches de fond: {e}")
                await asyncio.sleep(60)


background_tasks = BackgroundTasks()


# ============== Cycle de vie de l'application ==============

# Variable globale pour stocker l'heure de démarrage
server_start_time: datetime = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire du cycle de vie de l'application"""
    global server_start_time

    # Démarrage
    logger.info("=" * 60)
    logger.info(f"Démarrage de {settings.app_name} v{settings.app_version}")
    logger.info("=" * 60)

    server_start_time = datetime.now()

    # Initialiser la base de données
    logger.info("Initialisation de la base de données...")
    await init_db()
    await init_default_roles()
    await init_default_admin()
    logger.info("Base de données initialisée")

    # Démarrer les tâches de fond
    await background_tasks.start()

    logger.info(f"Serveur prêt sur http://{settings.host}:{settings.port}")
    logger.info("=" * 60)

    yield

    # Arrêt
    logger.info("Arrêt du serveur...")
    await background_tasks.stop()
    await close_db()
    logger.info("Serveur arrêté proprement")


# ============== Application FastAPI ==============

app = FastAPI(
    title=settings.app_name,
    description="API REST pour la gestion de planning transport",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS pour permettre les requêtes depuis les clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les origines autorisées
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de logging
app.add_middleware(LoggingMiddleware)

# Monter les fichiers statiques pour l'admin
static_path = Path(__file__).parent / "admin" / "static"
if static_path.exists():
    app.mount("/admin/static", StaticFiles(directory=static_path), name="static")

# Templates pour l'admin
templates_path = Path(__file__).parent / "admin" / "templates"
templates = Jinja2Templates(directory=templates_path) if templates_path.exists() else None


# ============== Routes API ==============

app.include_router(auth_router)
app.include_router(missions_router)
app.include_router(voyages_router)
app.include_router(chauffeurs_router)
app.include_router(admin_router)
app.include_router(stats_router)


# ============== Endpoints de base ==============

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Page d'accueil - redirige vers l'admin ou affiche les infos API"""
    if templates:
        return templates.TemplateResponse("index.html", {"request": request})

    return HTMLResponse(f"""
    <html>
    <head>
        <title>{settings.app_name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #2c3e50; }}
            .info {{ background: #ecf0f1; padding: 15px; border-radius: 4px; margin: 10px 0; }}
            a {{ color: #3498db; }}
            .status {{ color: #27ae60; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{settings.app_name}</h1>
            <p class="status">Serveur en cours d'exécution</p>
            <div class="info">
                <strong>Version:</strong> {settings.app_version}<br>
                <strong>Documentation API:</strong> <a href="/docs">/docs</a><br>
                <strong>API OpenAPI:</strong> <a href="/openapi.json">/openapi.json</a>
            </div>
            <h2>Endpoints disponibles</h2>
            <ul>
                <li><code>POST /auth/login</code> - Authentification</li>
                <li><code>GET /missions</code> - Liste des missions</li>
                <li><code>GET /voyages</code> - Liste des voyages</li>
                <li><code>GET /chauffeurs</code> - Liste des chauffeurs</li>
                <li><code>GET /stats/dashboard</code> - Statistiques</li>
                <li><code>GET /admin/*</code> - Administration</li>
            </ul>
        </div>
    </body>
    </html>
    """)


@app.get("/health")
async def health_check():
    """Vérification de l'état du serveur"""
    global server_start_time

    uptime_seconds = 0
    if server_start_time:
        uptime_seconds = int((datetime.now() - server_start_time).total_seconds())

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": format_uptime(uptime_seconds),
        "version": settings.app_version,
    }


@app.get("/server-info")
async def server_info():
    """Informations sur le serveur (pour les clients)"""
    global server_start_time

    uptime_seconds = 0
    if server_start_time:
        uptime_seconds = int((datetime.now() - server_start_time).total_seconds())

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "host": settings.host,
        "port": settings.port,
        "started_at": server_start_time.isoformat() if server_start_time else None,
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": format_uptime(uptime_seconds),
    }


def format_uptime(seconds: int) -> str:
    """Formate une durée en secondes en format lisible"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


# ============== Point d'entrée ==============

def main():
    """Point d'entrée pour lancer le serveur"""
    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
