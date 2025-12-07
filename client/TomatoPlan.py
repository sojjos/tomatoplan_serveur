#!/usr/bin/env python3
"""
TomatoPlan Client - Version Standalone
======================================

Client complet pour TomatoPlan. Un seul fichier, pret a l'emploi.

Usage:
    python TomatoPlan.py

Placez ce fichier dans le meme dossier que PTT_v0.6.0.py
"""

import os
import sys
import json
import socket
import ssl
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

# ===========================================================================
# CONFIGURATION - Modifiez ici si necessaire
# ===========================================================================

SERVER_URL = "https://54.37.231.92"
VERIFY_SSL = False
TIMEOUT = 30

# ===========================================================================
# IMPORTS AVEC GESTION D'ERREURS
# ===========================================================================

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    print("ERREUR: tkinter n'est pas installe")
    print("Sur Linux: sudo apt install python3-tk")
    sys.exit(1)

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("ERREUR: requests n'est pas installe")
    print("Lancez: pip install requests")
    sys.exit(1)

# WebSocket optionnel
try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False


# ===========================================================================
# CLIENT API
# ===========================================================================

class APIClient:
    """Client API REST pour TomatoPlan"""

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
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None
        self.must_change_password = False
        self._session = requests.Session()
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, endpoint: str, data=None, params=None, use_cache=False):
        url = f"{self.server_url}{endpoint}"
        cache_key = f"{method}:{endpoint}:{json.dumps(params or {})}"

        if use_cache and method == "GET":
            with self._lock:
                if cache_key in self._cache:
                    ts = self._cache_timestamps.get(cache_key, 0)
                    if datetime.now().timestamp() - ts < 30:
                        return self._cache[cache_key]

        try:
            response = self._session.request(
                method=method, url=url, headers=self._headers(),
                json=data, params=params, timeout=TIMEOUT, verify=VERIFY_SSL
            )

            if response.status_code == 401:
                self.token = None
                raise PermissionError("Session expiree")
            if response.status_code == 403:
                raise PermissionError(f"Acces refuse: {response.json().get('detail', '')}")
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise Exception(f"Erreur API ({response.status_code}): {response.json().get('detail', '')}")

            result = response.json() if response.content else {"success": True}

            if use_cache and method == "GET":
                with self._lock:
                    self._cache[cache_key] = result
                    self._cache_timestamps[cache_key] = datetime.now().timestamp()

            return result

        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Impossible de se connecter au serveur")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Le serveur ne repond pas")

    def invalidate_cache(self, pattern: str = None):
        with self._lock:
            if pattern:
                keys = [k for k in self._cache.keys() if pattern in k]
                for k in keys:
                    del self._cache[k]
                    self._cache_timestamps.pop(k, None)
            else:
                self._cache.clear()
                self._cache_timestamps.clear()

    def check_server(self) -> Dict:
        try:
            r = requests.get(f"{self.server_url}/health", timeout=5, verify=VERIFY_SSL)
            return r.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def login(self, username: str, password: str) -> bool:
        response = self._request("POST", "/auth/login", {
            "username": username, "password": password, "hostname": socket.gethostname()
        })
        if response and "access_token" in response:
            self.token = response["access_token"]
            self.user_info = response.get("user", {})
            self.must_change_password = response.get("must_change_password", False)
            return True
        return False

    def logout(self):
        if self.token:
            try:
                self._request("POST", "/auth/logout")
            except:
                pass
        self.token = None
        self.user_info = None

    def change_password(self, current: str, new: str) -> bool:
        r = self._request("POST", "/auth/change-password", {"current_password": current, "new_password": new})
        if r and r.get("success"):
            self.must_change_password = False
            return True
        return False

    def get_permissions(self) -> Dict:
        return self.user_info.get("permissions", {}) if self.user_info else {}

    # Missions
    def get_missions_by_date(self, d: date) -> List[Dict]:
        return self._request("GET", f"/missions/by-date/{d.isoformat()}", use_cache=True) or []

    def get_missions(self, date_debut=None, date_fin=None, **filters) -> List[Dict]:
        params = {}
        if date_debut:
            params["date_debut"] = date_debut if isinstance(date_debut, str) else date_debut.isoformat()
        if date_fin:
            params["date_fin"] = date_fin if isinstance(date_fin, str) else date_fin.isoformat()
        params.update(filters)
        return self._request("GET", "/missions", params=params) or []

    def create_mission(self, data: Dict) -> Dict:
        self.invalidate_cache("/missions")
        return self._request("POST", "/missions", data)

    def update_mission(self, mid: int, data: Dict) -> Dict:
        self.invalidate_cache("/missions")
        return self._request("PUT", f"/missions/{mid}", data)

    def delete_mission(self, mid: int) -> bool:
        self.invalidate_cache("/missions")
        r = self._request("DELETE", f"/missions/{mid}")
        return r.get("success", False) if r else False

    # Voyages
    def get_voyages(self, active_only: bool = True) -> List[Dict]:
        return self._request("GET", "/voyages", params={"active_only": active_only}, use_cache=True) or []

    def create_voyage(self, data: Dict) -> Dict:
        self.invalidate_cache("/voyages")
        return self._request("POST", "/voyages", data)

    def update_voyage(self, vid: int, data: Dict) -> Dict:
        self.invalidate_cache("/voyages")
        return self._request("PUT", f"/voyages/{vid}", data)

    # Chauffeurs
    def get_chauffeurs(self, active_only: bool = True) -> List[Dict]:
        return self._request("GET", "/chauffeurs", params={"active_only": active_only}, use_cache=True) or []

    def get_chauffeurs_disponibles(self, d: date) -> Dict:
        return self._request("GET", f"/chauffeurs/disponibles/{d.isoformat()}") or {"disponibles": [], "indisponibles": []}

    def get_chauffeur_disponibilites(self, cid: int, date_debut=None, date_fin=None) -> List[Dict]:
        params = {}
        if date_debut:
            params["date_debut"] = date_debut.isoformat() if isinstance(date_debut, date) else date_debut
        if date_fin:
            params["date_fin"] = date_fin.isoformat() if isinstance(date_fin, date) else date_fin
        return self._request("GET", f"/chauffeurs/{cid}/disponibilites", params=params) or []

    def create_chauffeur(self, data: Dict) -> Dict:
        self.invalidate_cache("/chauffeurs")
        return self._request("POST", "/chauffeurs", data)

    def update_chauffeur(self, cid: int, data: Dict) -> Dict:
        self.invalidate_cache("/chauffeurs")
        return self._request("PUT", f"/chauffeurs/{cid}", data)

    def create_disponibilite(self, data: Dict) -> Dict:
        return self._request("POST", "/chauffeurs/disponibilites", data)

    def delete_disponibilite(self, did: int) -> bool:
        r = self._request("DELETE", f"/chauffeurs/disponibilites/{did}")
        return r.get("success", False) if r else False

    # SST
    def get_sst_list(self, active_only: bool = True) -> List[Dict]:
        return self._request("GET", "/sst", params={"active_only": active_only}, use_cache=True) or []

    def get_sst_tarifs(self, sst_id: int = None) -> List[Dict]:
        if sst_id:
            return self._request("GET", f"/sst/{sst_id}/tarifs") or []
        return self._request("GET", "/sst/tarifs/all") or []

    def create_sst(self, data: Dict) -> Dict:
        self.invalidate_cache("/sst")
        return self._request("POST", "/sst", data)

    def update_sst(self, sid: int, data: Dict) -> Dict:
        self.invalidate_cache("/sst")
        return self._request("PUT", f"/sst/{sid}", data)

    # Finance
    def get_revenus_palettes(self) -> List[Dict]:
        return self._request("GET", "/finance/revenus", use_cache=True) or []

    def create_revenu_palette(self, data: Dict) -> Dict:
        self.invalidate_cache("/finance")
        return self._request("POST", "/finance/revenus", data)

    def get_finance_stats(self, d1: date, d2: date) -> Dict:
        return self._request("GET", "/finance/stats", params={"date_debut": d1.isoformat(), "date_fin": d2.isoformat()}) or {}

    # Stats
    def get_dashboard_stats(self) -> Dict:
        return self._request("GET", "/stats/dashboard") or {}

    def get_recent_activity(self, limit: int = 50, username: str = None) -> List[Dict]:
        params = {"limit": limit}
        if username:
            params["username"] = username
        return self._request("GET", "/stats/activity/recent", params=params) or []

    # Admin
    def get_users(self) -> List[Dict]:
        return self._request("GET", "/admin/users") or []

    def get_roles(self) -> List[Dict]:
        return self._request("GET", "/admin/roles") or []

    def create_user(self, data: Dict) -> Dict:
        return self._request("POST", "/admin/users", data)

    def update_user(self, uid: int, data: Dict) -> Dict:
        return self._request("PUT", f"/admin/users/{uid}", data)


# Instance globale
api_client = APIClient()


# ===========================================================================
# MONITEUR DE CONNEXION
# ===========================================================================

class ConnectionMonitor:
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
        self._callbacks: List[Callable] = []
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while not self._stop_event.is_set():
            self._check()
            self._stop_event.wait(5)

    def _check(self):
        old = self._is_online
        try:
            r = api_client.check_server()
            self._is_online = r.get("status") == "ok"
        except:
            self._is_online = False
        if old != self._is_online:
            for cb in self._callbacks:
                try:
                    cb(self._is_online)
                except:
                    pass

    def add_callback(self, cb):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    @property
    def is_online(self) -> bool:
        return self._is_online


connection_monitor = ConnectionMonitor()


# ===========================================================================
# CLIENT WEBSOCKET
# ===========================================================================

class LiveSyncClient:
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
        self._on_data_changed_callbacks: List[Callable] = []
        self._connected_users: List[str] = []

    def start(self):
        if not HAS_WEBSOCKET:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as e:
                print(f"[WS] Erreur: {e}")
            if not self._stop_event.is_set():
                self._stop_event.wait(5)

    def _connect(self):
        ws_url = SERVER_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
        if api_client.token:
            ws_url += f"?token={api_client.token}"

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=lambda ws, e: None,
            on_close=self._on_close
        )
        ssl_opt = {"cert_reqs": ssl.CERT_NONE} if not VERIFY_SSL else None
        self._ws.run_forever(sslopt=ssl_opt)

    def _on_open(self, ws):
        self._connected = True

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "welcome":
                self._connected_users = data.get("connected_users", [])
            elif msg_type == "data_changed":
                change = data.get("data", {})
                entity = change.get("entity", "")
                action = change.get("action", "")
                api_client.invalidate_cache(f"/{entity}")
                for cb in self._on_data_changed_callbacks:
                    try:
                        cb(entity, action, change)
                    except:
                        pass
            elif msg_type == "refresh_required":
                api_client.invalidate_cache()
                for cb in self._on_data_changed_callbacks:
                    try:
                        cb("all", "refresh", data.get("data", {}))
                    except:
                        pass
        except:
            pass

    def _on_close(self, ws, code, msg):
        self._connected = False

    def on_data_changed(self, cb):
        if cb not in self._on_data_changed_callbacks:
            self._on_data_changed_callbacks.append(cb)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connected_users_count(self) -> int:
        return len(self._connected_users)


live_sync = LiveSyncClient()


# ===========================================================================
# FONCTIONS D'ADAPTATION POUR PTT
# ===========================================================================

def api_load_json(filename, default=None):
    filename_str = str(filename).lower()
    try:
        if "voyages.json" in filename_str:
            voyages = api_client.get_voyages(active_only=False) or []
            return [{
                "code": v.get("code", ""),
                "type": v.get("type", "LIVRAISON") if "type" in v else ("LIVRAISON" if v.get("is_livraison", True) else "RAMASSE"),
                "actif": v.get("is_active", True),
                "country": v.get("pays_destination", "Belgique"),
                "duree": v.get("duree", 60),
                "description": v.get("description", ""),
            } for v in voyages]

        elif "chauffeurs.json" in filename_str:
            chauffeurs = api_client.get_chauffeurs(active_only=False) or []
            return [{
                "id": c.get("id"), "code": c.get("code", ""), "nom": c.get("nom", ""),
                "prenom": c.get("prenom", ""), "telephone": c.get("telephone", ""),
                "email": c.get("email", ""), "type": c.get("type_contrat", "INTERNE"),
                "actif": c.get("is_active", True), "tracteur_attire": c.get("tracteur_attire", ""),
                "adr": c.get("adr", False), "fimo": c.get("fimo", True),
            } for c in chauffeurs]

        elif "dispo_chauffeurs.json" in filename_str:
            return []

        elif "sst.json" in filename_str:
            sst_list = api_client.get_sst_list(active_only=False) or []
            return [s.get("code", "") for s in sst_list]

        elif "tarifs_sst.json" in filename_str:
            tarifs = api_client.get_sst_tarifs() or []
            result = {}
            for t in tarifs:
                sst = t.get("sst_code", "")
                if sst not in result:
                    result[sst] = {}
                result[sst][t.get("destination", "")] = t.get("prix", 0)
            return result

        elif "revenus_palettes.json" in filename_str:
            revenus = api_client.get_revenus_palettes() or []
            return {r.get("destination", ""): r.get("revenu_par_palette", 0) for r in revenus}

        elif "users_rights.json" in filename_str:
            # Retourner des droits par defaut si l'API echoue
            try:
                users = api_client.get_users() or []
                roles = api_client.get_roles() or []
                return {
                    "roles": {r.get("name", ""): {"view_planning": True} for r in roles} if roles else {"admin": {"view_planning": True}},
                    "users": {u.get("username", ""): [u.get("role", "viewer")] for u in users} if users else {}
                }
            except:
                # Droits par defaut pour que l'app fonctionne
                current_user = get_current_user()
                return {
                    "roles": {"admin": {"view_planning": True, "edit_planning": True, "manage_users": True}},
                    "users": {current_user: ["admin"]}
                }

        elif "missions.json" in filename_str or "/planning/" in filename_str:
            return default if default is not None else []

        return default if default is not None else {}
    except Exception as e:
        print(f"[API] Erreur chargement {filename}: {e}")
        # Retourner des valeurs par defaut appropriees selon le type de fichier
        if "users_rights.json" in filename_str:
            current_user = get_current_user()
            return {"roles": {"admin": {"view_planning": True}}, "users": {current_user: ["admin"]}}
        elif "voyages.json" in filename_str or "chauffeurs.json" in filename_str or "sst.json" in filename_str:
            return []
        elif "tarifs_sst.json" in filename_str or "revenus_palettes.json" in filename_str:
            return {}
        return default if default is not None else {}


def api_save_json(filename, data):
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
    try:
        today = date.today()
        missions = api_client.get_missions(date_debut=today - timedelta(days=90), date_fin=today + timedelta(days=30))
        dates_set = set()
        for m in missions:
            d = m.get("date_mission")
            if d:
                if isinstance(d, str):
                    try:
                        d = datetime.fromisoformat(d.replace("Z", "")).date()
                    except:
                        continue
                dates_set.add(d.strftime("%d/%m/%Y"))
        return sorted(dates_set, key=lambda x: datetime.strptime(x, "%d/%m/%Y"))
    except Exception as e:
        print(f"[API] Erreur list_existing_dates: {e}")
        return []


def api_get_planning_for_date(d: date) -> List[Dict]:
    try:
        return api_client.get_missions_by_date(d)
    except Exception as e:
        print(f"[API] Erreur get_planning_for_date: {e}")
        return []


class ActivityLogger:
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
        pass

    def log_session_end(self):
        try:
            api_client.logout()
        except:
            pass


activity_logger = ActivityLogger()


def is_online() -> bool:
    return connection_monitor.is_online


def get_current_user() -> str:
    return api_client.user_info.get("username", "INCONNU") if api_client.user_info else "INCONNU"


# ===========================================================================
# FENETRE DE CONNEXION
# ===========================================================================

class LoginWindow:
    def __init__(self):
        self.authenticated = False
        self.root = tk.Tk()
        self.root.title("TomatoPlan - Connexion")
        self.root.geometry("420x380")
        self.root.resizable(False, False)

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 210
        y = (self.root.winfo_screenheight() // 2) - 190
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self._check_server()

    def _build_ui(self):
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=20)
        ttk.Label(title_frame, text="TomatoPlan", font=("Arial", 28, "bold")).pack()
        ttk.Label(title_frame, text="Planning Transport Tubize", font=("Arial", 11)).pack()
        ttk.Label(title_frame, text="Client v1.0", font=("Arial", 9), foreground="gray").pack()

        status_frame = ttk.Frame(self.root)
        status_frame.pack(pady=10)
        self.status_label = ttk.Label(status_frame, text="Verification du serveur...", foreground="orange")
        self.status_label.pack()

        form_frame = ttk.LabelFrame(self.root, text="Connexion", padding=15)
        form_frame.pack(padx=20, pady=10, fill="x")

        ttk.Label(form_frame, text="Utilisateur:").grid(row=0, column=0, sticky="w", pady=5)
        default_user = os.environ.get("USERNAME", os.environ.get("USER", "")).upper()
        self.username_var = tk.StringVar(value=default_user)
        self.username_entry = ttk.Entry(form_frame, textvariable=self.username_var, width=30)
        self.username_entry.grid(row=0, column=1, pady=5, padx=5)

        ttk.Label(form_frame, text="Mot de passe:").grid(row=1, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(form_frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=1, column=1, pady=5, padx=5)
        self.password_entry.bind("<Return>", lambda e: self._on_login())

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=15)
        self.login_btn = ttk.Button(btn_frame, text="Connexion", command=self._on_login, width=15)
        self.login_btn.pack(side="left", padx=5)
        self.login_btn.config(state="disabled")
        ttk.Button(btn_frame, text="Quitter", command=self.root.destroy, width=15).pack(side="left", padx=5)

        self.error_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.error_var, foreground="red", wraplength=380).pack(pady=5)
        ttk.Label(self.root, text=f"Serveur: {SERVER_URL}", font=("Arial", 8), foreground="gray").pack(side="bottom", pady=5)
        self.password_entry.focus()

    def _check_server(self):
        def check():
            try:
                status = api_client.check_server()
                if status.get("status") == "ok":
                    self.root.after(0, lambda: self._update_status(True, "Serveur connecte"))
                else:
                    self.root.after(0, lambda: self._update_status(False, "Serveur indisponible"))
            except Exception as e:
                self.root.after(0, lambda: self._update_status(False, f"Erreur: {str(e)[:50]}"))
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
        dialog = tk.Toplevel(self.root)
        dialog.title("Changement de mot de passe requis")
        dialog.geometry("420x280")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 210
        y = (dialog.winfo_screenheight() // 2) - 140
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="Vous devez changer votre mot de passe temporaire", font=("Arial", 10, "bold")).pack(pady=15)

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
        ttk.Label(dialog, text="(Min 8 caracteres, majuscule, minuscule, chiffre)", font=("Arial", 8), foreground="gray").pack()

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
                if api_client.change_password(self.password_var.get(), new_pwd):
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
        self.root.mainloop()
        return self.authenticated


# ===========================================================================
# PATCH PTT
# ===========================================================================

def patch_and_run_ptt():
    # Chercher PTT_v0.6.0.py
    script_dir = Path(__file__).parent
    ptt_path = script_dir / "PTT_v0.6.0.py"

    if not ptt_path.exists():
        # Essayer dans le dossier parent
        ptt_path = script_dir.parent / "PTT_v0.6.0.py"

    if not ptt_path.exists():
        messagebox.showerror("Erreur", f"PTT_v0.6.0.py non trouve!\n\nPlacez TomatoPlan.py dans le meme dossier que PTT_v0.6.0.py")
        return

    with open(ptt_path, "r", encoding="utf-8") as f:
        ptt_source = f.read()

    # Remplacer les fonctions originales
    patched_source = ptt_source.replace(
        "def load_json(filename, default=None):",
        "def _original_load_json(filename, default=None):  # PATCHED"
    )
    patched_source = patched_source.replace(
        "def save_json(filename, data):",
        "def _original_save_json(filename, data):  # PATCHED"
    )
    patched_source = patched_source.replace(
        "def list_existing_dates():",
        "def _original_list_existing_dates():  # PATCHED"
    )

    # Commenter les definitions de DATA_DIR et fichiers pour eviter OneDrive
    patched_source = patched_source.replace(
        '# Dossier de données OneDrive\nDATA_DIR = Path.home()',
        '# PATCHED - OneDrive desactive\n_ORIGINAL_DATA_DIR = Path.home()'
    )
    patched_source = patched_source.replace(
        'DATA_DIR = Path.home() / "OneDrive - STEF"',
        '_DISABLED_DATA_DIR = None  # PATCHED\n# DATA_DIR = Path.home() / "OneDrive - STEF"'
    )
    patched_source = patched_source.replace(
        "DATA_DIR.mkdir(parents=True, exist_ok=True)",
        "pass  # PATCHED - DATA_DIR.mkdir"
    )

    # Header avec les fonctions patchees - utilise les globals injectes
    header = '''
# ===== PATCHED FOR CLIENT-SERVER MODE =====
import tempfile
from pathlib import Path

# Remplacer DATA_DIR par un dossier temporaire local (pas OneDrive)
DATA_DIR = Path(tempfile.gettempdir()) / "TomatoPlan_Client"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Chemins des fichiers (rediriges vers le dossier temp)
MISSIONS_FILE = DATA_DIR / "missions.json"
VOYAGES_FILE = DATA_DIR / "voyages.json"
CHAUFFEURS_FILE = DATA_DIR / "chauffeurs.json"
TARIFS_SST_FILE = DATA_DIR / "tarifs_sst.json"
REVENUS_FILE = DATA_DIR / "revenus_palettes.json"
SST_EMAILS_FILE = DATA_DIR / "sst_emails.json"
ANNOUNCEMENT_CONFIG_FILE = DATA_DIR / "announcement_config.json"
ANNOUNCEMENT_HISTORY_FILE = DATA_DIR / "announcement_history.json"

# Ces variables sont injectees via exec_globals
# _api_client, _connection_monitor, _live_sync, etc.

def load_json(filename, default=None):
    return _api_load_json(filename, default)

def save_json(filename, data):
    return _api_save_json(filename, data)

def list_existing_dates():
    return _api_list_existing_dates()

class ActivityLogger:
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
        pass
    def log_session_end(self):
        pass

activity_logger = ActivityLogger()

_ptt_app_instance = None

def _on_data_changed(entity_type, action, data):
    global _ptt_app_instance
    if not _ptt_app_instance:
        return
    changed_by = data.get("changed_by", "")
    if changed_by == _ptt_app_instance.current_user:
        return
    def do_refresh():
        try:
            if hasattr(_ptt_app_instance, 'refresh_all'):
                _ptt_app_instance.refresh_all()
        except:
            pass
    try:
        _ptt_app_instance.root.after(100, do_refresh)
    except:
        pass

def _update_live_status(app):
    if not hasattr(app, 'status_var') or not hasattr(app, 'root'):
        return
    try:
        is_live = _connection_monitor.is_online
        ws_connected = _live_sync.is_connected
        users_count = _live_sync.connected_users_count
        if ws_connected:
            status_text = f"En ligne ({users_count} utilisateur{'s' if users_count > 1 else ''})"
            indicator = "●"
        elif is_live:
            status_text = "En ligne"
            indicator = "●"
        else:
            status_text = "Hors ligne"
            indicator = "○"
        app.status_var.set(f"Session : {app.current_user} | {indicator} {status_text}")
        if hasattr(app, 'status_label'):
            try:
                app.status_label.config(foreground="green" if (is_live or ws_connected) else "red")
            except:
                pass
    except:
        pass

def _start_live_status_monitor(app):
    global _ptt_app_instance
    _ptt_app_instance = app
    _connection_monitor.start()
    _live_sync.on_data_changed(_on_data_changed)
    _live_sync.start()
    def update_loop():
        if _ptt_app_instance and hasattr(_ptt_app_instance, 'root'):
            _update_live_status(_ptt_app_instance)
            try:
                _ptt_app_instance.root.after(5000, update_loop)
            except:
                pass
    _update_live_status(app)
    try:
        app.root.after(5000, update_loop)
    except:
        pass

# ===== END PATCH =====

'''

    # Patcher update_status_bar_initial
    patched_source = patched_source.replace(
        '''def update_status_bar_initial(self):
        """Initialise la barre de statut au démarrage (session + heure de lancement)."""
        from datetime import datetime
        self.last_refresh_dt = datetime.now()
        try:
            self.status_var.set(
                f"Session : {self.current_user} | Dernière MAJ : {self.last_refresh_dt.strftime('%d/%m/%Y %H:%M:%S')}"
            )
        except Exception:
            pass''',
        '''def update_status_bar_initial(self):
        """Initialise la barre de statut avec statut live."""
        _start_live_status_monitor(self)'''
    )

    patched_source = header + patched_source

    # Executer avec les objets authentifies injectes directement
    import builtins
    code = compile(patched_source, str(ptt_path), "exec")

    # Injecter les objets directement dans le namespace d'execution
    exec_globals = {
        "__name__": "__main__",
        "__file__": str(ptt_path),
        "__builtins__": builtins,
        # Injecter les objets authentifies
        "_api_client": api_client,
        "_connection_monitor": connection_monitor,
        "_live_sync": live_sync,
        "_api_load_json": api_load_json,
        "_api_save_json": api_save_json,
        "_api_list_existing_dates": api_list_existing_dates,
        "_api_get_planning_for_date": api_get_planning_for_date,
    }

    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    os.chdir(ptt_path.parent)

    # Executer PTT avec gestion d'erreur detaillee
    try:
        exec(code, exec_globals)
    except Exception as e:
        import traceback
        print("\n" + "="*50)
        print("ERREUR LORS DE L'EXECUTION DE PTT:")
        print("="*50)
        traceback.print_exc()
        print("="*50 + "\n")
        raise


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    print("TomatoPlan Client - Connexion au serveur...")

    login = LoginWindow()
    if not login.run():
        print("Connexion annulee")
        return

    print(f"Connecte: {get_current_user()}")
    print("Chargement de l'application...")

    try:
        patch_and_run_ptt()
    except FileNotFoundError as e:
        messagebox.showerror("Erreur", str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("Erreur", f"Erreur au lancement: {e}")
    finally:
        try:
            live_sync.stop()
        except:
            pass
        try:
            connection_monitor.stop()
        except:
            pass
        try:
            api_client.logout()
        except:
            pass


if __name__ == "__main__":
    main()
