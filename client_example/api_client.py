"""
TomatoPlan API Client
Module client pour communiquer avec le serveur TomatoPlan.

Ce module remplace les fonctions load_json/save_json de l'application originale
pour utiliser l'API REST au lieu des fichiers JSON locaux.

IMPORTANT: Pour un serveur exposé sur Internet, utilisez HTTPS obligatoirement.
L'authentification par mot de passe est requise.

Usage:
    from api_client import TomatoPlanClient

    # Connexion au serveur (HTTPS obligatoire pour Internet)
    client = TomatoPlanClient("https://serveur.example.com", verify_ssl=True)
    # Pour certificat auto-signé: verify_ssl=False

    # Connexion avec mot de passe (demandé interactivement si non fourni)
    client.login(password="votre_mot_de_passe")
    # Ou: client.login()  # Le mot de passe sera demandé via getpass

    # Si premier login avec mot de passe temporaire
    if client.must_change_password:
        client.change_password("mot_de_passe_temp", "nouveau_mot_de_passe")

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
import urllib3
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import json

# Désactiver les warnings pour les certificats auto-signés (si nécessaire)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TomatoPlanClient:
    """Client pour l'API TomatoPlan"""

    def __init__(
        self,
        server_url: str,
        timeout: int = 30,
        verify_ssl: bool = True
    ):
        """
        Initialise le client API.

        Args:
            server_url: URL du serveur (ex: "https://serveur.example.com")
            timeout: Timeout des requêtes en secondes
            verify_ssl: Vérifier le certificat SSL (False pour certificats auto-signés)
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None
        self.must_change_password: bool = False
        self._session = requests.Session()

        # Chemins pour le cache local et les credentials
        self._app_dir = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "TomatoPlan"
        self._cache_dir = self._app_dir / "cache"
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
                timeout=self.timeout,
                verify=self.verify_ssl
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

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Authentifie l'utilisateur auprès du serveur.

        Args:
            username: Nom d'utilisateur (optionnel, utilise le user Windows par défaut)
            password: Mot de passe (obligatoire pour serveur Internet)

        Returns:
            True si l'authentification réussit

        Raises:
            PermissionError: Si l'utilisateur n'est pas autorisé
            ValueError: Si le mot de passe n'est pas fourni
        """
        if username is None:
            username = self._get_windows_username()

        # Demander le mot de passe si non fourni
        if password is None:
            password = getpass.getpass(f"Mot de passe pour {username}: ")

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

            print(f"Connecté en tant que {self.user_info.get('username')} ({self.user_info.get('role')})")

            if self.must_change_password:
                print("⚠️  Vous devez changer votre mot de passe temporaire.")

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
        self.must_change_password = False

    def change_password(self, current_password: str, new_password: str) -> bool:
        """
        Change le mot de passe de l'utilisateur.

        Args:
            current_password: Mot de passe actuel
            new_password: Nouveau mot de passe (min 8 car., majuscule, minuscule, chiffre)

        Returns:
            True si le changement réussit

        Raises:
            ValueError: Si le nouveau mot de passe ne respecte pas les critères
        """
        response = self._request("POST", "/auth/change-password", {
            "current_password": current_password,
            "new_password": new_password
        })

        if response and response.get("success"):
            self.must_change_password = False
            print("Mot de passe modifié avec succès.")
            return True

        return False

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
                timeout=5,
                verify=self.verify_ssl
            )
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_server_info(self) -> Dict:
        """Récupère les informations du serveur"""
        try:
            response = requests.get(
                f"{self.server_url}/server-info",
                timeout=5,
                verify=self.verify_ssl
            )
            return response.json()
        except Exception:
            return {}


# ============== Fonctions de compatibilité ==============
# Ces fonctions permettent de remplacer load_json/save_json
# avec un minimum de modifications dans le code existant

_client: Optional[TomatoPlanClient] = None


def init_client(
    server_url: str,
    password: Optional[str] = None,
    verify_ssl: bool = True
) -> TomatoPlanClient:
    """
    Initialise le client global.

    Args:
        server_url: URL du serveur (ex: "https://server.example.com")
        password: Mot de passe (demandé interactivement si non fourni)
        verify_ssl: Vérifier le certificat SSL (False pour certificats auto-signés)

    Returns:
        Instance du client
    """
    global _client
    _client = TomatoPlanClient(server_url, verify_ssl=verify_ssl)
    _client.login(password=password)
    return _client


def get_client() -> TomatoPlanClient:
    """Retourne le client global"""
    if _client is None:
        raise RuntimeError("Client non initialisé. Appelez init_client() d'abord.")
    return _client


# ============== Exemple d'utilisation ==============

if __name__ == "__main__":
    # Configuration - Utiliser HTTPS pour serveur Internet
    SERVER_URL = "https://votre-serveur.example.com"
    # Pour développement local :
    # SERVER_URL = "http://localhost:8000"

    # Créer le client
    # verify_ssl=False si vous utilisez un certificat auto-signé
    client = TomatoPlanClient(SERVER_URL, verify_ssl=True)

    # Vérifier le serveur
    print("Vérification du serveur...")
    status = client.check_server()
    print(f"  Status: {status.get('status')}")
    print(f"  Uptime: {status.get('uptime_formatted')}")

    # Se connecter (le mot de passe sera demandé interactivement)
    print("\nConnexion...")
    try:
        if client.login():  # password sera demandé via getpass
            print(f"  Utilisateur: {client.user_info.get('username')}")
            print(f"  Rôle: {client.user_info.get('role')}")
            print(f"  Permissions: {list(k for k, v in client.user_info.get('permissions', {}).items() if v)}")

            # Vérifier si changement de mot de passe requis
            if client.must_change_password:
                print("\n⚠️  Changement de mot de passe requis!")
                new_pwd = getpass.getpass("Nouveau mot de passe: ")
                confirm_pwd = getpass.getpass("Confirmer: ")
                if new_pwd == confirm_pwd:
                    # Le mot de passe actuel est le mot de passe temporaire utilisé pour login
                    current_pwd = getpass.getpass("Mot de passe actuel (temporaire): ")
                    client.change_password(current_pwd, new_pwd)

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
