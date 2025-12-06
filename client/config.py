"""
Configuration du client TomatoPlan
===================================

Modifiez ces valeurs selon votre environnement.
"""

# URL du serveur TomatoPlan
SERVER_URL = "https://54.37.231.92"

# Verification SSL (False pour certificats auto-signes)
VERIFY_SSL = False

# Timeout des requetes (secondes)
TIMEOUT = 30

# Intervalle de verification du statut (secondes)
STATUS_CHECK_INTERVAL = 5

# TTL du cache local (secondes)
CACHE_TTL = 30

# Delai de reconnexion WebSocket (secondes)
WS_RECONNECT_DELAY = 5

# Version du client
CLIENT_VERSION = "1.0.0"
