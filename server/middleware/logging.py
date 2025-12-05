"""
Middleware de logging des requêtes API
"""

import time
import logging
from datetime import datetime
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import async_session_maker
from server.models import ApiRequestLog

logger = logging.getLogger("tomatoplan")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware pour logger toutes les requêtes API"""

    # Chemins à exclure du logging (pour éviter le bruit)
    EXCLUDED_PATHS = [
        "/health",
        "/favicon.ico",
        "/admin/static",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Vérifier si le chemin est exclu
        for excluded in self.EXCLUDED_PATHS:
            if request.url.path.startswith(excluded):
                return await call_next(request)

        # Mesurer le temps de réponse
        start_time = time.time()

        # Extraire les informations de la requête
        method = request.method
        path = request.url.path
        query_params = str(request.query_params) if request.query_params else None
        client_ip = request.client.host if request.client else None

        # Extraire le username du token si disponible
        username = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Le username sera extrait plus tard si nécessaire
            pass

        # Appeler le endpoint
        response = None
        error_message = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            error_message = str(e)
            logger.exception(f"Erreur lors de la requête {method} {path}")
            raise

        # Calculer le temps de réponse
        response_time = int((time.time() - start_time) * 1000)

        # Logger dans la base de données (en asynchrone)
        try:
            async with async_session_maker() as db:
                log_entry = ApiRequestLog(
                    method=method,
                    path=path,
                    query_params=query_params,
                    username=username,
                    client_ip=client_ip,
                    status_code=status_code,
                    response_time_ms=response_time,
                    error_message=error_message
                )
                db.add(log_entry)
                await db.commit()
        except Exception as e:
            # Ne pas faire échouer la requête si le logging échoue
            logger.warning(f"Impossible de logger la requête: {e}")

        # Logger aussi dans les logs texte
        log_level = logging.INFO if status_code < 400 else logging.WARNING
        logger.log(
            log_level,
            f"{method} {path} - {status_code} ({response_time}ms)"
        )

        return response
