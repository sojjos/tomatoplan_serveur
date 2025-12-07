#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TomatoPlan Client v0.2.0
========================

Client unifié pour TomatoPlan avec connexion WebSocket au serveur API.
Fichier unique autonome - Stockage temporaire dans AppData.

Usage:
    python TomatoPlan_Client_v0.2.0.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import json
import os
import sys
import socket
import ssl
import threading
import uuid
import getpass
import subprocess
import shutil
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

# ============================================================================
# CONFIGURATION
# ============================================================================

CLIENT_VERSION = "0.2.0"
APP_NAME = "TomatoPlan"

# Serveur par défaut - peut être modifié via fichier config
DEFAULT_SERVER_URL = "https://localhost:8000"
VERIFY_SSL = False
TIMEOUT = 30
CACHE_TTL = 30
WS_RECONNECT_DELAY = 5
STATUS_CHECK_INTERVAL = 5

# Dossier AppData pour stockage temporaire
if sys.platform == "win32":
    APPDATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TomatoPlan"
else:
    APPDATA_DIR = Path.home() / ".tomatoplan"

APPDATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APPDATA_DIR / "config.json"
CACHE_DIR = APPDATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Couleurs pays
EU_COUNTRIES = ["Belgique", "Allemagne", "France", "Luxembourg", "Pays-Bas"]
COUNTRY_COLORS = {
    "Belgique": "#FAFAFA",
    "France": "#E8F4FD",
    "Allemagne": "#FFF9E6",
    "Pays-Bas": "#FFF0E6",
    "Luxembourg": "#E8F8F0",
    "Espagne": "#FFEBEE",
    "Italie": "#F0FFF0",
}

# Imports optionnels
try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("ERREUR: pip install requests")

try:
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import win32com.client
    OUTLOOK_AVAILABLE = True
except ImportError:
    OUTLOOK_AVAILABLE = False

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def load_config() -> Dict:
    """Charge la configuration depuis AppData"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"server_url": DEFAULT_SERVER_URL}


def save_config(config: Dict):
    """Sauvegarde la configuration"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde config: {e}")


def format_date_display(d) -> str:
    """Formate une date pour l'affichage"""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            try:
                d = datetime.strptime(d, "%d/%m/%Y").date()
            except ValueError:
                return d
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)


def parse_date(s: str) -> Optional[date]:
    """Parse une date depuis une chaîne"""
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def format_currency(value) -> str:
    """Formate un montant en euros"""
    try:
        return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")
    except (ValueError, TypeError):
        return "0,00 €"


def get_desktop_path() -> Path:
    """Retourne le chemin du bureau"""
    home = Path.home()
    desktop = home / "Desktop"
    if not desktop.exists():
        desktop = home / "Bureau"
    if not desktop.exists():
        desktop = home
    return desktop


# ============================================================================
# CLIENT API REST
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

        config = load_config()
        self.server_url = config.get("server_url", DEFAULT_SERVER_URL).rstrip("/")
        self.verify_ssl = VERIFY_SSL
        self.timeout = TIMEOUT
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None
        self.must_change_password = False
        self._session = requests.Session() if REQUESTS_AVAILABLE else None
        self._lock = threading.Lock()

        # Cache local
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = CACHE_TTL

    def set_server_url(self, url: str):
        """Change l'URL du serveur"""
        self.server_url = url.rstrip("/")
        config = load_config()
        config["server_url"] = self.server_url
        save_config(config)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, endpoint: str, data=None, params=None, use_cache=False):
        """Execute une requete API"""
        if not REQUESTS_AVAILABLE:
            raise Exception("Module requests non disponible")

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
        """Invalide le cache"""
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

    def delete_voyage(self, voyage_id: int) -> bool:
        """Supprime un voyage"""
        self.invalidate_cache("/voyages")
        result = self._request("DELETE", f"/voyages/{voyage_id}")
        return result.get("success", False) if result else False

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

    def create_tarif_sst(self, sst_id: int, data: Dict) -> Dict:
        """Cree un tarif SST"""
        return self._request("POST", f"/sst/{sst_id}/tarifs", data)

    def delete_tarif_sst(self, sst_id: int, tarif_id: int) -> bool:
        """Supprime un tarif SST"""
        result = self._request("DELETE", f"/sst/{sst_id}/tarifs/{tarif_id}")
        return result.get("success", False) if result else False

    # ========== Finance ==========

    def get_revenus_palettes(self) -> List[Dict]:
        """Recupere les revenus palettes"""
        return self._request("GET", "/finance/revenus", use_cache=True) or []

    def create_revenu_palette(self, data: Dict) -> Dict:
        """Cree un revenu palette"""
        self.invalidate_cache("/finance")
        return self._request("POST", "/finance/revenus", data)

    def update_revenu_palette(self, revenu_id: int, data: Dict) -> Dict:
        """Met a jour un revenu palette"""
        self.invalidate_cache("/finance")
        return self._request("PUT", f"/finance/revenus/{revenu_id}", data)

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

    def get_user_stats(self, username: str) -> Dict:
        """Recupere les statistiques d'un utilisateur"""
        return self._request("GET", f"/stats/users/{username}") or {}

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
# CLIENT WEBSOCKET
# ============================================================================

class LiveSyncClient:
    """Client WebSocket pour synchronisation temps reel (singleton)"""

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
        if not WEBSOCKET_AVAILABLE:
            print("[WS] websocket-client non installe")
            return

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
        if not WEBSOCKET_AVAILABLE:
            return

        ws_url = api_client.server_url.replace("https://", "wss://").replace("http://", "ws://")
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

            elif msg_type == "connected_users":
                self._connected_users = data.get("users", [])

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

    def send_ping(self):
        """Envoie un ping au serveur"""
        if self._ws and self._connected:
            try:
                self._ws.send(json.dumps({"type": "ping"}))
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
# INSTANCES GLOBALES
# ============================================================================

api_client = APIClient()
connection_monitor = ConnectionMonitor()
live_sync = LiveSyncClient()


# ============================================================================
# FENETRE DE CONNEXION
# ============================================================================

class LoginWindow:
    """Fenetre de connexion au serveur TomatoPlan"""

    def __init__(self):
        self.authenticated = False
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - Connexion")
        self.root.geometry("450x420")
        self.root.resizable(False, False)

        # Centrer la fenetre
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 225
        y = (self.root.winfo_screenheight() // 2) - 210
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self._check_server()

    def _build_ui(self):
        # Titre
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=20)

        ttk.Label(title_frame, text=APP_NAME, font=("Arial", 28, "bold")).pack()
        ttk.Label(title_frame, text="Planning Transport Tubize", font=("Arial", 11)).pack()
        ttk.Label(title_frame, text=f"Client v{CLIENT_VERSION}", font=("Arial", 9), foreground="gray").pack()

        # Serveur
        server_frame = ttk.LabelFrame(self.root, text="Serveur", padding=10)
        server_frame.pack(padx=20, pady=5, fill="x")

        self.server_var = tk.StringVar(value=api_client.server_url)
        server_entry = ttk.Entry(server_frame, textvariable=self.server_var, width=45)
        server_entry.pack(side="left", padx=(0, 5))
        ttk.Button(server_frame, text="Tester", command=self._check_server, width=8).pack(side="left")

        # Statut serveur
        self.status_label = ttk.Label(self.root, text="Verification du serveur...", foreground="orange")
        self.status_label.pack(pady=5)

        # Formulaire
        form_frame = ttk.LabelFrame(self.root, text="Connexion", padding=15)
        form_frame.pack(padx=20, pady=10, fill="x")

        # Username
        ttk.Label(form_frame, text="Utilisateur:").grid(row=0, column=0, sticky="w", pady=5)
        default_user = os.environ.get("USERNAME", os.environ.get("USER", "")).upper()
        self.username_var = tk.StringVar(value=default_user)
        self.username_entry = ttk.Entry(form_frame, textvariable=self.username_var, width=30)
        self.username_entry.grid(row=0, column=1, pady=5, padx=5)

        # Password
        ttk.Label(form_frame, text="Mot de passe:").grid(row=1, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(form_frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=1, column=1, pady=5, padx=5)
        self.password_entry.bind("<Return>", lambda e: self._on_login())

        # Boutons
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=15)

        self.login_btn = ttk.Button(btn_frame, text="Connexion", command=self._on_login, width=15)
        self.login_btn.pack(side="left", padx=5)
        self.login_btn.config(state="disabled")

        ttk.Button(btn_frame, text="Quitter", command=self.root.destroy, width=15).pack(side="left", padx=5)

        # Erreur
        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(self.root, textvariable=self.error_var, foreground="red", wraplength=400)
        self.error_label.pack(pady=5)

        self.password_entry.focus()

    def _check_server(self):
        """Verification du serveur"""
        server_url = self.server_var.get().strip()
        if server_url:
            api_client.set_server_url(server_url)

        self.status_label.config(text="Verification...", foreground="orange")
        self.login_btn.config(state="disabled")

        def check():
            try:
                status = api_client.check_server()
                if status.get("status") == "ok":
                    version = status.get("version", "?")
                    self.root.after(0, lambda: self._update_status(True, f"Serveur OK (v{version})"))
                else:
                    self.root.after(0, lambda: self._update_status(False, "Serveur indisponible"))
            except Exception as e:
                self.root.after(0, lambda: self._update_status(False, f"Erreur: {str(e)[:40]}"))

        threading.Thread(target=check, daemon=True).start()

    def _update_status(self, connected: bool, message: str):
        if connected:
            self.status_label.config(text=message, foreground="green")
            self.login_btn.config(state="normal")
        else:
            self.status_label.config(text=message, foreground="red")
            self.login_btn.config(state="disabled")

    def _on_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username:
            self.error_var.set("Veuillez entrer un nom d'utilisateur")
            return
        if not password:
            self.error_var.set("Veuillez entrer un mot de passe")
            return

        self.error_var.set("")
        self.login_btn.config(state="disabled")
        self.status_label.config(text="Connexion en cours...", foreground="orange")

        def do_login():
            try:
                if api_client.login(username, password):
                    self.authenticated = True
                    self.root.after(0, self._on_success)
                else:
                    self.root.after(0, lambda: self._on_error("Echec de l'authentification"))
            except PermissionError as e:
                self.root.after(0, lambda: self._on_error(str(e)))
            except ConnectionError:
                self.root.after(0, lambda: self._on_error("Connexion impossible"))
            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)[:100]))

        threading.Thread(target=do_login, daemon=True).start()

    def _on_success(self):
        if api_client.must_change_password:
            self._show_change_password()
        else:
            self.root.destroy()

    def _on_error(self, message: str):
        self.error_var.set(message)
        self.login_btn.config(state="normal")
        self.status_label.config(text="Serveur connecte", foreground="green")

    def _show_change_password(self):
        """Dialogue changement mot de passe"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Changement de mot de passe requis")
        dialog.geometry("420x280")
        dialog.transient(self.root)
        dialog.grab_set()

        # Centrer
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 210
        y = (dialog.winfo_screenheight() // 2) - 140
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="Vous devez changer votre mot de passe temporaire",
                  font=("Arial", 10, "bold")).pack(pady=15)

        form = ttk.Frame(dialog, padding=15)
        form.pack(fill="x")

        ttk.Label(form, text="Nouveau mot de passe:").grid(row=0, column=0, sticky="w", pady=5)
        new_pwd_var = tk.StringVar()
        new_pwd_entry = ttk.Entry(form, textvariable=new_pwd_var, show="*", width=30)
        new_pwd_entry.grid(row=0, column=1, pady=5)

        ttk.Label(form, text="Confirmer:").grid(row=1, column=0, sticky="w", pady=5)
        confirm_var = tk.StringVar()
        ttk.Entry(form, textvariable=confirm_var, show="*", width=30).grid(row=1, column=1, pady=5)

        error_var = tk.StringVar()
        ttk.Label(dialog, textvariable=error_var, foreground="red").pack()

        ttk.Label(dialog, text="(Min 8 caracteres, majuscule, minuscule, chiffre)",
                  font=("Arial", 8), foreground="gray").pack()

        def do_change():
            new_pwd = new_pwd_var.get()
            confirm = confirm_var.get()

            if new_pwd != confirm:
                error_var.set("Les mots de passe ne correspondent pas")
                return
            if len(new_pwd) < 8:
                error_var.set("Minimum 8 caracteres requis")
                return

            try:
                current = self.password_var.get()
                if api_client.change_password(current, new_pwd):
                    dialog.destroy()
                    self.root.destroy()
                else:
                    error_var.set("Echec du changement")
            except Exception as e:
                error_var.set(str(e)[:50])

        ttk.Button(dialog, text="Changer le mot de passe", command=do_change).pack(pady=15)
        new_pwd_entry.focus()
        dialog.wait_window()

    def run(self) -> bool:
        """Lance la fenetre de login"""
        self.root.mainloop()
        return self.authenticated


# ============================================================================
# APPLICATION PRINCIPALE
# ============================================================================

class TomatoPlanApp:
    """Application principale TomatoPlan"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} - Planning Transport v{CLIENT_VERSION}")
        self.root.minsize(1200, 700)
        self.root.geometry("1400x900")
        self.root.resizable(True, True)

        # Utilisateur courant
        self.current_user = api_client.user_info.get("username", "INCONNU").upper()
        self.permissions = api_client.get_permissions()

        # Variables d'état
        self.current_date = date.today()
        self.missions = []
        self.voyages = []
        self.chauffeurs = []
        self.sst_list = []
        self.dispos = []
        self.tarifs_sst = {}
        self.revenus_palettes = {}

        # Interface
        self.country_trees = {}
        self.country_frames = {}
        self.country_headers = {}
        self.sort_criteria = "heure"
        self.sort_reverse = False

        # Barre de statut
        self.status_var = tk.StringVar(value=f"Session : {self.current_user}")
        self.last_refresh_dt = datetime.now()

        # Construire l'interface
        self._build_gui()

        # Charger les données initiales
        self._load_initial_data()

        # Démarrer les services
        self._start_services()

        # Charger le planning du jour
        self.load_planning_for_date(self.current_date)

        # Fermeture de l'application
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_gui(self):
        """Construit l'interface graphique"""
        # Menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Rafraichir", command=self.refresh_all, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self._on_close)
        menubar.add_cascade(label="Fichier", menu=file_menu)

        # Raccourcis
        self.root.bind("<F5>", lambda e: self.refresh_all())

        # Barre de statut
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side="bottom", fill="x")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="e")
        self.status_label.pack(side="right", padx=5, pady=2)

        # Notebook (onglets)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Créer les onglets selon les permissions
        perms = self.permissions

        if perms.get("view_planning", True):
            self._build_planning_tab()

        if perms.get("view_drivers", True):
            self._build_chauffeurs_tab()

        if perms.get("manage_voyages", False):
            self._build_voyages_tab()

        if perms.get("view_finance", False):
            self._build_finance_tab()

        if perms.get("view_analyse", False):
            self._build_analyse_tab()

        if perms.get("manage_rights", False):
            self._build_admin_tab()

        if perms.get("view_sauron", False):
            self._build_sauron_tab()

    def _build_planning_tab(self):
        """Construit l'onglet Planning"""
        self.tab_planning = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_planning, text="Planning")

        # Barre de navigation date
        top_frame = ttk.Frame(self.tab_planning)
        top_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(top_frame, text="Date :").pack(side="left")
        self.date_var = tk.StringVar(value=format_date_display(self.current_date))
        self.date_entry = ttk.Entry(top_frame, textvariable=self.date_var, width=12)
        self.date_entry.bind('<Return>', lambda e: self._on_load_date())
        self.date_entry.pack(side="left", padx=(5, 15))

        ttk.Button(top_frame, text="◀◀ -7j", command=lambda: self._navigate_days(-7), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="◀ -1j", command=lambda: self._navigate_days(-1), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Aujourd'hui", command=self._set_today, width=12).pack(side="left", padx=5)
        ttk.Button(top_frame, text="+1j ▶", command=lambda: self._navigate_days(1), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="+7j ▶▶", command=lambda: self._navigate_days(7), width=8).pack(side="left", padx=2)

        ttk.Separator(top_frame, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(top_frame, text="Rafraichir", command=self.refresh_all).pack(side="left", padx=5)

        # Résumé
        self.summary_frame = ttk.Frame(self.tab_planning, relief='solid', borderwidth=1)
        self.summary_frame.pack(fill='x', padx=5, pady=3)

        stats_container = ttk.Frame(self.summary_frame)
        stats_container.pack(fill='x', padx=5, pady=3)

        ttk.Label(stats_container, text="Résumé:", font=('Arial', 9, 'bold')).pack(side='left', padx=(5, 10))

        ttk.Label(stats_container, text="Liv:", font=('Arial', 8)).pack(side='left', padx=2)
        self.summary_liv_label = ttk.Label(stats_container, text="0", font=('Arial', 10, 'bold'), foreground='#2196F3')
        self.summary_liv_label.pack(side='left', padx=(0, 8))

        ttk.Label(stats_container, text="Ram:", font=('Arial', 8)).pack(side='left', padx=2)
        self.summary_ram_label = ttk.Label(stats_container, text="0", font=('Arial', 10, 'bold'), foreground='#4CAF50')
        self.summary_ram_label.pack(side='left', padx=(0, 8))

        ttk.Separator(stats_container, orient='vertical').pack(side='left', fill='y', padx=5)

        ttk.Label(stats_container, text="Chauffeurs utilisés:", font=('Arial', 8)).pack(side='left', padx=2)
        self.summary_used_label = ttk.Label(stats_container, text="0", font=('Arial', 10, 'bold'), foreground='#FF9800')
        self.summary_used_label.pack(side='left', padx=(0, 8))

        ttk.Label(stats_container, text="Palettes:", font=('Arial', 8)).pack(side='left', padx=2)
        self.summary_pal_label = ttk.Label(stats_container, text="0", font=('Arial', 10, 'bold'), foreground='#9C27B0')
        self.summary_pal_label.pack(side='left', padx=(0, 8))

        # Boutons d'action
        btn_frame = ttk.Frame(self.tab_planning)
        btn_frame.pack(fill="x", padx=5, pady=5)

        if self.permissions.get("edit_planning", False):
            ttk.Button(btn_frame, text="+ Ajouter", command=self._on_add_mission).pack(side="left", padx=2)
            ttk.Button(btn_frame, text="Modifier", command=self._on_edit_mission).pack(side="left", padx=2)
            ttk.Button(btn_frame, text="Supprimer", command=self._on_delete_mission).pack(side="left", padx=2)

        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(btn_frame, text="Trier par:").pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Heure", command=lambda: self._sort_missions("heure")).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Voyage", command=lambda: self._sort_missions("voyage")).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Chauffeur", command=lambda: self._sort_missions("chauffeur")).pack(side="left", padx=2)

        self.sort_label = ttk.Label(btn_frame, text="(Tri: Heure)", foreground="blue")
        self.sort_label.pack(side="left", padx=10)

        # Zone scrollable pour les plannings par pays
        canvas_frame = ttk.Frame(self.tab_planning)
        canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Scroll avec molette
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self.planning_container = self.scrollable_frame

    def _build_chauffeurs_tab(self):
        """Construit l'onglet Chauffeurs"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Chauffeurs")

        # Barre d'outils
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", padx=5, pady=5)

        if self.permissions.get("manage_drivers", False):
            ttk.Button(toolbar, text="+ Ajouter", command=self._on_add_chauffeur).pack(side="left", padx=2)
            ttk.Button(toolbar, text="Modifier", command=self._on_edit_chauffeur).pack(side="left", padx=2)

        ttk.Button(toolbar, text="Rafraichir", command=self._refresh_chauffeurs).pack(side="left", padx=5)

        # Liste des chauffeurs
        columns = ("code", "nom", "prenom", "telephone", "type", "tracteur", "actif")
        self.chauffeurs_tree = ttk.Treeview(tab, columns=columns, show="headings", height=20)

        for col, txt, width in [
            ("code", "Code", 80),
            ("nom", "Nom", 120),
            ("prenom", "Prénom", 120),
            ("telephone", "Téléphone", 120),
            ("type", "Type", 80),
            ("tracteur", "Tracteur", 100),
            ("actif", "Actif", 60),
        ]:
            self.chauffeurs_tree.heading(col, text=txt)
            self.chauffeurs_tree.column(col, width=width)

        vsb = ttk.Scrollbar(tab, orient="vertical", command=self.chauffeurs_tree.yview)
        self.chauffeurs_tree.configure(yscrollcommand=vsb.set)

        self.chauffeurs_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        vsb.pack(side="right", fill="y", pady=5)

    def _build_voyages_tab(self):
        """Construit l'onglet Voyages"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Voyages")

        # Barre d'outils
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", padx=5, pady=5)

        ttk.Button(toolbar, text="+ Ajouter", command=self._on_add_voyage).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Modifier", command=self._on_edit_voyage).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Rafraichir", command=self._refresh_voyages).pack(side="left", padx=5)

        # Liste des voyages
        columns = ("code", "type", "pays", "actif", "duree")
        self.voyages_tree = ttk.Treeview(tab, columns=columns, show="headings", height=20)

        for col, txt, width in [
            ("code", "Code", 120),
            ("type", "Type", 100),
            ("pays", "Pays", 120),
            ("actif", "Actif", 60),
            ("duree", "Durée (min)", 80),
        ]:
            self.voyages_tree.heading(col, text=txt)
            self.voyages_tree.column(col, width=width)

        vsb = ttk.Scrollbar(tab, orient="vertical", command=self.voyages_tree.yview)
        self.voyages_tree.configure(yscrollcommand=vsb.set)

        self.voyages_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        vsb.pack(side="right", fill="y", pady=5)

    def _build_finance_tab(self):
        """Construit l'onglet Finance"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Finance")

        # Sous-notebook
        finance_nb = ttk.Notebook(tab)
        finance_nb.pack(fill="both", expand=True, padx=5, pady=5)

        # SST
        sst_frame = ttk.Frame(finance_nb)
        finance_nb.add(sst_frame, text="SST & Tarifs")

        ttk.Label(sst_frame, text="Gestion des sous-traitants et tarifs", font=("Arial", 12, "bold")).pack(pady=10)

        columns = ("code", "nom", "actif")
        self.sst_tree = ttk.Treeview(sst_frame, columns=columns, show="headings", height=15)
        for col, txt, width in [("code", "Code", 100), ("nom", "Nom", 200), ("actif", "Actif", 60)]:
            self.sst_tree.heading(col, text=txt)
            self.sst_tree.column(col, width=width)
        self.sst_tree.pack(fill="both", expand=True, padx=5, pady=5)

        # Revenus
        rev_frame = ttk.Frame(finance_nb)
        finance_nb.add(rev_frame, text="Revenus Palettes")

        ttk.Label(rev_frame, text="Revenus par palette par destination", font=("Arial", 12, "bold")).pack(pady=10)

        columns = ("destination", "pays", "revenu")
        self.revenus_tree = ttk.Treeview(rev_frame, columns=columns, show="headings", height=15)
        for col, txt, width in [("destination", "Destination", 200), ("pays", "Pays", 100), ("revenu", "Revenu/Pal", 100)]:
            self.revenus_tree.heading(col, text=txt)
            self.revenus_tree.column(col, width=width)
        self.revenus_tree.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_analyse_tab(self):
        """Construit l'onglet Analyse"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Analyse")

        ttk.Label(tab, text="Module d'Analyse Avancée", font=("Arial", 14, "bold")).pack(pady=20)

        # Période
        period_frame = ttk.LabelFrame(tab, text="Période d'analyse", padding=10)
        period_frame.pack(fill="x", padx=20, pady=10)

        ttk.Label(period_frame, text="Du:").pack(side="left", padx=5)
        self.analyse_start_var = tk.StringVar(value=format_date_display(date.today() - timedelta(days=30)))
        ttk.Entry(period_frame, textvariable=self.analyse_start_var, width=12).pack(side="left", padx=5)

        ttk.Label(period_frame, text="Au:").pack(side="left", padx=5)
        self.analyse_end_var = tk.StringVar(value=format_date_display(date.today()))
        ttk.Entry(period_frame, textvariable=self.analyse_end_var, width=12).pack(side="left", padx=5)

        ttk.Button(period_frame, text="Analyser", command=self._run_analyse).pack(side="left", padx=20)

        # Résultats
        self.analyse_results_frame = ttk.Frame(tab)
        self.analyse_results_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ttk.Label(self.analyse_results_frame, text="Sélectionnez une période et cliquez sur Analyser",
                  foreground="gray").pack(pady=50)

    def _build_admin_tab(self):
        """Construit l'onglet Administration"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Administration")

        ttk.Label(tab, text="Gestion des Utilisateurs", font=("Arial", 14, "bold")).pack(pady=20)

        # Barre d'outils
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", padx=20, pady=5)

        ttk.Button(toolbar, text="+ Nouvel utilisateur", command=self._on_add_user).pack(side="left", padx=5)
        ttk.Button(toolbar, text="Rafraichir", command=self._refresh_users).pack(side="left", padx=5)

        # Liste des utilisateurs
        columns = ("username", "display_name", "role", "actif", "last_login")
        self.users_tree = ttk.Treeview(tab, columns=columns, show="headings", height=15)

        for col, txt, width in [
            ("username", "Utilisateur", 120),
            ("display_name", "Nom affiché", 150),
            ("role", "Rôle", 120),
            ("actif", "Actif", 60),
            ("last_login", "Dernière connexion", 150),
        ]:
            self.users_tree.heading(col, text=txt)
            self.users_tree.column(col, width=width)

        self.users_tree.pack(fill="both", expand=True, padx=20, pady=10)

    def _build_sauron_tab(self):
        """Construit l'onglet SAURON (logs)"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="SAURON")

        ttk.Label(tab, text="Surveillance des Activités (SAURON)", font=("Arial", 14, "bold")).pack(pady=20)

        # Filtres
        filter_frame = ttk.Frame(tab)
        filter_frame.pack(fill="x", padx=20, pady=5)

        ttk.Label(filter_frame, text="Utilisateur:").pack(side="left", padx=5)
        self.sauron_user_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.sauron_user_var, width=20).pack(side="left", padx=5)

        ttk.Button(filter_frame, text="Rechercher", command=self._search_activity).pack(side="left", padx=10)
        ttk.Button(filter_frame, text="Tout afficher", command=self._show_all_activity).pack(side="left", padx=5)

        # Liste des activités
        columns = ("timestamp", "user", "action", "details")
        self.activity_tree = ttk.Treeview(tab, columns=columns, show="headings", height=20)

        for col, txt, width in [
            ("timestamp", "Date/Heure", 150),
            ("user", "Utilisateur", 100),
            ("action", "Action", 150),
            ("details", "Détails", 400),
        ]:
            self.activity_tree.heading(col, text=txt)
            self.activity_tree.column(col, width=width)

        vsb = ttk.Scrollbar(tab, orient="vertical", command=self.activity_tree.yview)
        self.activity_tree.configure(yscrollcommand=vsb.set)

        self.activity_tree.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        vsb.pack(side="right", fill="y", pady=10)

    # ========== CHARGEMENT DES DONNÉES ==========

    def _load_initial_data(self):
        """Charge les données initiales depuis le serveur"""
        try:
            self.voyages = api_client.get_voyages(active_only=False) or []
            self.chauffeurs = api_client.get_chauffeurs(active_only=False) or []
            self.sst_list = api_client.get_sst_list(active_only=False) or []

            # Préparer les listes pour les combobox
            self._voyage_codes = [v.get("code", "") for v in self.voyages if v.get("is_active", True)]
            self._chauffeur_noms = [f"{c.get('nom', '')} {c.get('prenom', '')}".strip() for c in self.chauffeurs if c.get("is_active", True)]
            self._sst_codes = [s.get("code", "") for s in self.sst_list if s.get("is_active", True)]

        except Exception as e:
            print(f"Erreur chargement données: {e}")
            messagebox.showerror("Erreur", f"Impossible de charger les données: {e}")

    def _start_services(self):
        """Démarre les services de fond"""
        # Démarrer le monitoring de connexion
        connection_monitor.start()
        connection_monitor.add_callback(self._on_connection_changed)

        # Démarrer la synchronisation WebSocket
        live_sync.on_data_changed(self._on_data_changed)
        live_sync.on_connection_changed(self._on_ws_connection_changed)
        live_sync.start()

        # Démarrer le timer de mise à jour du statut
        self._update_status_bar()

    def _update_status_bar(self):
        """Met à jour la barre de statut"""
        try:
            ws_connected = live_sync.is_connected
            users_count = live_sync.connected_users_count

            if ws_connected:
                status = f"En ligne ({users_count} utilisateur{'s' if users_count > 1 else ''})"
                indicator = "●"
                self.status_label.config(foreground="green")
            elif connection_monitor.is_online:
                status = "En ligne"
                indicator = "●"
                self.status_label.config(foreground="green")
            else:
                status = "Hors ligne"
                indicator = "○"
                self.status_label.config(foreground="red")

            self.status_var.set(f"Session: {self.current_user} | {indicator} {status} | MAJ: {self.last_refresh_dt.strftime('%H:%M:%S')}")
        except Exception:
            pass

        # Répéter toutes les 5 secondes
        self.root.after(5000, self._update_status_bar)

    def _on_connection_changed(self, is_online: bool):
        """Callback quand la connexion change"""
        if is_online:
            self.root.after(100, self.refresh_all)

    def _on_ws_connection_changed(self, connected: bool):
        """Callback quand la connexion WebSocket change"""
        pass

    def _on_data_changed(self, entity: str, action: str, data: dict):
        """Callback quand des données changent sur le serveur"""
        changed_by = data.get("changed_by", "")
        if changed_by.upper() == self.current_user:
            return

        print(f"[SYNC] Changement: {entity}/{action} par {changed_by}")

        # Rafraîchir l'interface
        self.root.after(100, self.refresh_all)

    # ========== NAVIGATION DATE ==========

    def _navigate_days(self, days: int):
        """Navigue de X jours"""
        self.current_date += timedelta(days=days)
        self.date_var.set(format_date_display(self.current_date))
        self.load_planning_for_date(self.current_date)

    def _set_today(self):
        """Retourne à aujourd'hui"""
        self.current_date = date.today()
        self.date_var.set(format_date_display(self.current_date))
        self.load_planning_for_date(self.current_date)

    def _on_load_date(self):
        """Charge la date entrée"""
        d = parse_date(self.date_var.get())
        if d:
            self.current_date = d
            self.date_var.set(format_date_display(d))
            self.load_planning_for_date(d)
        else:
            messagebox.showwarning("Date invalide", "Format attendu: JJ/MM/AAAA")

    # ========== CHARGEMENT PLANNING ==========

    def load_planning_for_date(self, d: date):
        """Charge le planning pour une date"""
        try:
            # Récupérer les missions du serveur
            raw_missions = api_client.get_missions_by_date(d)

            # Convertir en format interne
            self.missions = []
            for m in raw_missions:
                mission = {
                    "id": m.get("id"),
                    "date": d,
                    "heure": m.get("heure_debut", "")[:5] if m.get("heure_debut") else "",
                    "type": m.get("type_mission", "LIVRAISON"),
                    "voyage": m.get("voyage", {}).get("code", "") if isinstance(m.get("voyage"), dict) else m.get("voyage_code", ""),
                    "nb_pal": m.get("nb_palettes", 0),
                    "numero": m.get("numero", ""),
                    "sst": m.get("sst", {}).get("code", "") if isinstance(m.get("sst"), dict) else m.get("sst_code", ""),
                    "chauffeur_id": m.get("chauffeur_id"),
                    "chauffeur_nom": m.get("chauffeur", {}).get("nom_complet", "") if isinstance(m.get("chauffeur"), dict) else m.get("chauffeur_nom", ""),
                    "ramasse": m.get("ramasse", ""),
                    "infos": m.get("infos", "") or m.get("commentaire", ""),
                    "pays": m.get("voyage", {}).get("pays_destination", "Belgique") if isinstance(m.get("voyage"), dict) else "Belgique",
                    "sans_sst": m.get("sans_sst", False),
                    "sans_chauffeur": m.get("sans_chauffeur", False),
                }
                self.missions.append(mission)

            self.last_refresh_dt = datetime.now()
            self._refresh_planning_view()
            self._update_summary_stats()

        except Exception as e:
            print(f"Erreur chargement planning: {e}")
            messagebox.showerror("Erreur", f"Impossible de charger le planning: {e}")

    def _refresh_planning_view(self):
        """Rafraîchit l'affichage du planning"""
        # Grouper les missions par pays
        missions_by_country = {}
        v_by_code = {v.get("code"): v for v in self.voyages}

        for m in self.missions:
            voyage_code = m.get("voyage", "")
            voyage = v_by_code.get(voyage_code, {})
            country = voyage.get("pays_destination", m.get("pays", "Belgique"))
            m["pays"] = country

            if country not in missions_by_country:
                missions_by_country[country] = []
            missions_by_country[country].append(m)

        # Trier les pays
        country_order = ["Belgique", "France", "Allemagne", "Pays-Bas", "Luxembourg"]
        sorted_countries = sorted(missions_by_country.keys(),
                                  key=lambda x: country_order.index(x) if x in country_order else 100)

        # Créer/mettre à jour les sections par pays
        for country in sorted_countries:
            if country not in self.country_frames:
                self._create_country_section(country)

            self._fill_country_trees(country, missions_by_country[country])

        # Masquer les pays sans missions
        for country in list(self.country_frames.keys()):
            if country not in missions_by_country:
                self.country_frames[country].pack_forget()
            else:
                self.country_frames[country].pack(fill="x", expand=False, pady=5)

    def _create_country_section(self, country: str):
        """Crée une section de planning pour un pays"""
        bg_color = COUNTRY_COLORS.get(country, "#F5F5F5")

        # Frame principal du pays
        country_frame = ttk.LabelFrame(self.planning_container, text=f"  {self._get_flag(country)}  {country.upper()}  ", padding=10)
        country_frame.pack(fill="x", expand=False, pady=5)

        # Frame intérieur avec les deux arbres
        inner_frame = ttk.Frame(country_frame)
        inner_frame.pack(fill="both", expand=True)

        # Livraisons (gauche)
        left_frame = ttk.LabelFrame(inner_frame, text="LIVRAISONS", padding=5)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        columns_liv = ("heure", "voyage", "nb_pal", "numero", "sst", "chauffeur", "infos")
        tree_liv = ttk.Treeview(left_frame, columns=columns_liv, show="headings", height=8)

        for col, txt, width in [
            ("heure", "Heure", 50), ("voyage", "Voyage", 80), ("nb_pal", "Pal", 40),
            ("numero", "N°", 30), ("sst", "SST", 60), ("chauffeur", "Chauffeur", 100), ("infos", "Infos", 120)
        ]:
            tree_liv.heading(col, text=txt)
            tree_liv.column(col, width=width, minwidth=30)

        tree_liv.pack(fill="both", expand=True)
        tree_liv.bind("<Double-1>", lambda e: self._on_edit_mission())

        # Ramasses (droite)
        right_frame = ttk.LabelFrame(inner_frame, text="RAMASSES", padding=5)
        right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))

        columns_ram = ("heure", "voyage", "nb_pal", "numero", "sst", "chauffeur", "ramasse", "infos")
        tree_ram = ttk.Treeview(right_frame, columns=columns_ram, show="headings", height=8)

        for col, txt, width in [
            ("heure", "Heure", 50), ("voyage", "Voyage", 80), ("nb_pal", "Pal", 40),
            ("numero", "N°", 30), ("sst", "SST", 60), ("chauffeur", "Chauffeur", 80),
            ("ramasse", "Ramasse", 80), ("infos", "Infos", 100)
        ]:
            tree_ram.heading(col, text=txt)
            tree_ram.column(col, width=width, minwidth=30)

        tree_ram.pack(fill="both", expand=True)
        tree_ram.bind("<Double-1>", lambda e: self._on_edit_mission())

        # Stocker les références
        self.country_frames[country] = country_frame
        self.country_trees[country] = {"livraison": tree_liv, "ramasse": tree_ram}

    def _fill_country_trees(self, country: str, missions: List[Dict]):
        """Remplit les arbres d'un pays avec les missions"""
        if country not in self.country_trees:
            return

        tree_liv = self.country_trees[country]["livraison"]
        tree_ram = self.country_trees[country]["ramasse"]

        # Vider les arbres
        for item in tree_liv.get_children():
            tree_liv.delete(item)
        for item in tree_ram.get_children():
            tree_ram.delete(item)

        # Trier les missions
        missions_sorted = self._sort_missions_list(missions)

        # Remplir
        for m in missions_sorted:
            if m.get("type") == "LIVRAISON":
                tree_liv.insert("", "end", iid=str(m.get("id")), values=(
                    m.get("heure", ""),
                    m.get("voyage", ""),
                    m.get("nb_pal", ""),
                    m.get("numero", ""),
                    m.get("sst", ""),
                    m.get("chauffeur_nom", ""),
                    m.get("infos", ""),
                ))
            else:
                tree_ram.insert("", "end", iid=str(m.get("id")), values=(
                    m.get("heure", ""),
                    m.get("voyage", ""),
                    m.get("nb_pal", ""),
                    m.get("numero", ""),
                    m.get("sst", ""),
                    m.get("chauffeur_nom", ""),
                    m.get("ramasse", ""),
                    m.get("infos", ""),
                ))

    def _sort_missions_list(self, missions: List[Dict]) -> List[Dict]:
        """Trie une liste de missions selon le critère actuel"""
        def sort_key(m):
            if self.sort_criteria == "heure":
                return m.get("heure", "") or "99:99"
            elif self.sort_criteria == "voyage":
                return m.get("voyage", "")
            elif self.sort_criteria == "chauffeur":
                return m.get("chauffeur_nom", "")
            else:
                return m.get("heure", "")

        return sorted(missions, key=sort_key, reverse=self.sort_reverse)

    def _sort_missions(self, criteria: str):
        """Change le critère de tri"""
        if self.sort_criteria == criteria:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_criteria = criteria
            self.sort_reverse = False

        arrow = "↓" if self.sort_reverse else "↑"
        self.sort_label.config(text=f"(Tri: {criteria.capitalize()} {arrow})")
        self._refresh_planning_view()

    def _update_summary_stats(self):
        """Met à jour les statistiques résumées"""
        nb_liv = sum(1 for m in self.missions if m.get("type") == "LIVRAISON")
        nb_ram = sum(1 for m in self.missions if m.get("type") == "RAMASSE")
        total_pal = sum(int(m.get("nb_pal", 0) or 0) for m in self.missions)
        chauffeurs_used = len(set(m.get("chauffeur_nom") for m in self.missions if m.get("chauffeur_nom")))

        self.summary_liv_label.config(text=str(nb_liv))
        self.summary_ram_label.config(text=str(nb_ram))
        self.summary_pal_label.config(text=str(total_pal))
        self.summary_used_label.config(text=str(chauffeurs_used))

    def _get_flag(self, country: str) -> str:
        """Retourne l'emoji drapeau d'un pays"""
        flags = {
            "Belgique": "🇧🇪", "France": "🇫🇷", "Allemagne": "🇩🇪",
            "Pays-Bas": "🇳🇱", "Luxembourg": "🇱🇺", "Espagne": "🇪🇸",
            "Italie": "🇮🇹", "Portugal": "🇵🇹",
        }
        return flags.get(country, "🌍")

    # ========== ACTIONS MISSIONS ==========

    def _get_selected_mission(self) -> Optional[Dict]:
        """Retourne la mission sélectionnée"""
        for country, trees in self.country_trees.items():
            for tree_type, tree in trees.items():
                selection = tree.selection()
                if selection:
                    mission_id = int(selection[0])
                    for m in self.missions:
                        if m.get("id") == mission_id:
                            return m
        return None

    def _on_add_mission(self):
        """Ajoute une nouvelle mission"""
        self._show_mission_dialog(None)

    def _on_edit_mission(self):
        """Modifie la mission sélectionnée"""
        mission = self._get_selected_mission()
        if mission:
            self._show_mission_dialog(mission)
        else:
            messagebox.showwarning("Attention", "Veuillez sélectionner une mission")

    def _on_delete_mission(self):
        """Supprime la mission sélectionnée"""
        mission = self._get_selected_mission()
        if not mission:
            messagebox.showwarning("Attention", "Veuillez sélectionner une mission")
            return

        if messagebox.askyesno("Confirmation", "Supprimer cette mission ?"):
            try:
                api_client.delete_mission(mission["id"])
                self.load_planning_for_date(self.current_date)
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de supprimer: {e}")

    def _show_mission_dialog(self, mission: Optional[Dict]):
        """Affiche le dialogue d'édition de mission"""
        is_edit = mission is not None

        dialog = tk.Toplevel(self.root)
        dialog.title("Modifier la mission" if is_edit else "Nouvelle mission")
        dialog.geometry("500x450")
        dialog.transient(self.root)
        dialog.grab_set()

        # Centrer
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 450) // 2
        dialog.geometry(f"+{x}+{y}")

        # Variables
        type_var = tk.StringVar(value=mission.get("type", "LIVRAISON") if mission else "LIVRAISON")
        heure_var = tk.StringVar(value=mission.get("heure", "") if mission else "")
        voyage_var = tk.StringVar(value=mission.get("voyage", "") if mission else "")
        nb_pal_var = tk.StringVar(value=str(mission.get("nb_pal", "")) if mission else "")
        numero_var = tk.StringVar(value=str(mission.get("numero", "")) if mission else "")
        sst_var = tk.StringVar(value=mission.get("sst", "") if mission else "")
        chauffeur_var = tk.StringVar(value=mission.get("chauffeur_nom", "") if mission else "")
        ramasse_var = tk.StringVar(value=mission.get("ramasse", "") if mission else "")
        infos_var = tk.StringVar(value=mission.get("infos", "") if mission else "")

        # Formulaire
        form = ttk.Frame(dialog, padding=20)
        form.pack(fill="both", expand=True)

        row = 0

        ttk.Label(form, text="Type:").grid(row=row, column=0, sticky="w", pady=5)
        type_combo = ttk.Combobox(form, textvariable=type_var, values=["LIVRAISON", "RAMASSE"], state="readonly", width=25)
        type_combo.grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Heure (HH:MM):").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=heure_var, width=28).grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Voyage:").grid(row=row, column=0, sticky="w", pady=5)
        voyage_combo = ttk.Combobox(form, textvariable=voyage_var, values=self._voyage_codes, width=25)
        voyage_combo.grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Nb Palettes:").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=nb_pal_var, width=28).grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="N° tournée:").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=numero_var, width=28).grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="SST:").grid(row=row, column=0, sticky="w", pady=5)
        sst_combo = ttk.Combobox(form, textvariable=sst_var, values=[""] + self._sst_codes, width=25)
        sst_combo.grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Chauffeur:").grid(row=row, column=0, sticky="w", pady=5)
        chauffeur_combo = ttk.Combobox(form, textvariable=chauffeur_var, values=[""] + self._chauffeur_noms, width=25)
        chauffeur_combo.grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Ramasse:").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=ramasse_var, width=28).grid(row=row, column=1, pady=5, padx=5)
        row += 1

        ttk.Label(form, text="Infos:").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=infos_var, width=28).grid(row=row, column=1, pady=5, padx=5)
        row += 1

        # Boutons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", padx=20, pady=10)

        def save():
            try:
                # Trouver l'ID du voyage
                voyage_code = voyage_var.get()
                voyage_id = None
                for v in self.voyages:
                    if v.get("code") == voyage_code:
                        voyage_id = v.get("id")
                        break

                # Trouver l'ID du chauffeur
                chauffeur_nom = chauffeur_var.get()
                chauffeur_id = None
                for c in self.chauffeurs:
                    nom_complet = f"{c.get('nom', '')} {c.get('prenom', '')}".strip()
                    if nom_complet == chauffeur_nom:
                        chauffeur_id = c.get("id")
                        break

                # Trouver l'ID du SST
                sst_code = sst_var.get()
                sst_id = None
                for s in self.sst_list:
                    if s.get("code") == sst_code:
                        sst_id = s.get("id")
                        break

                data = {
                    "date_mission": self.current_date.isoformat(),
                    "heure_debut": heure_var.get() + ":00" if heure_var.get() else None,
                    "type_mission": type_var.get(),
                    "voyage_id": voyage_id,
                    "nb_palettes": int(nb_pal_var.get()) if nb_pal_var.get() else 0,
                    "numero": numero_var.get(),
                    "sst_id": sst_id,
                    "chauffeur_id": chauffeur_id,
                    "ramasse": ramasse_var.get(),
                    "commentaire": infos_var.get(),
                }

                if is_edit:
                    api_client.update_mission(mission["id"], data)
                else:
                    api_client.create_mission(data)

                dialog.destroy()
                self.load_planning_for_date(self.current_date)

            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de sauvegarder: {e}")

        ttk.Button(btn_frame, text="Enregistrer", command=save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Annuler", command=dialog.destroy).pack(side="left", padx=5)

    # ========== AUTRES ACTIONS ==========

    def _on_add_chauffeur(self):
        messagebox.showinfo("Info", "Fonctionnalité à implémenter")

    def _on_edit_chauffeur(self):
        messagebox.showinfo("Info", "Fonctionnalité à implémenter")

    def _refresh_chauffeurs(self):
        """Rafraîchit la liste des chauffeurs"""
        try:
            self.chauffeurs = api_client.get_chauffeurs(active_only=False) or []

            for item in self.chauffeurs_tree.get_children():
                self.chauffeurs_tree.delete(item)

            for c in self.chauffeurs:
                self.chauffeurs_tree.insert("", "end", values=(
                    c.get("code", ""),
                    c.get("nom", ""),
                    c.get("prenom", ""),
                    c.get("telephone", ""),
                    c.get("type_contrat", ""),
                    c.get("tracteur_attire", ""),
                    "Oui" if c.get("is_active", True) else "Non",
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de rafraîchir: {e}")

    def _on_add_voyage(self):
        messagebox.showinfo("Info", "Fonctionnalité à implémenter")

    def _on_edit_voyage(self):
        messagebox.showinfo("Info", "Fonctionnalité à implémenter")

    def _refresh_voyages(self):
        """Rafraîchit la liste des voyages"""
        try:
            self.voyages = api_client.get_voyages(active_only=False) or []

            for item in self.voyages_tree.get_children():
                self.voyages_tree.delete(item)

            for v in self.voyages:
                self.voyages_tree.insert("", "end", values=(
                    v.get("code", ""),
                    v.get("type", "LIVRAISON"),
                    v.get("pays_destination", "Belgique"),
                    "Oui" if v.get("is_active", True) else "Non",
                    v.get("duree", 60),
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de rafraîchir: {e}")

    def _run_analyse(self):
        """Lance une analyse"""
        start = parse_date(self.analyse_start_var.get())
        end = parse_date(self.analyse_end_var.get())

        if not start or not end:
            messagebox.showwarning("Attention", "Dates invalides")
            return

        try:
            missions = api_client.get_missions(date_debut=start, date_fin=end)

            # Afficher les résultats
            for widget in self.analyse_results_frame.winfo_children():
                widget.destroy()

            ttk.Label(self.analyse_results_frame,
                      text=f"Période: {format_date_display(start)} - {format_date_display(end)}",
                      font=("Arial", 11, "bold")).pack(pady=10)

            ttk.Label(self.analyse_results_frame,
                      text=f"Nombre de missions: {len(missions)}",
                      font=("Arial", 10)).pack(pady=5)

            total_pal = sum(m.get("nb_palettes", 0) or 0 for m in missions)
            ttk.Label(self.analyse_results_frame,
                      text=f"Total palettes: {total_pal}",
                      font=("Arial", 10)).pack(pady=5)

        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'analyser: {e}")

    def _on_add_user(self):
        messagebox.showinfo("Info", "Fonctionnalité à implémenter")

    def _refresh_users(self):
        """Rafraîchit la liste des utilisateurs"""
        try:
            users = api_client.get_users()

            for item in self.users_tree.get_children():
                self.users_tree.delete(item)

            for u in users:
                self.users_tree.insert("", "end", values=(
                    u.get("username", ""),
                    u.get("display_name", ""),
                    u.get("role", {}).get("name", "") if isinstance(u.get("role"), dict) else u.get("role_name", ""),
                    "Oui" if u.get("is_active", True) else "Non",
                    u.get("last_login", "")[:16] if u.get("last_login") else "",
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de rafraîchir: {e}")

    def _search_activity(self):
        """Recherche les activités d'un utilisateur"""
        username = self.sauron_user_var.get().strip()
        self._load_activity(username if username else None)

    def _show_all_activity(self):
        """Affiche toutes les activités"""
        self.sauron_user_var.set("")
        self._load_activity(None)

    def _load_activity(self, username: Optional[str]):
        """Charge les activités"""
        try:
            activities = api_client.get_recent_activity(limit=100, username=username)

            for item in self.activity_tree.get_children():
                self.activity_tree.delete(item)

            for a in activities:
                self.activity_tree.insert("", "end", values=(
                    a.get("created_at", "")[:19] if a.get("created_at") else "",
                    a.get("username", ""),
                    a.get("action_type", ""),
                    str(a.get("details", ""))[:100],
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger: {e}")

    def refresh_all(self):
        """Rafraîchit toutes les données"""
        api_client.invalidate_cache()
        self._load_initial_data()
        self.load_planning_for_date(self.current_date)

    def _on_close(self):
        """Fermeture de l'application"""
        try:
            live_sync.stop()
            connection_monitor.stop()
            api_client.logout()
        except Exception:
            pass
        finally:
            self.root.destroy()


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

def main():
    """Point d'entrée principal"""
    print(f"{APP_NAME} Client v{CLIENT_VERSION}")
    print("=" * 40)

    if not REQUESTS_AVAILABLE:
        messagebox.showerror("Erreur", "Module 'requests' requis.\npip install requests")
        return

    # Fenêtre de login
    login = LoginWindow()
    if not login.run():
        print("Connexion annulée")
        return

    print(f"Connecté: {api_client.user_info.get('username', '?')}")
    print("Chargement de l'application...")

    # Application principale
    root = tk.Tk()
    app = TomatoPlanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
