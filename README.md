# TomatoPlan Server

Serveur API REST pour la gestion de planning transport, conçu pour remplacer l'architecture fichiers JSON de PTT_v0.6 par une architecture client-serveur moderne.

## Architecture

```
[ Postes clients Windows ]          [ Serveur Linux ]
       (PTT Client)         ────►    (TomatoPlan Server)
           │                              │
           │  HTTP/REST API               │
           │  Port 8000                   │
           └──────────────────────────────┘
                                          │
                                    [ SQLite DB ]
```

## Fonctionnalités

### API REST
- **Authentification** par identifiant Windows (pas de mot de passe)
- **Gestion des missions** : CRUD complet, filtrage par date/chauffeur/voyage
- **Gestion des voyages** : lignes de transport régulières
- **Gestion des chauffeurs** : disponibilités, compétences
- **Statistiques** : dashboard, activité par utilisateur

### Interface d'administration web
- Dashboard temps réel (uptime, stats, sessions actives)
- Gestion des utilisateurs et des rôles
- Visualisation des logs et activités
- Backup/Restauration de la base de données
- Configuration du serveur

### Système de droits
Rôles disponibles :
- `viewer` : Consultation uniquement
- `planner` : Modification du planning
- `planner_advanced` : Accès étendu (historique, finance)
- `driver_admin` : Gestion des chauffeurs
- `finance` : Accès aux données financières
- `admin` : Accès complet

## Installation rapide

### Prérequis
- Linux (Debian/Ubuntu ou RHEL/CentOS)
- Python 3.9+
- Accès réseau interne (port 8000)

### Installation

```bash
# Cloner le projet
git clone https://github.com/votre-org/tomatoplan_serveur.git
cd tomatoplan_serveur

# Lancer l'installation
chmod +x scripts/install.sh
./scripts/install.sh --port 8000 --admin VOTRE_USER
```

### Démarrage

```bash
# Démarrage manuel
./start.sh

# Ou via systemd (si installé avec sudo)
sudo systemctl start tomatoplan
sudo systemctl status tomatoplan
```

## Configuration

Le fichier `.env` contient la configuration du serveur :

```env
# Serveur
TOMATOPLAN_HOST=0.0.0.0
TOMATOPLAN_PORT=8000

# Base de données
TOMATOPLAN_DATABASE_PATH=./data/tomatoplan.db

# Admin par défaut
TOMATOPLAN_DEFAULT_ADMIN_USERNAME=ADMIN

# Logs
TOMATOPLAN_LOG_LEVEL=INFO

# Backup automatique
TOMATOPLAN_AUTO_BACKUP_ENABLED=true
TOMATOPLAN_AUTO_BACKUP_HOUR=2
TOMATOPLAN_BACKUP_RETENTION_DAYS=30
```

## Utilisation de l'API

### Authentification

```python
import requests

# Connexion (utilise l'identifiant Windows)
response = requests.post("http://server:8000/auth/login", json={
    "username": "JEAN.DUPONT",  # ou DOMAIN\\username
    "hostname": "PC-BUREAU-01"
})

token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
```

### Exemples de requêtes

```python
# Récupérer les missions d'une date
missions = requests.get(
    "http://server:8000/missions/by-date/2024-01-15",
    headers=headers
).json()

# Créer une mission
new_mission = requests.post(
    "http://server:8000/missions",
    headers=headers,
    json={
        "date_mission": "2024-01-15",
        "destination": "Paris",
        "chauffeur_id": 1,
        "voyage_id": 2,
        "heure_debut": "06:00",
        "statut": "planifie"
    }
).json()

# Récupérer les chauffeurs disponibles
dispo = requests.get(
    "http://server:8000/chauffeurs/disponibles/2024-01-15",
    headers=headers
).json()
```

## Adaptation du client PTT

Le dossier `client_example/` contient :
- `api_client.py` : Client Python complet pour l'API
- `migration_guide.py` : Guide de migration depuis PTT_v0.6

### Exemple d'intégration

```python
from client_example.api_client import TomatoPlanClient

# Configuration
client = TomatoPlanClient("http://192.168.1.100:8000")

# Connexion automatique avec l'utilisateur Windows
client.login()

# Utilisation
missions = client.get_missions_by_date("2024-01-15")
voyages = client.get_voyages()
chauffeurs = client.get_chauffeurs()

# Création
new_mission = client.create_mission({
    "date_mission": "2024-01-15",
    "destination": "Lyon",
    ...
})
```

## Structure du projet

```
tomatoplan_serveur/
├── server/
│   ├── main.py              # Point d'entrée FastAPI
│   ├── config.py            # Configuration
│   ├── database.py          # Connexion SQLite
│   ├── models/              # Modèles SQLAlchemy
│   │   ├── user.py
│   │   ├── mission.py
│   │   ├── voyage.py
│   │   ├── chauffeur.py
│   │   └── activity_log.py
│   ├── routers/             # Endpoints API
│   │   ├── auth.py
│   │   ├── missions.py
│   │   ├── voyages.py
│   │   ├── chauffeurs.py
│   │   ├── admin.py
│   │   └── stats.py
│   ├── services/            # Logique métier
│   │   ├── auth_service.py
│   │   ├── backup_service.py
│   │   └── stats_service.py
│   └── admin/               # Interface web admin
│       ├── templates/
│       └── static/
├── client_example/          # Exemple client Python
├── scripts/
│   └── install.sh           # Script d'installation
├── requirements.txt
└── README.md
```

## Endpoints API

### Authentification
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/auth/login` | Connexion |
| POST | `/auth/logout` | Déconnexion |
| GET | `/auth/me` | Info utilisateur courant |

### Missions
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/missions` | Liste avec filtres |
| GET | `/missions/{id}` | Détail d'une mission |
| GET | `/missions/by-date/{date}` | Missions d'une date |
| POST | `/missions` | Créer une mission |
| PUT | `/missions/{id}` | Modifier une mission |
| DELETE | `/missions/{id}` | Supprimer une mission |

### Voyages
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/voyages` | Liste des voyages |
| GET | `/voyages/{id}` | Détail d'un voyage |
| POST | `/voyages` | Créer un voyage |
| PUT | `/voyages/{id}` | Modifier un voyage |

### Chauffeurs
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/chauffeurs` | Liste des chauffeurs |
| GET | `/chauffeurs/disponibles/{date}` | Disponibilités |
| POST | `/chauffeurs` | Créer un chauffeur |

### Administration
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/admin/users` | Liste des utilisateurs |
| POST | `/admin/users` | Créer un utilisateur |
| GET | `/admin/sessions` | Sessions actives |
| POST | `/admin/backups` | Créer un backup |

### Statistiques
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/stats/dashboard` | Dashboard |
| GET | `/stats/activity/recent` | Activité récente |

## Sécurité

- **Authentification** : Token JWT basé sur l'identifiant Windows
- **Autorisations** : Système de rôles et permissions granulaires
- **Logging** : Toutes les actions sont tracées (système SAURON)
- **Réseau** : Conçu pour réseau interne uniquement

## Backup et restauration

```bash
# Backup manuel via API
curl -X POST "http://server:8000/admin/backups?description=Mon%20backup" \
     -H "Authorization: Bearer $TOKEN"

# Liste des backups
curl "http://server:8000/admin/backups" -H "Authorization: Bearer $TOKEN"

# Restauration
curl -X POST "http://server:8000/admin/backups/restore/backup_20240115_120000.db" \
     -H "Authorization: Bearer $TOKEN"
```

## Logs

Les logs sont disponibles dans :
- `./logs/server.log` : Logs applicatifs
- API `/stats/activity/recent` : Activités utilisateurs
- Interface admin `/admin/logs` : Visualisation temps réel

## Support

- Documentation API interactive : `http://server:8000/docs`
- Health check : `http://server:8000/health`
- Interface admin : `http://server:8000/admin`

## Licence

Propriétaire - Usage interne uniquement
