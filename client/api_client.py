"""
Client API TomatoPlan
=====================

Module pour communiquer avec le serveur TomatoPlan via REST API et WebSocket.
"""

import json
import socket
import ssl
import threading
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

import requests
import urllib3

from config import (
    SERVER_URL,
    VERIFY_SSL,
    TIMEOUT,
    STATUS_CHECK_INTERVAL,
    CACHE_TTL,
    WS_RECONNECT_DELAY,
)

# Desactiver les warnings SSL pour certificats auto-signes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# CLIENT API
# ============================================================================

class APIClient:
    """Client API REST pour TomatoPlan (singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.server_url = SERVER_URL.rstrip("/")
        self.verify_ssl = VERIFY_SSL
        self.timeout = TIMEOUT
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None
        self.must_change_password = False
        self._session = requests.Session()
        self._lock = threading.Lock()

        # Cache local
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = CACHE_TTL

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, endpoint: str, data=None, params=None, use_cache=False):
        """Execute une requete API"""
        url = f"{self.server_url}{endpoint}"
        cache_key = f"{method}:{endpoint}:{json.dumps(params or {})}"

        # Verifier le cache
        if use_cache and method == "GET":
            with self._lock:
                if cache_key in self._cache:
                    ts = self._cache_timestamps.get(cache_key, 0)
                    if datetime.now().timestamp() - ts < self._cache_ttl:
                        return self._cache[cache_key]

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=data,
                params=params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )

            if response.status_code == 401:
                self.token = None
                raise PermissionError("Session expiree, reconnexion necessaire")

            if response.status_code == 403:
                raise PermissionError(f"Acces refuse: {response.json().get('detail', '')}")

            if response.status_code == 404:
                return None

            if response.status_code >= 400:
                error_detail = response.json().get("detail", "Erreur inconnue")
                raise Exception(f"Erreur API ({response.status_code}): {error_detail}")

            result = response.json() if response.content else {"success": True}

            # Mettre en cache
            if use_cache and method == "GET":
                with self._lock:
                    self._cache[cache_key] = result
                    self._cache_timestamps[cache_key] = datetime.now().timestamp()

            return result

        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Impossible de se connecter au serveur {self.server_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Le serveur ne repond pas (timeout: {self.timeout}s)")

    def invalidate_cache(self, pattern: str = None):
        """Invalide le cache (tout ou par pattern)"""
        with self._lock:
            if pattern:
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]
                    if k in self._cache_timestamps:
                        del self._cache_timestamps[k]
            else:
                self._cache.clear()
                self._cache_timestamps.clear()

    # ========== Authentification ==========

    def check_server(self) -> Dict:
        """Verifie si le serveur est accessible"""
        try:
            response = requests.get(
                f"{self.server_url}/health",
                timeout=5,
                verify=self.verify_ssl
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def login(self, username: str, password: str) -> bool:
        """Connexion au serveur"""
        hostname = socket.gethostname()

        response = self._request("POST", "/auth/login", {
            "username": username,
            "password": password,
            "hostname": hostname
        })

        if response and "access_token" in response:
            self.token = response["access_token"]
            self.user_info = response.get("user", {})
            self.must_change_password = response.get("must_change_password", False)
            return True
        return False

    def logout(self):
        """Deconnexion"""
        if self.token:
            try:
                self._request("POST", "/auth/logout")
            except Exception:
                pass
        self.token = None
        self.user_info = None

    def change_password(self, current_password: str, new_password: str) -> bool:
        """Changer le mot de passe"""
        response = self._request("POST", "/auth/change-password", {
            "current_password": current_password,
            "new_password": new_password
        })
        if response and response.get("success"):
            self.must_change_password = False
            return True
        return False

    def get_permissions(self) -> Dict:
        """Retourne les permissions de l'utilisateur"""
        if not self.user_info:
            return {}
        return self.user_info.get("permissions", {})

    # ========== Missions ==========

    def get_missions_by_date(self, d: date) -> List[Dict]:
        """Recupere les missions d'une date"""
        return self._request("GET", f"/missions/by-date/{d.isoformat()}", use_cache=True) or []

    def get_missions(self, date_debut=None, date_fin=None, **filters) -> List[Dict]:
        """Recupere les missions avec filtres"""
        params = {}
        if date_debut:
            params["date_debut"] = date_debut if isinstance(date_debut, str) else date_debut.isoformat()
        if date_fin:
            params["date_fin"] = date_fin if isinstance(date_fin, str) else date_fin.isoformat()
        params.update(filters)
        return self._request("GET", "/missions", params=params) or []

    def create_mission(self, data: Dict) -> Dict:
        """Cree une mission"""
        self.invalidate_cache("/missions")
        return self._request("POST", "/missions", data)

    def update_mission(self, mission_id: int, data: Dict) -> Dict:
        """Met a jour une mission"""
        self.invalidate_cache("/missions")
        return self._request("PUT", f"/missions/{mission_id}", data)

    def delete_mission(self, mission_id: int) -> bool:
        """Supprime une mission"""
        self.invalidate_cache("/missions")
        result = self._request("DELETE", f"/missions/{mission_id}")
        return result.get("success", False) if result else False

    # ========== Voyages ==========

    def get_voyages(self, active_only: bool = True) -> List[Dict]:
        """Recupere les voyages"""
        return self._request("GET", "/voyages", params={"active_only": active_only}, use_cache=True) or []

    def create_voyage(self, data: Dict) -> Dict:
        """Cree un voyage"""
        self.invalidate_cache("/voyages")
        return self._request("POST", "/voyages", data)

    def update_voyage(self, voyage_id: int, data: Dict) -> Dict:
        """Met a jour un voyage"""
        self.invalidate_cache("/voyages")
        return self._request("PUT", f"/voyages/{voyage_id}", data)

    # ========== Chauffeurs ==========

    def get_chauffeurs(self, active_only: bool = True) -> List[Dict]:
        """Recupere les chauffeurs"""
        return self._request("GET", "/chauffeurs", params={"active_only": active_only}, use_cache=True) or []

    def get_chauffeurs_disponibles(self, d: date) -> Dict:
        """Recupere les chauffeurs disponibles a une date"""
        return self._request("GET", f"/chauffeurs/disponibles/{d.isoformat()}") or {"disponibles": [], "indisponibles": []}

    def get_chauffeur_disponibilites(self, chauffeur_id: int, date_debut=None, date_fin=None) -> List[Dict]:
        """Recupere les indisponibilites d'un chauffeur"""
        params = {}
        if date_debut:
            params["date_debut"] = date_debut.isoformat() if isinstance(date_debut, date) else date_debut
        if date_fin:
            params["date_fin"] = date_fin.isoformat() if isinstance(date_fin, date) else date_fin
        return self._request("GET", f"/chauffeurs/{chauffeur_id}/disponibilites", params=params) or []

    def create_chauffeur(self, data: Dict) -> Dict:
        """Cree un chauffeur"""
        self.invalidate_cache("/chauffeurs")
        return self._request("POST", "/chauffeurs", data)

    def update_chauffeur(self, chauffeur_id: int, data: Dict) -> Dict:
        """Met a jour un chauffeur"""
        self.invalidate_cache("/chauffeurs")
        return self._request("PUT", f"/chauffeurs/{chauffeur_id}", data)

    def create_disponibilite(self, data: Dict) -> Dict:
        """Cree une indisponibilite"""
        return self._request("POST", "/chauffeurs/disponibilites", data)

    def delete_disponibilite(self, dispo_id: int) -> bool:
        """Supprime une indisponibilite"""
        result = self._request("DELETE", f"/chauffeurs/disponibilites/{dispo_id}")
        return result.get("success", False) if result else False

    # ========== SST ==========

    def get_sst_list(self, active_only: bool = True) -> List[Dict]:
        """Recupere les SST"""
        return self._request("GET", "/sst", params={"active_only": active_only}, use_cache=True) or []

    def get_sst_tarifs(self, sst_id: int = None) -> List[Dict]:
        """Recupere les tarifs SST"""
        if sst_id:
            return self._request("GET", f"/sst/{sst_id}/tarifs") or []
        return self._request("GET", "/sst/tarifs/all") or []

    def create_sst(self, data: Dict) -> Dict:
        """Cree un SST"""
        self.invalidate_cache("/sst")
        return self._request("POST", "/sst", data)

    def update_sst(self, sst_id: int, data: Dict) -> Dict:
        """Met a jour un SST"""
        self.invalidate_cache("/sst")
        return self._request("PUT", f"/sst/{sst_id}", data)

    # ========== Finance ==========

    def get_revenus_palettes(self) -> List[Dict]:
        """Recupere les revenus palettes"""
        return self._request("GET", "/finance/revenus", use_cache=True) or []

    def create_revenu_palette(self, data: Dict) -> Dict:
        """Cree un revenu palette"""
        self.invalidate_cache("/finance")
        return self._request("POST", "/finance/revenus", data)

    def get_finance_stats(self, date_debut: date, date_fin: date) -> Dict:
        """Recupere les statistiques financieres"""
        return self._request("GET", "/finance/stats", params={
            "date_debut": date_debut.isoformat(),
            "date_fin": date_fin.isoformat()
        }) or {}

    # ========== Stats ==========

    def get_dashboard_stats(self) -> Dict:
        """Recupere les stats du dashboard"""
        return self._request("GET", "/stats/dashboard") or {}

    def get_recent_activity(self, limit: int = 50, username: str = None) -> List[Dict]:
        """Recupere les activites recentes"""
        params = {"limit": limit}
        if username:
            params["username"] = username
        return self._request("GET", "/stats/activity/recent", params=params) or []

    # ========== Admin ==========

    def get_users(self) -> List[Dict]:
        """Recupere les utilisateurs"""
        return self._request("GET", "/admin/users") or []

    def get_roles(self) -> List[Dict]:
        """Recupere les roles"""
        return self._request("GET", "/admin/roles") or []

    def create_user(self, data: Dict) -> Dict:
        """Cree un utilisateur"""
        return self._request("POST", "/admin/users", data)

    def update_user(self, user_id: int, data: Dict) -> Dict:
        """Met a jour un utilisateur"""
        return self._request("PUT", f"/admin/users/{user_id}", data)


# ============================================================================
# MONITEUR DE CONNEXION
# ============================================================================

class ConnectionMonitor:
    """Moniteur de statut de connexion (singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._is_online = False
        self._last_check = None
        self._check_interval = STATUS_CHECK_INTERVAL
        self._callbacks: List[Callable] = []
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Demarre le monitoring"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrete le monitoring"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            self._check_connection()
            self._stop_event.wait(self._check_interval)

    def _check_connection(self):
        old_status = self._is_online
        try:
            result = api_client.check_server()
            self._is_online = result.get("status") == "ok"
        except Exception:
            self._is_online = False

        self._last_check = datetime.now()

        if old_status != self._is_online:
            for callback in self._callbacks:
                try:
                    callback(self._is_online)
                except Exception:
                    pass

    def add_callback(self, callback: Callable):
        """Ajoute un callback pour changement de statut"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    @property
    def is_online(self) -> bool:
        return self._is_online

    @property
    def status_text(self) -> str:
        return "En ligne" if self._is_online else "Hors ligne"

    def force_check(self) -> bool:
        self._check_connection()
        return self._is_online


# ============================================================================
# CLIENT WEBSOCKET (Synchronisation temps reel)
# ============================================================================

class LiveSyncClient:
    """Client WebSocket pour synchronisation multi-utilisateur (singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._ws = None
        self._thread = None
        self._stop_event = threading.Event()
        self._connected = False
        self._reconnect_delay = WS_RECONNECT_DELAY

        self._on_data_changed_callbacks: List[Callable] = []
        self._on_user_event_callbacks: List[Callable] = []
        self._on_connection_changed_callbacks: List[Callable] = []
        self._connected_users: List[str] = []

    def start(self):
        """Demarre la connexion WebSocket"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Arrete la connexion"""
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def _connection_loop(self):
        while not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as e:
                print(f"[WS] Erreur connexion: {e}")

            if not self._stop_event.is_set():
                self._stop_event.wait(self._reconnect_delay)

    def _connect(self):
        try:
            import websocket
        except ImportError:
            print("[WS] websocket-client non installe, mode temps reel desactive")
            return

        ws_url = SERVER_URL.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/ws"

        if api_client.token:
            ws_url = f"{ws_url}?token={api_client.token}"

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        ssl_opt = {"cert_reqs": ssl.CERT_NONE} if not VERIFY_SSL else None
        self._ws.run_forever(sslopt=ssl_opt)

    def _on_open(self, ws):
        self._connected = True
        print("[WS] Connecte - Mode temps reel actif")
        for callback in self._on_connection_changed_callbacks:
            try:
                callback(True)
            except Exception:
                pass

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "welcome":
                self._connected_users = data.get("connected_users", [])

            elif msg_type == "data_changed":
                change_data = data.get("data", {})
                entity = change_data.get("entity", "")
                action = change_data.get("action", "")

                api_client.invalidate_cache(f"/{entity}")

                for callback in self._on_data_changed_callbacks:
                    try:
                        callback(entity, action, change_data)
                    except Exception:
                        pass

            elif msg_type == "user_connected":
                username = data.get("data", {}).get("username", "")
                for callback in self._on_user_event_callbacks:
                    try:
                        callback("connected", username)
                    except Exception:
                        pass

            elif msg_type == "user_disconnected":
                username = data.get("data", {}).get("username", "")
                for callback in self._on_user_event_callbacks:
                    try:
                        callback("disconnected", username)
                    except Exception:
                        pass

            elif msg_type == "refresh_required":
                api_client.invalidate_cache()
                for callback in self._on_data_changed_callbacks:
                    try:
                        callback("all", "refresh", data.get("data", {}))
                    except Exception:
                        pass

        except Exception as e:
            print(f"[WS] Erreur message: {e}")

    def _on_error(self, ws, error):
        print(f"[WS] Erreur: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected = False
        for callback in self._on_connection_changed_callbacks:
            try:
                callback(False)
            except Exception:
                pass

    def on_data_changed(self, callback: Callable):
        """Enregistre callback pour changements de donnees"""
        if callback not in self._on_data_changed_callbacks:
            self._on_data_changed_callbacks.append(callback)

    def on_user_event(self, callback: Callable):
        """Enregistre callback pour evenements utilisateur"""
        if callback not in self._on_user_event_callbacks:
            self._on_user_event_callbacks.append(callback)

    def on_connection_changed(self, callback: Callable):
        """Enregistre callback pour changement de connexion"""
        if callback not in self._on_connection_changed_callbacks:
            self._on_connection_changed_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connected_users(self) -> List[str]:
        return self._connected_users.copy()

    @property
    def connected_users_count(self) -> int:
        return len(self._connected_users)


# ============================================================================
# FONCTIONS D'ADAPTATION POUR PTT
# ============================================================================

def api_load_json(filename, default=None):
    """Remplace load_json pour utiliser l'API"""
    filename_str = str(filename).lower()

    try:
        if "voyages.json" in filename_str:
            voyages = api_client.get_voyages(active_only=False)
            return [
                {
                    "code": v.get("code", ""),
                    "type": v.get("type", "LIVRAISON") if "type" in v else ("LIVRAISON" if v.get("is_livraison", True) else "RAMASSE"),
                    "actif": v.get("is_active", True),
                    "country": v.get("pays_destination", "Belgique"),
                    "duree": v.get("duree", 60),
                    "description": v.get("description", ""),
                }
                for v in voyages
            ]

        elif "chauffeurs.json" in filename_str:
            chauffeurs = api_client.get_chauffeurs(active_only=False)
            return [
                {
                    "id": c.get("id"),
                    "code": c.get("code", ""),
                    "nom": c.get("nom", ""),
                    "prenom": c.get("prenom", ""),
                    "telephone": c.get("telephone", ""),
                    "email": c.get("email", ""),
                    "type": c.get("type_contrat", "INTERNE"),
                    "actif": c.get("is_active", True),
                    "tracteur_attire": c.get("tracteur_attire", ""),
                    "adr": c.get("adr", False),
                    "fimo": c.get("fimo", True),
                }
                for c in chauffeurs
            ]

        elif "dispo_chauffeurs.json" in filename_str:
            return []

        elif "sst.json" in filename_str:
            sst_list = api_client.get_sst_list(active_only=False)
            return [s.get("code", "") for s in sst_list]

        elif "tarifs_sst.json" in filename_str:
            tarifs = api_client.get_sst_tarifs()
            result = {}
            for t in tarifs:
                sst_code = t.get("sst_code", "")
                if sst_code not in result:
                    result[sst_code] = {}
                result[sst_code][t.get("destination", "")] = t.get("prix", 0)
            return result

        elif "revenus_palettes.json" in filename_str:
            revenus = api_client.get_revenus_palettes()
            result = {}
            for r in revenus:
                result[r.get("destination", "")] = r.get("revenu_par_palette", 0)
            return result

        elif "users_rights.json" in filename_str:
            users = api_client.get_users()
            roles = api_client.get_roles()

            roles_def = {}
            for r in roles:
                roles_def[r.get("name", "")] = {"view_planning": True}

            users_def = {}
            for u in users:
                users_def[u.get("username", "")] = [u.get("role", "viewer")]

            return {"roles": roles_def, "users": users_def}

        elif "missions.json" in filename_str or "/planning/" in filename_str:
            return default if default is not None else []

        else:
            return default if default is not None else {}

    except Exception as e:
        print(f"[API] Erreur chargement {filename}: {e}")
        return default if default is not None else {}


def api_save_json(filename, data):
    """Remplace save_json pour utiliser l'API"""
    filename_str = str(filename).lower()

    try:
        if "voyages.json" in filename_str:
            api_client.invalidate_cache("/voyages")
        elif "chauffeurs.json" in filename_str:
            api_client.invalidate_cache("/chauffeurs")
        elif "missions.json" in filename_str:
            api_client.invalidate_cache("/missions")
    except Exception as e:
        print(f"[API] Erreur sauvegarde {filename}: {e}")


def api_list_existing_dates() -> List[str]:
    """Liste les dates avec des missions"""
    try:
        today = date.today()
        date_debut = today - timedelta(days=90)
        date_fin = today + timedelta(days=30)

        missions = api_client.get_missions(date_debut=date_debut, date_fin=date_fin)

        dates_set = set()
        for m in missions:
            d = m.get("date_mission")
            if d:
                if isinstance(d, str):
                    try:
                        d = datetime.fromisoformat(d.replace("Z", "")).date()
                    except Exception:
                        continue
                dates_set.add(d.strftime("%d/%m/%Y"))

        return sorted(dates_set, key=lambda x: datetime.strptime(x, "%d/%m/%Y"))

    except Exception as e:
        print(f"[API] Erreur list_existing_dates: {e}")
        return []


def api_get_planning_for_date(d: date) -> List[Dict]:
    """Recupere le planning d'une date"""
    try:
        return api_client.get_missions_by_date(d)
    except Exception as e:
        print(f"[API] Erreur get_planning_for_date: {e}")
        return []


# ============================================================================
# ACTIVITY LOGGER
# ============================================================================

class ActivityLogger:
    """Logger d'activite compatible avec PTT"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.current_user = None
        self.logs_dir = None

    def initialize(self, root_dir, username):
        self.current_user = username.upper()

    def log_action(self, action_type, details=None, before_state=None, after_state=None):
        pass  # Les actions sont logguees cote serveur

    def log_session_end(self):
        try:
            api_client.logout()
        except Exception:
            pass


# ============================================================================
# INSTANCES GLOBALES
# ============================================================================

api_client = APIClient()
connection_monitor = ConnectionMonitor()
live_sync = LiveSyncClient()
activity_logger = ActivityLogger()


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def is_connected() -> bool:
    """Verifie si connecte au serveur"""
    return api_client.token is not None


def is_online() -> bool:
    """Verifie si le serveur est accessible"""
    return connection_monitor.is_online


def get_current_user() -> str:
    """Retourne le nom d'utilisateur courant"""
    if api_client.user_info:
        return api_client.user_info.get("username", "INCONNU")
    return "INCONNU"


def get_user_permissions() -> Dict:
    """Retourne les permissions de l'utilisateur"""
    return api_client.get_permissions()


def start_live_sync():
    """Demarre la synchronisation temps reel"""
    live_sync.start()


def stop_live_sync():
    """Arrete la synchronisation temps reel"""
    live_sync.stop()
