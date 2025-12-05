"""
Routers API pour TomatoPlan
"""

from server.routers.auth import router as auth_router
from server.routers.missions import router as missions_router
from server.routers.voyages import router as voyages_router
from server.routers.chauffeurs import router as chauffeurs_router
from server.routers.admin import router as admin_router
from server.routers.stats import router as stats_router
from server.routers.sst import router as sst_router
from server.routers.finance import router as finance_router

__all__ = [
    "auth_router",
    "missions_router",
    "voyages_router",
    "chauffeurs_router",
    "admin_router",
    "stats_router",
    "sst_router",
    "finance_router",
]
