"""
WebSocket Manager - Gestion des connexions temps réel multi-utilisateurs

Ce module gère les connexions WebSocket pour permettre la synchronisation
en temps réel entre tous les clients connectés.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass, field
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("tomatoplan.websocket")


@dataclass
class ConnectedClient:
    """Représente un client connecté"""
    websocket: WebSocket
    username: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class WebSocketManager:
    """
    Gestionnaire centralisé des connexions WebSocket.

    Permet de:
    - Gérer les connexions/déconnexions des clients
    - Diffuser des messages à tous les clients
    - Envoyer des notifications de changements de données
    """

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

        # Clients connectés: {client_id: ConnectedClient}
        self._clients: Dict[str, ConnectedClient] = {}

        # Lock pour thread-safety
        self._lock = asyncio.Lock()

        # Compteur pour générer des IDs uniques
        self._client_counter = 0

        logger.info("WebSocket Manager initialisé")

    def _generate_client_id(self, username: str) -> str:
        """Génère un ID unique pour un client"""
        self._client_counter += 1
        return f"{username}_{self._client_counter}_{datetime.now().timestamp()}"

    async def connect(self, websocket: WebSocket, username: str) -> str:
        """
        Enregistre une nouvelle connexion WebSocket.

        Returns:
            client_id: Identifiant unique du client
        """
        await websocket.accept()

        async with self._lock:
            client_id = self._generate_client_id(username)
            self._clients[client_id] = ConnectedClient(
                websocket=websocket,
                username=username
            )

        logger.info(f"Client connecté: {username} (ID: {client_id})")

        # Notifier les autres utilisateurs
        await self.broadcast_user_event("user_connected", {
            "username": username,
            "timestamp": datetime.now().isoformat()
        }, exclude_client=client_id)

        # Envoyer la liste des utilisateurs connectés au nouveau client
        await self.send_to_client(client_id, {
            "type": "connected_users",
            "users": await self.get_connected_users()
        })

        return client_id

    async def disconnect(self, client_id: str):
        """Déconnecte un client"""
        async with self._lock:
            if client_id in self._clients:
                client = self._clients[client_id]
                username = client.username
                del self._clients[client_id]

                logger.info(f"Client déconnecté: {username} (ID: {client_id})")

                # Notifier les autres utilisateurs
                await self._broadcast_internal("user_disconnected", {
                    "username": username,
                    "timestamp": datetime.now().isoformat()
                })

    async def send_to_client(self, client_id: str, message: dict):
        """Envoie un message à un client spécifique"""
        async with self._lock:
            if client_id in self._clients:
                try:
                    await self._clients[client_id].websocket.send_json(message)
                    self._clients[client_id].last_activity = datetime.now()
                except Exception as e:
                    logger.error(f"Erreur envoi à {client_id}: {e}")

    async def broadcast(self, message_type: str, data: dict, exclude_client: str = None):
        """
        Diffuse un message à tous les clients connectés.

        Args:
            message_type: Type du message (ex: "data_changed", "notification")
            data: Données du message
            exclude_client: ID du client à exclure (ex: l'émetteur)
        """
        message = {
            "type": message_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        async with self._lock:
            disconnected = []

            for client_id, client in self._clients.items():
                if exclude_client and client_id == exclude_client:
                    continue

                try:
                    await client.websocket.send_json(message)
                    client.last_activity = datetime.now()
                except Exception as e:
                    logger.error(f"Erreur broadcast à {client_id}: {e}")
                    disconnected.append(client_id)

            # Nettoyer les clients déconnectés
            for client_id in disconnected:
                if client_id in self._clients:
                    del self._clients[client_id]

    async def _broadcast_internal(self, message_type: str, data: dict):
        """Broadcast interne (sans lock)"""
        message = {
            "type": message_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        disconnected = []

        for client_id, client in list(self._clients.items()):
            try:
                await client.websocket.send_json(message)
            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            if client_id in self._clients:
                del self._clients[client_id]

    async def broadcast_data_change(
        self,
        entity_type: str,
        action: str,
        entity_id: Any = None,
        data: dict = None,
        changed_by: str = None
    ):
        """
        Notifie tous les clients d'un changement de données.

        Args:
            entity_type: Type d'entité modifiée (missions, voyages, chauffeurs, etc.)
            action: Action effectuée (created, updated, deleted)
            entity_id: ID de l'entité concernée
            data: Données supplémentaires
            changed_by: Utilisateur ayant fait le changement
        """
        await self.broadcast("data_changed", {
            "entity": entity_type,
            "action": action,
            "entity_id": entity_id,
            "changed_by": changed_by,
            "details": data or {}
        })

        logger.debug(f"Changement diffusé: {entity_type}/{action} par {changed_by}")

    async def broadcast_user_event(
        self,
        event_type: str,
        data: dict,
        exclude_client: str = None
    ):
        """Diffuse un événement utilisateur (connexion, déconnexion, etc.)"""
        await self.broadcast(event_type, data, exclude_client)

    async def get_connected_users(self) -> list:
        """Retourne la liste des utilisateurs connectés"""
        users = {}

        async with self._lock:
            for client in self._clients.values():
                if client.username not in users:
                    users[client.username] = {
                        "username": client.username,
                        "connected_at": client.connected_at.isoformat(),
                        "connections": 1
                    }
                else:
                    users[client.username]["connections"] += 1

        return list(users.values())

    @property
    def connected_count(self) -> int:
        """Nombre de connexions actives"""
        return len(self._clients)

    @property
    def connected_users_count(self) -> int:
        """Nombre d'utilisateurs uniques connectés"""
        usernames = set()
        for client in self._clients.values():
            usernames.add(client.username)
        return len(usernames)


# Instance globale
ws_manager = WebSocketManager()


# ============================================================================
# FONCTIONS UTILITAIRES POUR LES ROUTERS
# ============================================================================

async def notify_change(
    entity_type: str,
    action: str,
    entity_id: Any = None,
    data: dict = None,
    changed_by: str = None
):
    """
    Fonction utilitaire pour notifier un changement depuis les routers.

    Usage dans un router:
        from server.services.websocket_manager import notify_change

        @router.post("/missions")
        async def create_mission(...):
            # ... créer la mission ...
            await notify_change("missions", "created", mission.id, changed_by=current_user.username)
    """
    await ws_manager.broadcast_data_change(
        entity_type=entity_type,
        action=action,
        entity_id=entity_id,
        data=data,
        changed_by=changed_by
    )


async def notify_refresh_required(entity_type: str = None, changed_by: str = None):
    """
    Notifie les clients qu'un rafraîchissement est nécessaire.

    Args:
        entity_type: Type spécifique à rafraîchir (None = tout)
        changed_by: Utilisateur ayant fait le changement
    """
    await ws_manager.broadcast("refresh_required", {
        "entity": entity_type,
        "changed_by": changed_by
    })
