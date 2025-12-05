"""
TomatoPlan API Client
Module client pour communiquer avec le serveur TomatoPlan.

Ce module remplace les fonctions load_json/save_json de l'application originale
pour utiliser l'API REST au lieu des fichiers JSON locaux.

Usage:
    from api_client import TomatoPlanClient

    client = TomatoPlanClient("http://192.168.1.100:8000")
    client.login()  # Utilise automatiquement le nom d'utilisateur Windows

    # Récupérer les missions d'une date
    missions = client.get_missions_by_date("2024-01-15")

    # Créer une mission
    new_mission = client.create_mission({
        "date_mission": "2024-01-15",
        "destination": "Paris",
        "chauffeur_id": 1,
        ...
    })
"""

import os
import getpass
import socket
import requests
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import json


class TomatoPlanClient:
    """Client pour l'API TomatoPlan"""

    def __init__(self, server_url: str, timeout: int = 30):
        """
        Initialise le client API.

        Args:
            server_url: URL du serveur (ex: "http://192.168.1.100:8000")
            timeout: Timeout des requêtes en secondes
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None
        self._session = requests.Session()

        # Chemins pour le cache local (optionnel)
        self._cache_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "TomatoPlan" / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_windows_username(self) -> str:
        """Récupère le nom d'utilisateur Windows"""
        # Essayer différentes méthodes
        username = os.environ.get("USERNAME")
        if not username:
            username = getpass.getuser()
        return username.upper()

    def _get_hostname(self) -> str:
        """Récupère le nom de la machine"""
        return socket.gethostname()

    def _headers(self) -> Dict[str, str]:
        """Retourne les headers avec le token d'authentification"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Effectue une requête HTTP vers l'API.

        Args:
            method: Méthode HTTP (GET, POST, PUT, DELETE)
            endpoint: Chemin de l'endpoint (ex: "/missions")
            data: Données à envoyer (pour POST/PUT)
            params: Paramètres de requête (pour GET)

        Returns:
            Réponse JSON de l'API

        Raises:
            ConnectionError: Si le serveur est inaccessible
            PermissionError: Si l'authentification échoue
            Exception: Pour les autres erreurs
        """
        url = f"{self.server_url}{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=data,
                params=params,
                timeout=self.timeout
            )

            # Gérer les erreurs
            if response.status_code == 401:
                # Token expiré ou invalide
                self.token = None
                raise PermissionError("Session expirée, reconnexion nécessaire")

            if response.status_code == 403:
                raise PermissionError(f"Accès refusé: {response.json().get('detail', 'Permission refusée')}")

            if response.status_code == 404:
                return None

            if response.status_code >= 400:
                error_detail = response.json().get("detail", "Erreur inconnue")
                raise Exception(f"Erreur API ({response.status_code}): {error_detail}")

            # Retourner les données
            if response.content:
                return response.json()
            return {"success": True}

        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Impossible de se connecter au serveur {self.server_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Le serveur ne répond pas (timeout: {self.timeout}s)")

    # ============== Authentification ==============

    def login(self, username: Optional[str] = None) -> bool:
        """
        Authentifie l'utilisateur auprès du serveur.

        Args:
            username: Nom d'utilisateur (optionnel, utilise le user Windows par défaut)

        Returns:
            True si l'authentification réussit

        Raises:
            PermissionError: Si l'utilisateur n'est pas autorisé
        """
        if username is None:
            username = self._get_windows_username()

        hostname = self._get_hostname()

        response = self._request("POST", "/auth/login", {
            "username": username,
            "hostname": hostname
        })

        if response and "access_token" in response:
            self.token = response["access_token"]
            self.user_info = response.get("user", {})
            print(f"Connecté en tant que {self.user_info.get('username')} ({self.user_info.get('role')})")
            return True

        return False

    def logout(self):
        """Déconnecte l'utilisateur"""
        if self.token:
            try:
                self._request("POST", "/auth/logout")
            except Exception:
                pass
        self.token = None
        self.user_info = None

    def is_authenticated(self) -> bool:
        """Vérifie si l'utilisateur est authentifié"""
        return self.token is not None

    def get_current_user(self) -> Optional[Dict]:
        """Retourne les informations de l'utilisateur courant"""
        return self.user_info

    def has_permission(self, permission: str) -> bool:
        """Vérifie si l'utilisateur a une permission spécifique"""
        if not self.user_info:
            return False
        permissions = self.user_info.get("permissions", {})
        return permissions.get(permission, False)

    # ============== Missions ==============

    def get_missions(
        self,
        date_debut: Optional[str] = None,
        date_fin: Optional[str] = None,
        chauffeur_id: Optional[int] = None,
        voyage_id: Optional[int] = None,
        statut: Optional[str] = None
    ) -> List[Dict]:
        """
        Récupère les missions avec filtres optionnels.

        Args:
            date_debut: Date de début (format YYYY-MM-DD)
            date_fin: Date de fin (format YYYY-MM-DD)
            chauffeur_id: ID du chauffeur
            voyage_id: ID du voyage
            statut: Statut de la mission

        Returns:
            Liste des missions
        """
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

    def get_missions_by_date(self, mission_date: str) -> List[Dict]:
        """
        Récupère toutes les missions d'une date.

        Args:
            mission_date: Date au format YYYY-MM-DD

        Returns:
            Liste des missions de la date
        """
        return self._request("GET", f"/missions/by-date/{mission_date}") or []

    def get_mission(self, mission_id: int) -> Optional[Dict]:
        """Récupère une mission par son ID"""
        return self._request("GET", f"/missions/{mission_id}")

    def create_mission(self, mission_data: Dict) -> Dict:
        """
        Crée une nouvelle mission.

        Args:
            mission_data: Données de la mission

        Returns:
            Mission créée
        """
        return self._request("POST", "/missions", mission_data)

    def update_mission(self, mission_id: int, mission_data: Dict) -> Dict:
        """
        Met à jour une mission.

        Args:
            mission_id: ID de la mission
            mission_data: Données à mettre à jour

        Returns:
            Mission mise à jour
        """
        return self._request("PUT", f"/missions/{mission_id}", mission_data)

    def delete_mission(self, mission_id: int) -> bool:
        """Supprime une mission"""
        result = self._request("DELETE", f"/missions/{mission_id}")
        return result.get("success", False) if result else False

    # ============== Voyages ==============

    def get_voyages(self, active_only: bool = True) -> List[Dict]:
        """
        Récupère la liste des voyages.

        Args:
            active_only: Si True, retourne uniquement les voyages actifs

        Returns:
            Liste des voyages
        """
        params = {"active_only": active_only}
        return self._request("GET", "/voyages", params=params) or []

    def get_voyage(self, voyage_id: int) -> Optional[Dict]:
        """Récupère un voyage par son ID"""
        return self._request("GET", f"/voyages/{voyage_id}")

    def get_voyage_by_code(self, code: str) -> Optional[Dict]:
        """Récupère un voyage par son code"""
        return self._request("GET", f"/voyages/code/{code}")

    def create_voyage(self, voyage_data: Dict) -> Dict:
        """Crée un nouveau voyage"""
        return self._request("POST", "/voyages", voyage_data)

    def update_voyage(self, voyage_id: int, voyage_data: Dict) -> Dict:
        """Met à jour un voyage"""
        return self._request("PUT", f"/voyages/{voyage_id}", voyage_data)

    # ============== Chauffeurs ==============

    def get_chauffeurs(self, active_only: bool = True) -> List[Dict]:
        """
        Récupère la liste des chauffeurs.

        Args:
            active_only: Si True, retourne uniquement les chauffeurs actifs

        Returns:
            Liste des chauffeurs
        """
        params = {"active_only": active_only}
        return self._request("GET", "/chauffeurs", params=params) or []

    def get_chauffeur(self, chauffeur_id: int) -> Optional[Dict]:
        """Récupère un chauffeur par son ID"""
        return self._request("GET", f"/chauffeurs/{chauffeur_id}")

    def get_chauffeur_by_code(self, code: str) -> Optional[Dict]:
        """Récupère un chauffeur par son code"""
        return self._request("GET", f"/chauffeurs/code/{code}")

    def get_chauffeurs_disponibles(self, check_date: str) -> Dict:
        """
        Récupère les chauffeurs disponibles pour une date.

        Args:
            check_date: Date au format YYYY-MM-DD

        Returns:
            Dict avec "disponibles" et "indisponibles"
        """
        return self._request("GET", f"/chauffeurs/disponibles/{check_date}")

    def create_chauffeur(self, chauffeur_data: Dict) -> Dict:
        """Crée un nouveau chauffeur"""
        return self._request("POST", "/chauffeurs", chauffeur_data)

    def update_chauffeur(self, chauffeur_id: int, chauffeur_data: Dict) -> Dict:
        """Met à jour un chauffeur"""
        return self._request("PUT", f"/chauffeurs/{chauffeur_id}", chauffeur_data)

    # ============== Utilitaires ==============

    def check_server(self) -> Dict:
        """
        Vérifie l'état du serveur.

        Returns:
            Informations sur le serveur
        """
        try:
            # Pas besoin d'authentification pour /health
            response = requests.get(
                f"{self.server_url}/health",
                timeout=5
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_server_info(self) -> Dict:
        """Récupère les informations du serveur"""
        try:
            response = requests.get(
                f"{self.server_url}/server-info",
                timeout=5
            )
            return response.json()
        except Exception:
            return {}


# ============== Fonctions de compatibilité ==============
# Ces fonctions permettent de remplacer load_json/save_json
# avec un minimum de modifications dans le code existant

_client: Optional[TomatoPlanClient] = None


def init_client(server_url: str) -> TomatoPlanClient:
    """
    Initialise le client global.

    Args:
        server_url: URL du serveur

    Returns:
        Instance du client
    """
    global _client
    _client = TomatoPlanClient(server_url)
    _client.login()
    return _client


def get_client() -> TomatoPlanClient:
    """Retourne le client global"""
    if _client is None:
        raise RuntimeError("Client non initialisé. Appelez init_client() d'abord.")
    return _client


# ============== Exemple d'utilisation ==============

if __name__ == "__main__":
    # Configuration
    SERVER_URL = "http://localhost:8000"

    # Créer le client
    client = TomatoPlanClient(SERVER_URL)

    # Vérifier le serveur
    print("Vérification du serveur...")
    status = client.check_server()
    print(f"  Status: {status.get('status')}")
    print(f"  Uptime: {status.get('uptime_formatted')}")

    # Se connecter
    print("\nConnexion...")
    try:
        if client.login():
            print(f"  Utilisateur: {client.user_info.get('username')}")
            print(f"  Rôle: {client.user_info.get('role')}")
            print(f"  Permissions: {list(k for k, v in client.user_info.get('permissions', {}).items() if v)}")

            # Récupérer les données
            print("\nDonnées:")

            voyages = client.get_voyages()
            print(f"  Voyages actifs: {len(voyages)}")

            chauffeurs = client.get_chauffeurs()
            print(f"  Chauffeurs actifs: {len(chauffeurs)}")

            today = date.today().isoformat()
            missions = client.get_missions_by_date(today)
            print(f"  Missions aujourd'hui: {len(missions)}")

            # Déconnexion
            client.logout()
            print("\nDéconnecté.")

    except ConnectionError as e:
        print(f"  Erreur de connexion: {e}")
    except PermissionError as e:
        print(f"  Accès refusé: {e}")
    except Exception as e:
        print(f"  Erreur: {e}")
