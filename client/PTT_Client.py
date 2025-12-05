"""
PTT Client v0.6.0 - Version Client-Serveur
=========================================

Client Python pour TomatoPlan avec architecture client-serveur.
Ce fichier remplace l'application locale PTT_v0.6.0.py par une version
qui communique avec le serveur TomatoPlan via API REST.

Configuration:
    - Modifier SERVER_URL pour pointer vers votre serveur
    - Pour certificat auto-signe, mettre VERIFY_SSL = False

Usage:
    python PTT_Client.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import json
import os
import sys
import getpass
import socket
import threading
import queue
from datetime import date, datetime, timedelta
import uuid

# Ajouter le dossier parent au path pour importer le client API
sys.path.insert(0, str(Path(__file__).parent.parent / "client_example"))

# ============================================================================
# CONFIGURATION DU SERVEUR
# ============================================================================
SERVER_URL = "https://54.37.231.92"  # URL du serveur TomatoPlan
VERIFY_SSL = False  # False pour certificats auto-signes
TIMEOUT = 30  # Timeout des requetes en secondes

# ============================================================================
# CLIENT API
# ============================================================================
import requests
import urllib3

# Desactiver les warnings pour les certificats auto-signes
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TomatoPlanClient:
    """Client pour l'API TomatoPlan - Version integree"""

    def __init__(self, server_url: str, timeout: int = 30, verify_ssl: bool = True):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.token = None
        self.user_info = None
        self.must_change_password = False
        self._session = requests.Session()

        # Cache local pour les donnees
        self._cache_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "TomatoPlan" / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_windows_username(self) -> str:
        username = os.environ.get("USERNAME")
        if not username:
            username = getpass.getuser()
        return username.upper()

    def _get_hostname(self) -> str:
        return socket.gethostname()

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, endpoint: str, data=None, params=None):
        url = f"{self.server_url}{endpoint}"
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
                raise PermissionError(f"Acces refuse: {response.json().get('detail', 'Permission refusee')}")

            if response.status_code == 404:
                return None

            if response.status_code >= 400:
                error_detail = response.json().get("detail", "Erreur inconnue")
                raise Exception(f"Erreur API ({response.status_code}): {error_detail}")

            if response.content:
                return response.json()
            return {"success": True}

        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Impossible de se connecter au serveur {self.server_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Le serveur ne repond pas (timeout: {self.timeout}s)")

    # ============== Authentification ==============

    def login(self, username: str = None, password: str = None) -> bool:
        if username is None:
            username = self._get_windows_username()

        hostname = self._get_hostname()

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
        if self.token:
            try:
                self._request("POST", "/auth/logout")
            except Exception:
                pass
        self.token = None
        self.user_info = None

    def change_password(self, current_password: str, new_password: str) -> bool:
        response = self._request("POST", "/auth/change-password", {
            "current_password": current_password,
            "new_password": new_password
        })
        if response and response.get("success"):
            self.must_change_password = False
            return True
        return False

    def is_authenticated(self) -> bool:
        return self.token is not None

    def check_server(self):
        try:
            response = requests.get(
                f"{self.server_url}/health",
                timeout=5,
                verify=self.verify_ssl
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ============== Missions ==============

    def get_missions(self, date_debut=None, date_fin=None, chauffeur_id=None, voyage_id=None, statut=None):
        params = {}
        if date_debut:
            params["date_debut"] = date_debut
        if date_fin:
            params["date_fin"] = date_fin
        if chauffeur_id:
            params["chauffeur_id"] = chauffeur_id
        if voyage_id:
            params["voyage_id"] = voyage_id
        if statut:
            params["statut"] = statut
        return self._request("GET", "/missions", params=params) or []

    def get_missions_by_date(self, mission_date: str):
        return self._request("GET", f"/missions/by-date/{mission_date}") or []

    def get_mission(self, mission_id: int):
        return self._request("GET", f"/missions/{mission_id}")

    def create_mission(self, mission_data):
        return self._request("POST", "/missions", mission_data)

    def update_mission(self, mission_id: int, mission_data):
        return self._request("PUT", f"/missions/{mission_id}", mission_data)

    def delete_mission(self, mission_id: int):
        result = self._request("DELETE", f"/missions/{mission_id}")
        return result.get("success", False) if result else False

    # ============== Voyages ==============

    def get_voyages(self, active_only: bool = True):
        params = {"active_only": active_only}
        return self._request("GET", "/voyages", params=params) or []

    def get_voyage(self, voyage_id: int):
        return self._request("GET", f"/voyages/{voyage_id}")

    def create_voyage(self, voyage_data):
        return self._request("POST", "/voyages", voyage_data)

    def update_voyage(self, voyage_id: int, voyage_data):
        return self._request("PUT", f"/voyages/{voyage_id}", voyage_data)

    # ============== Chauffeurs ==============

    def get_chauffeurs(self, active_only: bool = True):
        params = {"active_only": active_only}
        return self._request("GET", "/chauffeurs", params=params) or []

    def get_chauffeur(self, chauffeur_id: int):
        return self._request("GET", f"/chauffeurs/{chauffeur_id}")

    def get_chauffeurs_disponibles(self, check_date: str):
        return self._request("GET", f"/chauffeurs/disponibles/{check_date}")

    def create_chauffeur(self, chauffeur_data):
        return self._request("POST", "/chauffeurs", chauffeur_data)

    def update_chauffeur(self, chauffeur_id: int, chauffeur_data):
        return self._request("PUT", f"/chauffeurs/{chauffeur_id}", chauffeur_data)


# Instance globale du client
api_client = None


def get_api_client() -> TomatoPlanClient:
    """Retourne le client API global"""
    global api_client
    if api_client is None:
        raise RuntimeError("Client non initialise. Lancez l'application via main()")
    return api_client


# ============================================================================
# FENETRE DE CONNEXION
# ============================================================================

class LoginWindow:
    """Fenetre de connexion au serveur TomatoPlan"""

    def __init__(self, server_url: str, verify_ssl: bool = True):
        self.server_url = server_url
        self.verify_ssl = verify_ssl
        self.client = None
        self.authenticated = False

        self.root = tk.Tk()
        self.root.title("TomatoPlan - Connexion")
        self.root.geometry("400x350")
        self.root.resizable(False, False)

        # Centrer la fenetre
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self._check_server()

    def _build_ui(self):
        # Titre
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=20)

        ttk.Label(title_frame, text="TomatoPlan", font=("Arial", 24, "bold")).pack()
        ttk.Label(title_frame, text="Planning Transport Tubize", font=("Arial", 10)).pack()

        # Status serveur
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(pady=10)

        self.status_label = ttk.Label(self.status_frame, text="Verification du serveur...", foreground="orange")
        self.status_label.pack()

        # Formulaire
        form_frame = ttk.LabelFrame(self.root, text="Connexion", padding=15)
        form_frame.pack(padx=20, pady=10, fill="x")

        # Username
        ttk.Label(form_frame, text="Utilisateur:").grid(row=0, column=0, sticky="w", pady=5)
        self.username_var = tk.StringVar(value=os.environ.get("USERNAME", getpass.getuser()).upper())
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
        btn_frame.pack(pady=20)

        self.login_btn = ttk.Button(btn_frame, text="Connexion", command=self._on_login, width=15)
        self.login_btn.pack(side="left", padx=5)

        ttk.Button(btn_frame, text="Quitter", command=self.root.destroy, width=15).pack(side="left", padx=5)

        # Message d'erreur
        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(self.root, textvariable=self.error_var, foreground="red", wraplength=350)
        self.error_label.pack(pady=5)

        # Focus sur le mot de passe
        self.password_entry.focus()

    def _check_server(self):
        """Verifie la connexion au serveur"""
        def check():
            try:
                client = TomatoPlanClient(self.server_url, verify_ssl=self.verify_ssl)
                status = client.check_server()
                if status.get("status") == "ok":
                    self.root.after(0, lambda: self._update_status(True, f"Serveur connecte - {self.server_url}"))
                else:
                    self.root.after(0, lambda: self._update_status(False, f"Serveur indisponible: {status.get('message', 'Erreur')}"))
            except Exception as e:
                self.root.after(0, lambda: self._update_status(False, f"Erreur: {str(e)}"))

        threading.Thread(target=check, daemon=True).start()

    def _update_status(self, connected: bool, message: str):
        if connected:
            self.status_label.config(text=message, foreground="green")
            self.login_btn.config(state="normal")
        else:
            self.status_label.config(text=message, foreground="red")
            self.login_btn.config(state="disabled")

    def _on_login(self):
        """Tente la connexion"""
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
                client = TomatoPlanClient(self.server_url, verify_ssl=self.verify_ssl)
                if client.login(username, password):
                    self.client = client
                    self.authenticated = True
                    self.root.after(0, self._on_login_success)
                else:
                    self.root.after(0, lambda: self._on_login_error("Echec de l'authentification"))
            except PermissionError as e:
                self.root.after(0, lambda: self._on_login_error(str(e)))
            except ConnectionError as e:
                self.root.after(0, lambda: self._on_login_error(f"Connexion impossible: {e}"))
            except Exception as e:
                self.root.after(0, lambda: self._on_login_error(f"Erreur: {e}"))

        threading.Thread(target=do_login, daemon=True).start()

    def _on_login_success(self):
        """Connexion reussie"""
        # Verifier si changement de mot de passe requis
        if self.client.must_change_password:
            self._show_change_password_dialog()
        else:
            self.root.destroy()

    def _on_login_error(self, message: str):
        """Erreur de connexion"""
        self.error_var.set(message)
        self.login_btn.config(state="normal")
        self.status_label.config(text=f"Serveur connecte - {self.server_url}", foreground="green")

    def _show_change_password_dialog(self):
        """Dialogue pour changer le mot de passe temporaire"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Changement de mot de passe requis")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Vous devez changer votre mot de passe temporaire",
                  font=("Arial", 10, "bold")).pack(pady=10)

        form = ttk.Frame(dialog, padding=15)
        form.pack(fill="x")

        ttk.Label(form, text="Nouveau mot de passe:").grid(row=0, column=0, sticky="w", pady=5)
        new_pwd_var = tk.StringVar()
        new_pwd_entry = ttk.Entry(form, textvariable=new_pwd_var, show="*", width=30)
        new_pwd_entry.grid(row=0, column=1, pady=5)

        ttk.Label(form, text="Confirmer:").grid(row=1, column=0, sticky="w", pady=5)
        confirm_var = tk.StringVar()
        confirm_entry = ttk.Entry(form, textvariable=confirm_var, show="*", width=30)
        confirm_entry.grid(row=1, column=1, pady=5)

        error_var = tk.StringVar()
        ttk.Label(dialog, textvariable=error_var, foreground="red").pack()

        ttk.Label(dialog, text="(Min 8 car., majuscule, minuscule, chiffre)",
                  font=("Arial", 8), foreground="gray").pack()

        def do_change():
            new_pwd = new_pwd_var.get()
            confirm = confirm_var.get()

            if new_pwd != confirm:
                error_var.set("Les mots de passe ne correspondent pas")
                return

            if len(new_pwd) < 8:
                error_var.set("Le mot de passe doit faire au moins 8 caracteres")
                return

            try:
                current_pwd = self.password_var.get()
                if self.client.change_password(current_pwd, new_pwd):
                    dialog.destroy()
                    self.root.destroy()
                else:
                    error_var.set("Echec du changement de mot de passe")
            except Exception as e:
                error_var.set(str(e))

        ttk.Button(dialog, text="Changer", command=do_change).pack(pady=10)

        new_pwd_entry.focus()
        dialog.wait_window()

    def run(self):
        """Lance la fenetre de connexion"""
        self.root.mainloop()
        return self.client if self.authenticated else None


# ============================================================================
# ADAPTATEUR DE DONNEES - Remplace load_json/save_json
# ============================================================================

class DataAdapter:
    """
    Adaptateur qui remplace les fonctions load_json/save_json
    par des appels API vers le serveur.
    """

    def __init__(self, client: TomatoPlanClient):
        self.client = client
        self._cache = {}

    def get_missions_for_date(self, d: date):
        """Recupere les missions d'une date"""
        try:
            return self.client.get_missions_by_date(d.isoformat())
        except Exception as e:
            print(f"Erreur recuperation missions: {e}")
            return []

    def save_mission(self, mission_data):
        """Cree ou met a jour une mission"""
        try:
            if "id" in mission_data and mission_data["id"]:
                return self.client.update_mission(mission_data["id"], mission_data)
            else:
                return self.client.create_mission(mission_data)
        except Exception as e:
            print(f"Erreur sauvegarde mission: {e}")
            raise

    def delete_mission(self, mission_id):
        """Supprime une mission"""
        try:
            return self.client.delete_mission(mission_id)
        except Exception as e:
            print(f"Erreur suppression mission: {e}")
            raise

    def get_voyages(self, active_only=True):
        """Recupere les voyages"""
        try:
            return self.client.get_voyages(active_only)
        except Exception as e:
            print(f"Erreur recuperation voyages: {e}")
            return []

    def save_voyage(self, voyage_data):
        """Cree ou met a jour un voyage"""
        try:
            if "id" in voyage_data and voyage_data["id"]:
                return self.client.update_voyage(voyage_data["id"], voyage_data)
            else:
                return self.client.create_voyage(voyage_data)
        except Exception as e:
            print(f"Erreur sauvegarde voyage: {e}")
            raise

    def get_chauffeurs(self, active_only=True):
        """Recupere les chauffeurs"""
        try:
            return self.client.get_chauffeurs(active_only)
        except Exception as e:
            print(f"Erreur recuperation chauffeurs: {e}")
            return []

    def get_chauffeurs_disponibles(self, d: date):
        """Recupere les chauffeurs disponibles pour une date"""
        try:
            return self.client.get_chauffeurs_disponibles(d.isoformat())
        except Exception as e:
            print(f"Erreur recuperation disponibilites: {e}")
            return {"disponibles": [], "indisponibles": []}

    def save_chauffeur(self, chauffeur_data):
        """Cree ou met a jour un chauffeur"""
        try:
            if "id" in chauffeur_data and chauffeur_data["id"]:
                return self.client.update_chauffeur(chauffeur_data["id"], chauffeur_data)
            else:
                return self.client.create_chauffeur(chauffeur_data)
        except Exception as e:
            print(f"Erreur sauvegarde chauffeur: {e}")
            raise


# Instance globale de l'adaptateur
data_adapter = None


def get_data_adapter() -> DataAdapter:
    """Retourne l'adaptateur de donnees global"""
    global data_adapter
    if data_adapter is None:
        raise RuntimeError("Adaptateur non initialise")
    return data_adapter


# ============================================================================
# CONSTANTES ET UTILITAIRES
# ============================================================================

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


def format_date_display(d: date) -> str:
    """Formate une date pour l'affichage"""
    return d.strftime("%d/%m/%Y")


def parse_date_display(s: str) -> date:
    """Parse une date depuis l'affichage"""
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return date.today()


# ============================================================================
# APPLICATION PRINCIPALE
# ============================================================================

class TransportPlannerClientApp:
    """
    Application principale du client TomatoPlan.
    Interface identique a PTT_v0.6.0.py mais utilisant l'API REST.
    """

    def __init__(self, root, client: TomatoPlanClient):
        self.root = root
        self.client = client
        self.data_adapter = DataAdapter(client)

        # Informations utilisateur
        self.current_user = client.user_info.get("username", "INCONNU")
        self.user_role = client.user_info.get("role", "viewer")
        self.permissions = client.user_info.get("permissions", {})

        self.root.title(f"TomatoPlan Client v0.6.0 - {self.current_user} ({self.user_role})")
        self.root.minsize(1200, 700)
        self.root.geometry("1400x900")
        self.root.resizable(True, True)

        self.status_var = tk.StringVar(value=f"Connecte: {self.current_user} | Serveur: {SERVER_URL}")

        self.current_date = date.today()
        self.missions = []
        self.voyages = []
        self.chauffeurs = []

        self.country_trees = {}
        self.country_frames = {}
        self.sort_criteria = "heure"
        self.sort_reverse = False

        # Charger les donnees initiales
        self._load_initial_data()

        # Construire l'interface
        self.build_gui()

        # Charger le planning du jour
        self.load_planning_for_date(self.current_date)

        # Fermeture propre
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_initial_data(self):
        """Charge les donnees initiales depuis le serveur"""
        try:
            self.voyages = self.data_adapter.get_voyages(active_only=False)
            self.chauffeurs = self.data_adapter.get_chauffeurs(active_only=False)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les donnees: {e}")

    def _on_close(self):
        """Fermeture de l'application"""
        try:
            self.client.logout()
        except Exception:
            pass
        self.root.destroy()

    def has_permission(self, perm: str) -> bool:
        """Verifie si l'utilisateur a une permission"""
        return self.permissions.get(perm, False)

    def build_gui(self):
        """Construit l'interface graphique"""
        # Menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Deconnexion", command=self._logout)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self._on_close)
        menubar.add_cascade(label="Fichier", menu=file_menu)

        # Barre de statut
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side="bottom", fill="x")
        ttk.Label(status_frame, textvariable=self.status_var, anchor="e").pack(side="right", padx=5, pady=2)

        # Indicateur de connexion
        self.connection_indicator = ttk.Label(status_frame, text="En ligne", foreground="green")
        self.connection_indicator.pack(side="left", padx=5)

        # Notebook pour les onglets
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Onglet Planning
        if self.has_permission("view_planning"):
            self.build_planning_tab()

        # Onglet Chauffeurs
        if self.has_permission("view_drivers"):
            self.build_chauffeurs_tab()

        # Onglet Voyages
        if self.has_permission("manage_voyages"):
            self.build_voyages_tab()

    def _logout(self):
        """Deconnexion et retour a l'ecran de login"""
        if messagebox.askyesno("Deconnexion", "Voulez-vous vous deconnecter ?"):
            self.client.logout()
            self.root.destroy()
            # Relancer l'application
            main()

    # ========================================================================
    # ONGLET PLANNING
    # ========================================================================

    def build_planning_tab(self):
        """Construit l'onglet Planning"""
        self.tab_planning = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_planning, text="Planning")

        # Barre de navigation des dates
        top_frame = ttk.Frame(self.tab_planning)
        top_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(top_frame, text="Date :").pack(side="left")
        self.date_var = tk.StringVar(value=format_date_display(self.current_date))
        self.date_entry = ttk.Entry(top_frame, textvariable=self.date_var, width=12)
        self.date_entry.bind('<Return>', lambda e: self.on_load_date())
        self.date_entry.pack(side="left", padx=(5, 15))

        ttk.Button(top_frame, text="<< -2j", command=lambda: self.navigate_days(-2), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="< -1j", command=lambda: self.navigate_days(-1), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Aujourd'hui", command=self.set_today, width=12).pack(side="left", padx=5)
        ttk.Button(top_frame, text="+1j >", command=lambda: self.navigate_days(1), width=8).pack(side="left", padx=2)
        ttk.Button(top_frame, text="+2j >>", command=lambda: self.navigate_days(2), width=8).pack(side="left", padx=(2, 15))

        # Resume
        self.summary_frame = ttk.LabelFrame(self.tab_planning, text="Resume", padding=5)
        self.summary_frame.pack(fill="x", padx=5, pady=3)

        self.summary_label = ttk.Label(self.summary_frame, text="Chargement...")
        self.summary_label.pack(side="left", padx=5)

        # Boutons d'action
        btn_frame = ttk.Frame(self.tab_planning)
        btn_frame.pack(fill="x", padx=5, pady=5)

        if self.has_permission("edit_planning"):
            ttk.Button(btn_frame, text="+ Ajouter", command=self.on_add_mission).pack(side="left")
            ttk.Button(btn_frame, text="Modifier", command=self.on_edit_mission).pack(side="left", padx=5)
            ttk.Button(btn_frame, text="Supprimer", command=self.on_delete_mission).pack(side="left", padx=5)

        ttk.Button(btn_frame, text="Rafraichir", command=self.refresh_planning_view).pack(side="right")

        # Zone des missions par pays
        self.countries_canvas = tk.Canvas(self.tab_planning)
        scrollbar = ttk.Scrollbar(self.tab_planning, orient="vertical", command=self.countries_canvas.yview)
        self.countries_frame = ttk.Frame(self.countries_canvas)

        self.countries_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.countries_canvas.pack(side="left", fill="both", expand=True)

        self.canvas_frame = self.countries_canvas.create_window((0, 0), window=self.countries_frame, anchor="nw")

        self.countries_frame.bind("<Configure>", lambda e: self.countries_canvas.configure(scrollregion=self.countries_canvas.bbox("all")))
        self.countries_canvas.bind("<Configure>", lambda e: self.countries_canvas.itemconfig(self.canvas_frame, width=e.width))

    def navigate_days(self, delta: int):
        """Navigation dans les dates"""
        self.current_date += timedelta(days=delta)
        self.date_var.set(format_date_display(self.current_date))
        self.load_planning_for_date(self.current_date)

    def set_today(self):
        """Retourne a la date du jour"""
        self.current_date = date.today()
        self.date_var.set(format_date_display(self.current_date))
        self.load_planning_for_date(self.current_date)

    def on_load_date(self):
        """Charge une date saisie manuellement"""
        try:
            self.current_date = parse_date_display(self.date_var.get())
            self.load_planning_for_date(self.current_date)
        except Exception:
            messagebox.showerror("Erreur", "Format de date invalide (JJ/MM/AAAA)")

    def load_planning_for_date(self, d: date):
        """Charge le planning d'une date"""
        self.status_var.set(f"Chargement du planning {format_date_display(d)}...")
        self.root.update()

        try:
            self.missions = self.data_adapter.get_missions_for_date(d)
            self.refresh_planning_view()
            self.update_summary()
            self.status_var.set(f"Connecte: {self.current_user} | {len(self.missions)} missions")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger le planning: {e}")
            self.status_var.set(f"Erreur de chargement")

    def refresh_planning_view(self):
        """Rafraichit l'affichage du planning"""
        # Effacer les frames existants
        for widget in self.countries_frame.winfo_children():
            widget.destroy()

        self.country_trees = {}
        self.country_frames = {}

        # Grouper les missions par pays
        missions_by_country = {}
        for mission in self.missions:
            country = mission.get("country", "Belgique")
            if country not in missions_by_country:
                missions_by_country[country] = []
            missions_by_country[country].append(mission)

        # Creer une frame pour chaque pays
        for country in EU_COUNTRIES:
            if country in missions_by_country or country == "Belgique":
                self._create_country_frame(country, missions_by_country.get(country, []))

    def _create_country_frame(self, country: str, missions: list):
        """Cree une frame pour un pays"""
        frame = ttk.LabelFrame(self.countries_frame, text=f"{country} ({len(missions)} missions)", padding=5)
        frame.pack(fill="x", padx=5, pady=5)

        self.country_frames[country] = frame

        # Treeview pour les missions
        columns = ("heure", "voyage", "chauffeur", "tracteur", "remorque", "statut", "palettes", "commentaire")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=min(len(missions) + 1, 10))

        tree.heading("heure", text="Heure")
        tree.heading("voyage", text="Voyage")
        tree.heading("chauffeur", text="Chauffeur")
        tree.heading("tracteur", text="Tracteur")
        tree.heading("remorque", text="Remorque")
        tree.heading("statut", text="Statut")
        tree.heading("palettes", text="Pal.")
        tree.heading("commentaire", text="Commentaire")

        tree.column("heure", width=60)
        tree.column("voyage", width=100)
        tree.column("chauffeur", width=120)
        tree.column("tracteur", width=80)
        tree.column("remorque", width=80)
        tree.column("statut", width=80)
        tree.column("palettes", width=50)
        tree.column("commentaire", width=200)

        # Ajouter les missions
        for mission in sorted(missions, key=lambda m: m.get("heure_depart", "00:00")):
            tree.insert("", "end", iid=str(mission.get("id", uuid.uuid4())), values=(
                mission.get("heure_depart", ""),
                mission.get("voyage_code", ""),
                mission.get("chauffeur_nom", ""),
                mission.get("tracteur", ""),
                mission.get("remorque", ""),
                mission.get("statut", ""),
                mission.get("palettes", ""),
                mission.get("commentaire", "")
            ))

        tree.pack(fill="x", expand=True)

        # Double-clic pour editer
        tree.bind("<Double-1>", lambda e: self.on_edit_mission())

        self.country_trees[country] = tree

    def update_summary(self):
        """Met a jour le resume"""
        total = len(self.missions)
        livraisons = sum(1 for m in self.missions if m.get("type_mission") == "LIVRAISON")
        ramasses = sum(1 for m in self.missions if m.get("type_mission") == "RAMASSE")
        palettes = sum(int(m.get("palettes", 0) or 0) for m in self.missions)

        self.summary_label.config(
            text=f"Total: {total} | Livraisons: {livraisons} | Ramasses: {ramasses} | Palettes: {palettes}"
        )

    def get_selected_mission(self):
        """Retourne la mission selectionnee"""
        for country, tree in self.country_trees.items():
            selection = tree.selection()
            if selection:
                mission_id = selection[0]
                for mission in self.missions:
                    if str(mission.get("id")) == mission_id:
                        return mission
        return None

    def on_add_mission(self):
        """Ajouter une nouvelle mission"""
        dialog = MissionDialog(self.root, self.voyages, self.chauffeurs, self.current_date)
        if dialog.result:
            try:
                mission_data = dialog.result
                mission_data["date_mission"] = self.current_date.isoformat()
                self.data_adapter.save_mission(mission_data)
                self.load_planning_for_date(self.current_date)
                messagebox.showinfo("Succes", "Mission ajoutee")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ajouter la mission: {e}")

    def on_edit_mission(self):
        """Modifier une mission"""
        mission = self.get_selected_mission()
        if not mission:
            messagebox.showwarning("Attention", "Selectionnez une mission a modifier")
            return

        dialog = MissionDialog(self.root, self.voyages, self.chauffeurs, self.current_date, mission)
        if dialog.result:
            try:
                mission_data = dialog.result
                mission_data["id"] = mission.get("id")
                self.data_adapter.save_mission(mission_data)
                self.load_planning_for_date(self.current_date)
                messagebox.showinfo("Succes", "Mission modifiee")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de modifier la mission: {e}")

    def on_delete_mission(self):
        """Supprimer une mission"""
        mission = self.get_selected_mission()
        if not mission:
            messagebox.showwarning("Attention", "Selectionnez une mission a supprimer")
            return

        if messagebox.askyesno("Confirmation", "Supprimer cette mission ?"):
            try:
                self.data_adapter.delete_mission(mission.get("id"))
                self.load_planning_for_date(self.current_date)
                messagebox.showinfo("Succes", "Mission supprimee")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible de supprimer la mission: {e}")

    # ========================================================================
    # ONGLET CHAUFFEURS
    # ========================================================================

    def build_chauffeurs_tab(self):
        """Construit l'onglet Chauffeurs"""
        self.tab_chauffeurs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chauffeurs, text="Chauffeurs")

        # Boutons
        btn_frame = ttk.Frame(self.tab_chauffeurs)
        btn_frame.pack(fill="x", padx=5, pady=5)

        if self.has_permission("manage_drivers"):
            ttk.Button(btn_frame, text="+ Ajouter", command=self.on_add_chauffeur).pack(side="left")
            ttk.Button(btn_frame, text="Modifier", command=self.on_edit_chauffeur).pack(side="left", padx=5)

        ttk.Button(btn_frame, text="Rafraichir", command=self.refresh_chauffeurs_view).pack(side="right")

        # Treeview
        columns = ("code", "nom", "prenom", "type", "actif")
        self.chauffeurs_tree = ttk.Treeview(self.tab_chauffeurs, columns=columns, show="headings")

        self.chauffeurs_tree.heading("code", text="Code")
        self.chauffeurs_tree.heading("nom", text="Nom")
        self.chauffeurs_tree.heading("prenom", text="Prenom")
        self.chauffeurs_tree.heading("type", text="Type")
        self.chauffeurs_tree.heading("actif", text="Actif")

        self.chauffeurs_tree.pack(fill="both", expand=True, padx=5, pady=5)

        self.refresh_chauffeurs_view()

    def refresh_chauffeurs_view(self):
        """Rafraichit la liste des chauffeurs"""
        self.chauffeurs_tree.delete(*self.chauffeurs_tree.get_children())

        try:
            self.chauffeurs = self.data_adapter.get_chauffeurs(active_only=False)
            for ch in self.chauffeurs:
                self.chauffeurs_tree.insert("", "end", iid=str(ch.get("id")), values=(
                    ch.get("code", ""),
                    ch.get("nom", ""),
                    ch.get("prenom", ""),
                    ch.get("type", ""),
                    "Oui" if ch.get("actif", True) else "Non"
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les chauffeurs: {e}")

    def on_add_chauffeur(self):
        """Ajouter un chauffeur"""
        dialog = ChauffeurDialog(self.root)
        if dialog.result:
            try:
                self.data_adapter.save_chauffeur(dialog.result)
                self.refresh_chauffeurs_view()
                messagebox.showinfo("Succes", "Chauffeur ajoute")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ajouter le chauffeur: {e}")

    def on_edit_chauffeur(self):
        """Modifier un chauffeur"""
        selection = self.chauffeurs_tree.selection()
        if not selection:
            messagebox.showwarning("Attention", "Selectionnez un chauffeur")
            return

        chauffeur_id = selection[0]
        chauffeur = next((c for c in self.chauffeurs if str(c.get("id")) == chauffeur_id), None)

        if chauffeur:
            dialog = ChauffeurDialog(self.root, chauffeur)
            if dialog.result:
                try:
                    dialog.result["id"] = chauffeur.get("id")
                    self.data_adapter.save_chauffeur(dialog.result)
                    self.refresh_chauffeurs_view()
                    messagebox.showinfo("Succes", "Chauffeur modifie")
                except Exception as e:
                    messagebox.showerror("Erreur", f"Impossible de modifier le chauffeur: {e}")

    # ========================================================================
    # ONGLET VOYAGES
    # ========================================================================

    def build_voyages_tab(self):
        """Construit l'onglet Voyages"""
        self.tab_voyages = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_voyages, text="Voyages")

        # Boutons
        btn_frame = ttk.Frame(self.tab_voyages)
        btn_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(btn_frame, text="+ Ajouter", command=self.on_add_voyage).pack(side="left")
        ttk.Button(btn_frame, text="Modifier", command=self.on_edit_voyage).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Rafraichir", command=self.refresh_voyages_view).pack(side="right")

        # Treeview
        columns = ("code", "type", "pays", "duree", "actif")
        self.voyages_tree = ttk.Treeview(self.tab_voyages, columns=columns, show="headings")

        self.voyages_tree.heading("code", text="Code")
        self.voyages_tree.heading("type", text="Type")
        self.voyages_tree.heading("pays", text="Pays")
        self.voyages_tree.heading("duree", text="Duree (min)")
        self.voyages_tree.heading("actif", text="Actif")

        self.voyages_tree.pack(fill="both", expand=True, padx=5, pady=5)

        self.refresh_voyages_view()

    def refresh_voyages_view(self):
        """Rafraichit la liste des voyages"""
        self.voyages_tree.delete(*self.voyages_tree.get_children())

        try:
            self.voyages = self.data_adapter.get_voyages(active_only=False)
            for v in self.voyages:
                self.voyages_tree.insert("", "end", iid=str(v.get("id")), values=(
                    v.get("code", ""),
                    v.get("type", ""),
                    v.get("country", ""),
                    v.get("duree", ""),
                    "Oui" if v.get("actif", True) else "Non"
                ))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les voyages: {e}")

    def on_add_voyage(self):
        """Ajouter un voyage"""
        dialog = VoyageDialog(self.root)
        if dialog.result:
            try:
                self.data_adapter.save_voyage(dialog.result)
                self.refresh_voyages_view()
                messagebox.showinfo("Succes", "Voyage ajoute")
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ajouter le voyage: {e}")

    def on_edit_voyage(self):
        """Modifier un voyage"""
        selection = self.voyages_tree.selection()
        if not selection:
            messagebox.showwarning("Attention", "Selectionnez un voyage")
            return

        voyage_id = selection[0]
        voyage = next((v for v in self.voyages if str(v.get("id")) == voyage_id), None)

        if voyage:
            dialog = VoyageDialog(self.root, voyage)
            if dialog.result:
                try:
                    dialog.result["id"] = voyage.get("id")
                    self.data_adapter.save_voyage(dialog.result)
                    self.refresh_voyages_view()
                    messagebox.showinfo("Succes", "Voyage modifie")
                except Exception as e:
                    messagebox.showerror("Erreur", f"Impossible de modifier le voyage: {e}")


# ============================================================================
# DIALOGUES
# ============================================================================

class MissionDialog:
    """Dialogue pour ajouter/modifier une mission"""

    def __init__(self, parent, voyages: list, chauffeurs: list, mission_date: date, mission: dict = None):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Mission" if mission else "Nouvelle Mission")
        self.dialog.geometry("500x450")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Formulaire
        form = ttk.Frame(self.dialog, padding=15)
        form.pack(fill="both", expand=True)

        row = 0

        # Heure
        ttk.Label(form, text="Heure depart:").grid(row=row, column=0, sticky="w", pady=5)
        self.heure_var = tk.StringVar(value=mission.get("heure_depart", "06:00") if mission else "06:00")
        ttk.Entry(form, textvariable=self.heure_var, width=10).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Voyage
        ttk.Label(form, text="Voyage:").grid(row=row, column=0, sticky="w", pady=5)
        voyage_codes = [v.get("code", "") for v in voyages if v.get("actif", True)]
        self.voyage_var = tk.StringVar(value=mission.get("voyage_code", "") if mission else "")
        ttk.Combobox(form, textvariable=self.voyage_var, values=voyage_codes, width=20).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Chauffeur
        ttk.Label(form, text="Chauffeur:").grid(row=row, column=0, sticky="w", pady=5)
        chauffeur_noms = [f"{c.get('nom', '')} {c.get('prenom', '')}" for c in chauffeurs if c.get("actif", True)]
        self.chauffeur_var = tk.StringVar(value=mission.get("chauffeur_nom", "") if mission else "")
        ttk.Combobox(form, textvariable=self.chauffeur_var, values=chauffeur_noms, width=25).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Tracteur
        ttk.Label(form, text="Tracteur:").grid(row=row, column=0, sticky="w", pady=5)
        self.tracteur_var = tk.StringVar(value=mission.get("tracteur", "") if mission else "")
        ttk.Entry(form, textvariable=self.tracteur_var, width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Remorque
        ttk.Label(form, text="Remorque:").grid(row=row, column=0, sticky="w", pady=5)
        self.remorque_var = tk.StringVar(value=mission.get("remorque", "") if mission else "")
        ttk.Entry(form, textvariable=self.remorque_var, width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Palettes
        ttk.Label(form, text="Palettes:").grid(row=row, column=0, sticky="w", pady=5)
        self.palettes_var = tk.StringVar(value=str(mission.get("palettes", "")) if mission else "")
        ttk.Entry(form, textvariable=self.palettes_var, width=10).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Statut
        ttk.Label(form, text="Statut:").grid(row=row, column=0, sticky="w", pady=5)
        self.statut_var = tk.StringVar(value=mission.get("statut", "PLANIFIE") if mission else "PLANIFIE")
        ttk.Combobox(form, textvariable=self.statut_var, values=["PLANIFIE", "EN_COURS", "TERMINE", "ANNULE"], width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Commentaire
        ttk.Label(form, text="Commentaire:").grid(row=row, column=0, sticky="w", pady=5)
        self.commentaire_var = tk.StringVar(value=mission.get("commentaire", "") if mission else "")
        ttk.Entry(form, textvariable=self.commentaire_var, width=40).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Boutons
        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Enregistrer", command=self._save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Annuler", command=self.dialog.destroy).pack(side="left", padx=5)

        self.dialog.wait_window()

    def _save(self):
        self.result = {
            "heure_depart": self.heure_var.get(),
            "voyage_code": self.voyage_var.get(),
            "chauffeur_nom": self.chauffeur_var.get(),
            "tracteur": self.tracteur_var.get(),
            "remorque": self.remorque_var.get(),
            "palettes": int(self.palettes_var.get() or 0),
            "statut": self.statut_var.get(),
            "commentaire": self.commentaire_var.get()
        }
        self.dialog.destroy()


class ChauffeurDialog:
    """Dialogue pour ajouter/modifier un chauffeur"""

    def __init__(self, parent, chauffeur: dict = None):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Chauffeur" if chauffeur else "Nouveau Chauffeur")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        form = ttk.Frame(self.dialog, padding=15)
        form.pack(fill="both", expand=True)

        row = 0

        # Code
        ttk.Label(form, text="Code:").grid(row=row, column=0, sticky="w", pady=5)
        self.code_var = tk.StringVar(value=chauffeur.get("code", "") if chauffeur else "")
        ttk.Entry(form, textvariable=self.code_var, width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Nom
        ttk.Label(form, text="Nom:").grid(row=row, column=0, sticky="w", pady=5)
        self.nom_var = tk.StringVar(value=chauffeur.get("nom", "") if chauffeur else "")
        ttk.Entry(form, textvariable=self.nom_var, width=25).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Prenom
        ttk.Label(form, text="Prenom:").grid(row=row, column=0, sticky="w", pady=5)
        self.prenom_var = tk.StringVar(value=chauffeur.get("prenom", "") if chauffeur else "")
        ttk.Entry(form, textvariable=self.prenom_var, width=25).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Type
        ttk.Label(form, text="Type:").grid(row=row, column=0, sticky="w", pady=5)
        self.type_var = tk.StringVar(value=chauffeur.get("type", "INTERNE") if chauffeur else "INTERNE")
        ttk.Combobox(form, textvariable=self.type_var, values=["INTERNE", "SST"], width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Actif
        self.actif_var = tk.BooleanVar(value=chauffeur.get("actif", True) if chauffeur else True)
        ttk.Checkbutton(form, text="Actif", variable=self.actif_var).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Boutons
        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Enregistrer", command=self._save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Annuler", command=self.dialog.destroy).pack(side="left", padx=5)

        self.dialog.wait_window()

    def _save(self):
        self.result = {
            "code": self.code_var.get(),
            "nom": self.nom_var.get(),
            "prenom": self.prenom_var.get(),
            "type": self.type_var.get(),
            "actif": self.actif_var.get()
        }
        self.dialog.destroy()


class VoyageDialog:
    """Dialogue pour ajouter/modifier un voyage"""

    def __init__(self, parent, voyage: dict = None):
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Voyage" if voyage else "Nouveau Voyage")
        self.dialog.geometry("400x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        form = ttk.Frame(self.dialog, padding=15)
        form.pack(fill="both", expand=True)

        row = 0

        # Code
        ttk.Label(form, text="Code:").grid(row=row, column=0, sticky="w", pady=5)
        self.code_var = tk.StringVar(value=voyage.get("code", "") if voyage else "")
        ttk.Entry(form, textvariable=self.code_var, width=20).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Type
        ttk.Label(form, text="Type:").grid(row=row, column=0, sticky="w", pady=5)
        self.type_var = tk.StringVar(value=voyage.get("type", "LIVRAISON") if voyage else "LIVRAISON")
        ttk.Combobox(form, textvariable=self.type_var, values=["LIVRAISON", "RAMASSE"], width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Pays
        ttk.Label(form, text="Pays:").grid(row=row, column=0, sticky="w", pady=5)
        self.pays_var = tk.StringVar(value=voyage.get("country", "Belgique") if voyage else "Belgique")
        ttk.Combobox(form, textvariable=self.pays_var, values=EU_COUNTRIES, width=15).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Duree
        ttk.Label(form, text="Duree (min):").grid(row=row, column=0, sticky="w", pady=5)
        self.duree_var = tk.StringVar(value=str(voyage.get("duree", 60)) if voyage else "60")
        ttk.Entry(form, textvariable=self.duree_var, width=10).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Actif
        self.actif_var = tk.BooleanVar(value=voyage.get("actif", True) if voyage else True)
        ttk.Checkbutton(form, text="Actif", variable=self.actif_var).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # Boutons
        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Enregistrer", command=self._save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Annuler", command=self.dialog.destroy).pack(side="left", padx=5)

        self.dialog.wait_window()

    def _save(self):
        self.result = {
            "code": self.code_var.get(),
            "type": self.type_var.get(),
            "country": self.pays_var.get(),
            "duree": int(self.duree_var.get() or 60),
            "actif": self.actif_var.get()
        }
        self.dialog.destroy()


# ============================================================================
# POINT D'ENTREE
# ============================================================================

def main():
    """Point d'entree principal"""
    global api_client, data_adapter

    # Afficher la fenetre de connexion
    login = LoginWindow(SERVER_URL, verify_ssl=VERIFY_SSL)
    client = login.run()

    if client is None:
        print("Connexion annulee")
        return

    # Stocker le client globalement
    api_client = client
    data_adapter = DataAdapter(client)

    # Lancer l'application principale
    root = tk.Tk()
    app = TransportPlannerClientApp(root, client)
    root.mainloop()


if __name__ == "__main__":
    main()
