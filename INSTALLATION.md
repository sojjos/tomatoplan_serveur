# Guide d'installation pas à pas - TomatoPlan Server

Ce guide vous accompagne étape par étape pour installer et configurer le serveur TomatoPlan.

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Installation du serveur](#2-installation-du-serveur)
3. [Configuration](#3-configuration)
4. [Premier démarrage](#4-premier-démarrage)
5. [Configuration des utilisateurs](#5-configuration-des-utilisateurs)
6. [Test de l'API](#6-test-de-lapi)
7. [Démarrage automatique (service)](#7-démarrage-automatique-service)
8. [Configuration du client Windows](#8-configuration-du-client-windows)
9. [Sauvegarde et maintenance](#9-sauvegarde-et-maintenance)
10. [Dépannage](#10-dépannage)

---

## 1. Prérequis

### Sur le serveur Linux

Vérifiez que vous avez :

```bash
# Vérifier la version de Python (3.9+ requis)
python3 --version

# Si Python n'est pas installé :
# Debian/Ubuntu :
sudo apt update
sudo apt install python3 python3-pip python3-venv git

# RHEL/CentOS :
sudo dnf install python3 python3-pip git
```

### Informations à préparer

Avant de commencer, notez :

- [ ] **Adresse IP du serveur** : `_______________` (ex: 192.168.1.100)
- [ ] **Port souhaité** : `_______________` (défaut: 8000)
- [ ] **Nom de l'admin** : `_______________` (votre user Windows, ex: JEAN.DUPONT)

---

## 2. Installation du serveur

### Étape 2.1 : Télécharger le projet

```bash
# Se placer dans le dossier d'installation
cd /opt

# Cloner le projet (ou copier les fichiers)
git clone https://github.com/votre-org/tomatoplan_serveur.git

# Entrer dans le dossier
cd tomatoplan_serveur
```

### Étape 2.2 : Lancer l'installation automatique

```bash
# Rendre le script exécutable
chmod +x scripts/install.sh

# Lancer l'installation
# Remplacez 8000 par votre port et VOTRE_USER par votre identifiant Windows
./scripts/install.sh --port 8000 --admin VOTRE_USER
```

**Exemple :**
```bash
./scripts/install.sh --port 8000 --admin JEAN.DUPONT
```

### Étape 2.3 : Vérifier l'installation

À la fin de l'installation, vous devriez voir :
```
============================================
   Installation terminée avec succès!
============================================

Configuration:
  Port:           8000
  Base de données: ./data/tomatoplan.db
  Admin:          JEAN.DUPONT
```

---

## 3. Configuration

### Étape 3.1 : Vérifier le fichier .env

Le fichier `.env` a été créé automatiquement. Vérifiez son contenu :

```bash
cat .env
```

Vous devriez voir :
```env
TOMATOPLAN_HOST=0.0.0.0
TOMATOPLAN_PORT=8000
TOMATOPLAN_DATABASE_PATH=./data/tomatoplan.db
TOMATOPLAN_DEFAULT_ADMIN_USERNAME=JEAN.DUPONT
TOMATOPLAN_LOG_LEVEL=INFO
```

### Étape 3.2 : Modifier la configuration (optionnel)

Pour modifier les paramètres :

```bash
nano .env
```

**Paramètres disponibles :**

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `TOMATOPLAN_PORT` | Port d'écoute | 8000 |
| `TOMATOPLAN_LOG_LEVEL` | Niveau de log (DEBUG/INFO/WARNING/ERROR) | INFO |
| `TOMATOPLAN_AUTO_BACKUP_ENABLED` | Backup automatique | true |
| `TOMATOPLAN_AUTO_BACKUP_HOUR` | Heure du backup (0-23) | 2 |
| `TOMATOPLAN_BACKUP_RETENTION_DAYS` | Conservation des backups (jours) | 30 |

---

## 4. Premier démarrage

### Étape 4.1 : Démarrer le serveur manuellement

```bash
./start.sh
```

Vous devriez voir :
```
============================================================
Démarrage de TomatoPlan Server v1.0.0
============================================================
Initialisation de la base de données...
Création des rôles par défaut...
  7 rôles créés
Création de l'utilisateur admin par défaut...
  Admin créé: JEAN.DUPONT
Base de données initialisée
Serveur prêt sur http://0.0.0.0:8000
============================================================
```

### Étape 4.2 : Tester l'accès

Depuis un navigateur ou avec curl :

```bash
# Test de santé
curl http://localhost:8000/health

# Réponse attendue :
# {"status":"healthy","uptime_seconds":42,"uptime_formatted":"42s","version":"1.0.0"}
```

### Étape 4.3 : Accéder à l'interface web

Ouvrez dans un navigateur :
- **Documentation API** : http://VOTRE_IP:8000/docs
- **Interface admin** : http://VOTRE_IP:8000/admin

---

## 5. Configuration des utilisateurs

### Étape 5.1 : Se connecter en tant qu'admin

Utilisez l'API pour vous connecter :

```bash
# Connexion (remplacez JEAN.DUPONT par votre admin)
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "JEAN.DUPONT"}'
```

Réponse :
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_at": "2024-01-15T18:00:00",
  "user": {
    "username": "JEAN.DUPONT",
    "role": "admin",
    "is_system_admin": true
  }
}
```

**Gardez le token pour les commandes suivantes !**

### Étape 5.2 : Créer des utilisateurs

```bash
# Remplacez TOKEN par votre access_token
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."

# Créer un planificateur
curl -X POST "http://localhost:8000/admin/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "MARIE.MARTIN",
    "display_name": "Marie Martin",
    "role_name": "planner"
  }'

# Créer un visualisateur
curl -X POST "http://localhost:8000/admin/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "PIERRE.DURAND",
    "display_name": "Pierre Durand",
    "role_name": "viewer"
  }'
```

### Étape 5.3 : Rôles disponibles

| Rôle | Description | Permissions |
|------|-------------|-------------|
| `viewer` | Consultation seule | Voir planning et chauffeurs |
| `planner` | Planificateur | Modifier planning, gérer voyages |
| `planner_advanced` | Planificateur avancé | + historique, finance |
| `driver_admin` | Gestionnaire chauffeurs | Gérer chauffeurs |
| `finance` | Finances | Voir/gérer données financières |
| `admin` | Administrateur | Tout accès |

### Étape 5.4 : Lister les utilisateurs

```bash
curl "http://localhost:8000/admin/users" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. Test de l'API

### Étape 6.1 : Créer un voyage test

```bash
curl -X POST "http://localhost:8000/voyages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "LUX01",
    "nom": "Luxembourg Daily",
    "depart": "Tubize",
    "destination": "Luxembourg",
    "pays_destination": "Luxembourg",
    "heure_depart_defaut": "06:00"
  }'
```

### Étape 6.2 : Créer un chauffeur test

```bash
curl -X POST "http://localhost:8000/chauffeurs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "JD01",
    "nom": "Dupont",
    "prenom": "Jean",
    "permis": "CE",
    "adr": true
  }'
```

### Étape 6.3 : Créer une mission test

```bash
curl -X POST "http://localhost:8000/missions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date_mission": "2024-01-15",
    "heure_debut": "06:00",
    "destination": "Luxembourg",
    "chauffeur_id": 1,
    "voyage_id": 1,
    "statut": "planifie"
  }'
```

### Étape 6.4 : Vérifier les données

```bash
# Lister les voyages
curl "http://localhost:8000/voyages" -H "Authorization: Bearer $TOKEN"

# Lister les chauffeurs
curl "http://localhost:8000/chauffeurs" -H "Authorization: Bearer $TOKEN"

# Lister les missions d'une date
curl "http://localhost:8000/missions/by-date/2024-01-15" -H "Authorization: Bearer $TOKEN"

# Dashboard stats
curl "http://localhost:8000/stats/dashboard" -H "Authorization: Bearer $TOKEN"
```

---

## 7. Démarrage automatique (service)

### Étape 7.1 : Installer le service systemd

```bash
# Arrêter le serveur manuel (Ctrl+C) puis :
sudo ./scripts/install.sh --port 8000 --admin VOTRE_USER
```

Ou créer le service manuellement :

```bash
sudo nano /etc/systemd/system/tomatoplan.service
```

Contenu :
```ini
[Unit]
Description=TomatoPlan Server
After=network.target

[Service]
Type=simple
User=votre_user
WorkingDirectory=/opt/tomatoplan_serveur
Environment="PATH=/opt/tomatoplan_serveur/venv/bin"
ExecStart=/opt/tomatoplan_serveur/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Étape 7.2 : Activer le service

```bash
# Recharger systemd
sudo systemctl daemon-reload

# Activer le démarrage automatique
sudo systemctl enable tomatoplan

# Démarrer le service
sudo systemctl start tomatoplan

# Vérifier le statut
sudo systemctl status tomatoplan
```

### Étape 7.3 : Commandes utiles

```bash
# Démarrer
sudo systemctl start tomatoplan

# Arrêter
sudo systemctl stop tomatoplan

# Redémarrer
sudo systemctl restart tomatoplan

# Voir les logs
sudo journalctl -u tomatoplan -f
```

---

## 8. Configuration du client Windows

### Étape 8.1 : Copier le module client

Copiez le dossier `client_example/` sur les postes Windows.

### Étape 8.2 : Installer les dépendances

```cmd
pip install requests
```

### Étape 8.3 : Tester la connexion

Créez un fichier `test_connexion.py` :

```python
from api_client import TomatoPlanClient

# Remplacez par l'IP de votre serveur
SERVER_URL = "http://192.168.1.100:8000"

# Créer le client
client = TomatoPlanClient(SERVER_URL)

# Vérifier le serveur
print("Test du serveur...")
status = client.check_server()
print(f"  Statut: {status.get('status')}")

# Se connecter (utilise automatiquement le user Windows)
print("\nConnexion...")
if client.login():
    print(f"  Connecté en tant que: {client.user_info.get('username')}")
    print(f"  Rôle: {client.user_info.get('role')}")

    # Test de lecture
    voyages = client.get_voyages()
    print(f"\n  Voyages disponibles: {len(voyages)}")

    client.logout()
    print("\nDéconnecté.")
else:
    print("  Échec de connexion!")
```

Exécuter :
```cmd
python test_connexion.py
```

### Étape 8.4 : Intégrer dans PTT

Dans votre fichier PTT modifié, ajoutez au début :

```python
# Configuration serveur
from client_example.api_client import init_client, get_client

SERVER_URL = "http://192.168.1.100:8000"

# Initialisation au démarrage
try:
    client = init_client(SERVER_URL)
    print(f"Connecté au serveur en tant que {client.user_info['username']}")
except Exception as e:
    print(f"Erreur de connexion: {e}")
    # Fallback ou message d'erreur
```

---

## 9. Sauvegarde et maintenance

### Étape 9.1 : Backup manuel

```bash
# Via l'API
curl -X POST "http://localhost:8000/admin/backups?description=Backup%20manuel" \
  -H "Authorization: Bearer $TOKEN"

# Ou copie directe du fichier
cp /opt/tomatoplan_serveur/data/tomatoplan.db /backup/tomatoplan_$(date +%Y%m%d).db
```

### Étape 9.2 : Lister les backups

```bash
curl "http://localhost:8000/admin/backups" -H "Authorization: Bearer $TOKEN"
```

### Étape 9.3 : Restaurer un backup

```bash
# Via l'API (ATTENTION: écrase la base actuelle!)
curl -X POST "http://localhost:8000/admin/backups/restore/backup_20240115_120000.db" \
  -H "Authorization: Bearer $TOKEN"

# Puis redémarrer le serveur
sudo systemctl restart tomatoplan
```

### Étape 9.4 : Consulter les logs

```bash
# Logs du serveur
tail -f /opt/tomatoplan_serveur/logs/server.log

# Logs systemd
sudo journalctl -u tomatoplan -f

# Activité via API
curl "http://localhost:8000/stats/activity/recent?limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 10. Dépannage

### Le serveur ne démarre pas

```bash
# Vérifier les erreurs
sudo journalctl -u tomatoplan --no-pager -n 50

# Vérifier les permissions
ls -la /opt/tomatoplan_serveur/

# Vérifier l'environnement virtuel
source /opt/tomatoplan_serveur/venv/bin/activate
python -c "import fastapi; print('OK')"
```

### Erreur "Connection refused"

```bash
# Vérifier que le serveur écoute
ss -tlnp | grep 8000

# Vérifier le firewall
sudo ufw status
sudo ufw allow 8000
```

### Erreur "401 Unauthorized"

- Vérifiez que votre username Windows est bien enregistré
- Vérifiez que votre compte est actif
- Le token a peut-être expiré (8h par défaut)

### Erreur "403 Forbidden"

- Votre rôle n'a pas la permission requise
- Contactez l'administrateur pour modifier vos droits

### Réinitialiser la base de données

```bash
# ATTENTION: supprime toutes les données!
sudo systemctl stop tomatoplan
rm /opt/tomatoplan_serveur/data/tomatoplan.db
sudo systemctl start tomatoplan
```

---

## Checklist de vérification

- [ ] Python 3.9+ installé sur le serveur
- [ ] Installation terminée sans erreur
- [ ] Fichier .env configuré
- [ ] Serveur accessible sur http://IP:8000/health
- [ ] Admin créé et peut se connecter
- [ ] Autres utilisateurs créés
- [ ] Service systemd activé (optionnel)
- [ ] Client Windows peut se connecter
- [ ] Backup automatique configuré

---

## Support

- **Documentation API** : http://VOTRE_IP:8000/docs
- **Interface admin** : http://VOTRE_IP:8000/admin
- **Logs** : `/opt/tomatoplan_serveur/logs/server.log`

---

*Guide créé pour TomatoPlan Server v1.0.0*
