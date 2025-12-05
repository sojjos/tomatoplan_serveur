#!/usr/bin/env python3
"""
PTT Client Complet - Version Client-Serveur
============================================

Ce script lance l'application PTT_v0.6.0.py complete mais connectee
au serveur TomatoPlan via API REST.

L'interface est 100% identique a l'original, seul le stockage des
donnees passe par le serveur au lieu des fichiers JSON locaux.

Usage:
    python PTT_Client_Full.py

Configuration:
    Modifiez SERVER_URL dans api_adapter.py pour pointer vers votre serveur.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from pathlib import Path

# Ajouter le dossier client au path
CLIENT_DIR = Path(__file__).parent
sys.path.insert(0, str(CLIENT_DIR))

# Importer l'adaptateur API
from api_adapter import (
    api_client,
    api_load_json,
    api_save_json,
    api_list_existing_dates,
    api_get_planning_for_date,
    ActivityLoggerAPI,
    get_current_user,
    get_user_permissions,
    SERVER_URL,
    VERIFY_SSL,
    connection_monitor,
    is_online,
    get_connection_status,
)


# ============================================================================
# FENETRE DE CONNEXION
# ============================================================================

class LoginWindow:
    """Fenetre de connexion au serveur TomatoPlan"""

    def __init__(self):
        self.authenticated = False
        self.root = tk.Tk()
        self.root.title("TomatoPlan - Connexion")
        self.root.geometry("420x380")
        self.root.resizable(False, False)

        # Centrer
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - 210
        y = (self.root.winfo_screenheight() // 2) - 190
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self._check_server()

    def _build_ui(self):
        # Logo/Titre
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=20)

        ttk.Label(title_frame, text="TomatoPlan", font=("Arial", 28, "bold")).pack()
        ttk.Label(title_frame, text="Planning Transport Tubize", font=("Arial", 11)).pack()
        ttk.Label(title_frame, text="v0.6.0 - Mode Client-Serveur", font=("Arial", 9), foreground="gray").pack()

        # Status serveur
        status_frame = ttk.Frame(self.root)
        status_frame.pack(pady=10)

        self.status_label = ttk.Label(status_frame, text="Verification du serveur...", foreground="orange")
        self.status_label.pack()

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
        self.error_label = ttk.Label(self.root, textvariable=self.error_var, foreground="red", wraplength=380)
        self.error_label.pack(pady=5)

        # Info serveur
        ttk.Label(self.root, text=f"Serveur: {SERVER_URL}", font=("Arial", 8), foreground="gray").pack(side="bottom", pady=5)

        self.password_entry.focus()

    def _check_server(self):
        """Verification du serveur en arriere-plan"""
        def check():
            try:
                status = api_client.check_server()
                if status.get("status") == "ok":
                    self.root.after(0, lambda: self._update_status(True, "Serveur connecte"))
                else:
                    self.root.after(0, lambda: self._update_status(False, f"Serveur indisponible: {status.get('message', '')}"))
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
            except ConnectionError as e:
                self.root.after(0, lambda: self._on_error(f"Connexion impossible"))
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
# PATCH DES FONCTIONS PTT
# ============================================================================

def patch_ptt_module():
    """
    Patche le module PTT pour utiliser l'API.
    Cette fonction modifie les fonctions globales de PTT_v0.6.0.py.
    """
    # Le chemin vers PTT_v0.6.0.py (dans le dossier parent)
    ptt_path = CLIENT_DIR.parent / "PTT_v0.6.0.py"

    if not ptt_path.exists():
        raise FileNotFoundError(f"PTT_v0.6.0.py non trouve: {ptt_path}")

    # Lire le code source
    with open(ptt_path, "r", encoding="utf-8") as f:
        ptt_source = f.read()

    # Creer un module compile
    import types
    ptt_module = types.ModuleType("ptt_patched")
    ptt_module.__file__ = str(ptt_path)

    # Ajouter nos fonctions de remplacement au namespace AVANT l'execution
    ptt_module.load_json = api_load_json
    ptt_module.save_json = api_save_json
    ptt_module.list_existing_dates = api_list_existing_dates

    # Remplacer ActivityLogger
    ptt_module.ActivityLogger = ActivityLoggerAPI
    ptt_module.activity_logger = ActivityLoggerAPI()

    # Executer le code PTT dans le namespace du module
    # On modifie le source pour remplacer les fonctions
    patched_source = ptt_source

    # Remplacer les definitions de fonctions
    patched_source = patched_source.replace(
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

    # Ajouter nos imports et fonctions au debut
    header = '''
# ===== PATCHED FOR CLIENT-SERVER MODE =====
import sys as _sys
_client_dir = _sys.path[0] if _sys.path else "."
if _client_dir not in _sys.path:
    _sys.path.insert(0, _client_dir)

from api_adapter import (
    api_load_json as load_json,
    api_save_json as save_json,
    api_list_existing_dates as list_existing_dates,
    api_get_planning_for_date,
    ActivityLoggerAPI,
    get_current_user as _api_get_current_user,
    get_user_permissions as _api_get_permissions,
    api_client as _api_client,
    connection_monitor as _connection_monitor,
    is_online as _is_online,
    get_connection_status as _get_connection_status,
)

# Remplacer ActivityLogger
class ActivityLogger(ActivityLoggerAPI):
    pass

activity_logger = ActivityLogger()

# Variable globale pour stocker la reference a l'app principale
_ptt_app_instance = None

# ===== LIVE STATUS INDICATOR =====

def _update_live_status(app):
    """Met a jour l'indicateur de statut en ligne/hors ligne"""
    if not hasattr(app, 'status_var') or not hasattr(app, 'root'):
        return

    try:
        is_live = _is_online()
        status_text = "En ligne" if is_live else "Hors ligne"
        status_indicator = "●" if is_live else "○"
        color_hint = "(live)" if is_live else "(deconnecte)"

        app.status_var.set(
            f"Session : {app.current_user} | {status_indicator} {status_text}"
        )

        # Mettre a jour la couleur de la barre de statut si possible
        if hasattr(app, 'status_label'):
            fg_color = "green" if is_live else "red"
            try:
                app.status_label.config(foreground=fg_color)
            except Exception:
                pass

    except Exception as e:
        pass

def _start_live_status_monitor(app):
    """Demarre le moniteur de statut en direct"""
    global _ptt_app_instance
    _ptt_app_instance = app

    # Demarrer le moniteur de connexion
    _connection_monitor.start()

    # Fonction de mise a jour periodique
    def update_loop():
        if _ptt_app_instance and hasattr(_ptt_app_instance, 'root'):
            _update_live_status(_ptt_app_instance)
            try:
                _ptt_app_instance.root.after(5000, update_loop)  # Toutes les 5 secondes
            except Exception:
                pass

    # Premiere mise a jour
    _update_live_status(app)

    # Demarrer la boucle de mise a jour
    try:
        app.root.after(5000, update_loop)
    except Exception:
        pass

# ===== END PATCH =====

'''

    # Patcher la methode update_status_bar_initial pour utiliser le statut live
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
        """Initialise la barre de statut au demarrage avec statut live."""
        # Mode client-serveur: utiliser le statut de connexion
        _start_live_status_monitor(self)'''
    )

    patched_source = header + patched_source

    return ptt_path, patched_source


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Point d'entree principal"""

    # Afficher la fenetre de login
    print("TomatoPlan Client - Connexion au serveur...")
    login = LoginWindow()

    if not login.run():
        print("Connexion annulee ou echouee")
        return

    print(f"Connecte en tant que: {get_current_user()}")
    print("Chargement de l'application...")

    # Patcher et lancer PTT
    try:
        ptt_path, patched_source = patch_ptt_module()

        # Preparer l'environnement
        import builtins
        original_input = builtins.input

        # Compiler et executer
        code = compile(patched_source, str(ptt_path), "exec")

        # Creer le namespace d'execution
        exec_globals = {
            "__name__": "__main__",
            "__file__": str(ptt_path),
            "__builtins__": builtins,
        }

        # Ajouter le dossier client au path pour les imports
        if str(CLIENT_DIR) not in sys.path:
            sys.path.insert(0, str(CLIENT_DIR))

        # Changer le repertoire de travail vers le dossier PTT
        os.chdir(ptt_path.parent)

        # Executer PTT
        exec(code, exec_globals)

    except FileNotFoundError as e:
        messagebox.showerror("Erreur", str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("Erreur", f"Erreur au lancement: {e}")
    finally:
        # Arreter le moniteur de connexion
        try:
            connection_monitor.stop()
        except Exception:
            pass
        # Deconnexion
        try:
            api_client.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()
