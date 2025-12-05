"""
Guide de migration PTT_v0.6 vers Client API

Ce fichier montre comment adapter le code existant de PTT_v0.6.py
pour utiliser l'API REST au lieu des fichiers JSON locaux.
"""

# ============================================================
# AVANT (PTT_v0.6.py - Lecture/Écriture fichiers JSON)
# ============================================================

# Ancien code - Lecture des missions depuis un fichier JSON
"""
def load_missions_for_date(d: date) -> list:
    day_dir = get_planning_day_dir(d)
    missions_file = day_dir / "missions.json"
    return load_json(missions_file, default=[])

def save_missions_for_date(d: date, missions: list):
    day_dir = get_planning_day_dir(d)
    day_dir.mkdir(parents=True, exist_ok=True)
    save_json(day_dir / "missions.json", missions)
"""


# ============================================================
# APRÈS (Nouveau code - Utilisation de l'API)
# ============================================================

from api_client import TomatoPlanClient, init_client, get_client
from datetime import date


# Initialisation au démarrage de l'application
def setup_api_connection(server_url: str = "http://localhost:8000"):
    """
    À appeler au démarrage de l'application.
    Configure la connexion au serveur et authentifie l'utilisateur.
    """
    client = init_client(server_url)
    return client


# Nouvelle version - Lecture des missions via l'API
def load_missions_for_date(d: date) -> list:
    """
    Charge les missions d'une date depuis l'API.

    Args:
        d: Date des missions à charger

    Returns:
        Liste des missions
    """
    client = get_client()
    date_str = d.strftime("%Y-%m-%d")
    return client.get_missions_by_date(date_str)


# Nouvelle version - Sauvegarde des missions via l'API
def save_mission(mission_data: dict) -> dict:
    """
    Sauvegarde une mission via l'API.

    Args:
        mission_data: Données de la mission

    Returns:
        Mission créée/mise à jour
    """
    client = get_client()

    if "id" in mission_data and mission_data["id"]:
        # Mise à jour d'une mission existante
        mission_id = mission_data.pop("id")
        return client.update_mission(mission_id, mission_data)
    else:
        # Création d'une nouvelle mission
        return client.create_mission(mission_data)


# ============================================================
# EXEMPLE D'ADAPTATION DE LA CLASSE TransportPlannerApp
# ============================================================

class TransportPlannerAppMigrated:
    """
    Exemple de migration de la classe principale.

    Modifications principales:
    1. Remplacer les appels load_json/save_json par des appels API
    2. Ajouter la gestion de connexion au démarrage
    3. Gérer les erreurs réseau
    """

    def __init__(self, server_url: str = "http://localhost:8000"):
        # Connexion au serveur
        self.client = TomatoPlanClient(server_url)

        # Vérifier la connexion
        server_status = self.client.check_server()
        if server_status.get("status") != "healthy":
            raise ConnectionError("Serveur inaccessible")

        # Authentification automatique avec l'utilisateur Windows
        if not self.client.login():
            raise PermissionError("Authentification refusée")

        # Stocker les infos utilisateur
        self.current_user = self.client.user_info
        self.permissions = self.current_user.get("permissions", {})

    # -------- Méthodes adaptées --------

    def load_voyages(self) -> list:
        """Charge la liste des voyages"""
        try:
            return self.client.get_voyages(active_only=True)
        except ConnectionError:
            # Fallback: utiliser le cache local si disponible
            return self._load_from_cache("voyages", [])

    def load_chauffeurs(self) -> list:
        """Charge la liste des chauffeurs"""
        try:
            return self.client.get_chauffeurs(active_only=True)
        except ConnectionError:
            return self._load_from_cache("chauffeurs", [])

    def load_missions(self, d: date) -> list:
        """Charge les missions d'une date"""
        try:
            missions = self.client.get_missions_by_date(d.strftime("%Y-%m-%d"))
            # Mettre en cache pour utilisation hors-ligne
            self._save_to_cache(f"missions_{d}", missions)
            return missions
        except ConnectionError:
            return self._load_from_cache(f"missions_{d}", [])

    def create_mission(self, mission_data: dict) -> dict:
        """Crée une nouvelle mission"""
        # Vérifier les permissions
        if not self.permissions.get("edit_planning"):
            raise PermissionError("Permission 'edit_planning' requise")

        return self.client.create_mission(mission_data)

    def update_mission(self, mission_id: int, mission_data: dict) -> dict:
        """Met à jour une mission"""
        if not self.permissions.get("edit_planning"):
            raise PermissionError("Permission 'edit_planning' requise")

        return self.client.update_mission(mission_id, mission_data)

    def delete_mission(self, mission_id: int) -> bool:
        """Supprime une mission"""
        if not self.permissions.get("edit_planning"):
            raise PermissionError("Permission 'edit_planning' requise")

        return self.client.delete_mission(mission_id)

    def get_chauffeurs_disponibles(self, d: date) -> dict:
        """Récupère les chauffeurs disponibles pour une date"""
        return self.client.get_chauffeurs_disponibles(d.strftime("%Y-%m-%d"))

    # -------- Gestion du cache local (optionnel) --------

    def _load_from_cache(self, key: str, default):
        """Charge des données depuis le cache local"""
        import json
        from pathlib import Path

        cache_file = Path.home() / ".tomatoplan_cache" / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def _save_to_cache(self, key: str, data):
        """Sauvegarde des données dans le cache local"""
        import json
        from pathlib import Path

        cache_dir = Path.home() / ".tomatoplan_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception:
            pass

    # -------- Gestion de la fermeture --------

    def on_close(self):
        """À appeler lors de la fermeture de l'application"""
        if self.client:
            self.client.logout()


# ============================================================
# EXEMPLE D'UTILISATION
# ============================================================

if __name__ == "__main__":
    print("=== Test de migration ===\n")

    try:
        # Créer l'application migrée
        app = TransportPlannerAppMigrated("http://localhost:8000")

        print(f"Connecté en tant que: {app.current_user.get('username')}")
        print(f"Rôle: {app.current_user.get('role')}")
        print()

        # Charger les données
        voyages = app.load_voyages()
        print(f"Voyages chargés: {len(voyages)}")

        chauffeurs = app.load_chauffeurs()
        print(f"Chauffeurs chargés: {len(chauffeurs)}")

        from datetime import date
        today = date.today()
        missions = app.load_missions(today)
        print(f"Missions du {today}: {len(missions)}")

        # Test des chauffeurs disponibles
        dispo = app.get_chauffeurs_disponibles(today)
        print(f"Chauffeurs disponibles: {len(dispo.get('disponibles', []))}")

        # Test de création de mission (si permission)
        if app.permissions.get("edit_planning"):
            print("\nTest de création de mission...")
            # new_mission = app.create_mission({
            #     "date_mission": today.isoformat(),
            #     "destination": "Test API",
            #     "statut": "planifie"
            # })
            # print(f"Mission créée: ID={new_mission.get('id')}")

        # Fermeture propre
        app.on_close()
        print("\nDéconnecté.")

    except ConnectionError as e:
        print(f"Erreur de connexion: {e}")
    except PermissionError as e:
        print(f"Erreur de permission: {e}")
    except Exception as e:
        print(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
