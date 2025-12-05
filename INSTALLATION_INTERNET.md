# Guide d'installation - Serveur Internet (Accès distant)

Ce guide détaille l'installation de TomatoPlan sur un **serveur vierge** accessible via **Internet**.

> **IMPORTANT**: Ce guide est pour un serveur exposé sur Internet. La sécurité est primordiale!

---

## Table des matières

1. [Architecture cible](#1-architecture-cible)
2. [Prérequis serveur](#2-prérequis-serveur)
3. [Installation système](#3-installation-système)
4. [Installation TomatoPlan](#4-installation-tomatoplan)
5. [Configuration nginx (reverse proxy)](#5-configuration-nginx)
6. [Configuration HTTPS (SSL)](#6-configuration-https)
7. [Configuration firewall](#7-configuration-firewall)
8. [Création du premier utilisateur](#8-création-du-premier-utilisateur)
9. [Configuration du client Windows](#9-configuration-du-client-windows)
10. [Sécurisation finale](#10-sécurisation-finale)
11. [Maintenance](#11-maintenance)

---

## 1. Architecture cible

```
┌─────────────────┐         Internet          ┌─────────────────────────────────┐
│  Client Windows │ ◄────── HTTPS/443 ──────► │        Serveur Linux            │
│  (PTT Client)   │                           │                                 │
└─────────────────┘                           │  ┌─────────┐    ┌───────────┐  │
                                              │  │  nginx  │───►│ TomatoPlan│  │
                                              │  │ :443    │    │ :8000     │  │
                                              │  └─────────┘    └─────┬─────┘  │
                                              │                       │        │
                                              │                 ┌─────▼─────┐  │
                                              │                 │  SQLite   │  │
                                              │                 └───────────┘  │
                                              └─────────────────────────────────┘
```

**Points clés:**
- nginx en frontal (reverse proxy)
- HTTPS obligatoire (port 443)
- Authentification par **mot de passe**
- Verrouillage après tentatives échouées
- Logs de toutes les connexions

---

## 2. Prérequis serveur

### Matériel minimum
- 1 vCPU
- 1 Go RAM
- 20 Go disque
- Connexion Internet

### Informations à collecter

| Information | Valeur | Exemple |
|-------------|--------|---------|
| IP publique du serveur | _____________ | 203.0.113.50 |
| Nom de domaine (optionnel) | _____________ | tomatoplan.example.com |
| Port SSH | _____________ | 22 |
| Nom admin TomatoPlan | _____________ | JEAN.DUPONT |
| Email (pour Let's Encrypt) | _____________ | admin@example.com |

---

## 3. Installation système

### 3.1 Se connecter au serveur

```bash
ssh root@VOTRE_IP_SERVEUR
```

### 3.2 Mettre à jour le système

**Debian/Ubuntu:**
```bash
apt update && apt upgrade -y
```

**RHEL/CentOS:**
```bash
dnf update -y
```

### 3.3 Installer les dépendances système

**Debian/Ubuntu:**
```bash
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    ufw \
    curl \
    htop
```

**RHEL/CentOS:**
```bash
dnf install -y \
    python3 \
    python3-pip \
    nginx \
    certbot \
    python3-certbot-nginx \
    git \
    firewalld \
    curl
```

### 3.4 Créer un utilisateur dédié

```bash
# Créer l'utilisateur tomatoplan
useradd -m -s /bin/bash tomatoplan

# Créer le dossier d'installation
mkdir -p /opt/tomatoplan
chown tomatoplan:tomatoplan /opt/tomatoplan
```

---

## 4. Installation TomatoPlan

### 4.1 Télécharger le projet

```bash
# Se connecter en tant que tomatoplan
su - tomatoplan

# Aller dans le dossier
cd /opt/tomatoplan

# Cloner le projet
git clone https://github.com/votre-org/tomatoplan_serveur.git .

# Ou télécharger et extraire une archive
# wget https://github.com/.../archive/main.zip
# unzip main.zip
```

### 4.2 Créer l'environnement Python

```bash
# Créer l'environnement virtuel
python3 -m venv venv

# Activer
source venv/bin/activate

# Mettre à jour pip
pip install --upgrade pip

# Installer les dépendances
pip install -r requirements.txt
```

### 4.3 Configurer l'application

```bash
# Créer le fichier de configuration
cat > .env << 'EOF'
# === TomatoPlan Server Configuration ===
# Serveur exposé sur Internet

# Serveur (écoute locale, nginx en frontal)
TOMATOPLAN_HOST=127.0.0.1
TOMATOPLAN_PORT=8000
TOMATOPLAN_DEBUG=false

# Base de données
TOMATOPLAN_DATABASE_PATH=/opt/tomatoplan/data/tomatoplan.db

# Sécurité - IMPORTANT: générer une clé unique!
TOMATOPLAN_SECRET_KEY=REMPLACEZ_PAR_UNE_CLE_ALEATOIRE_LONGUE

# Session (8 heures)
TOMATOPLAN_ACCESS_TOKEN_EXPIRE_MINUTES=480

# Admin initial
TOMATOPLAN_DEFAULT_ADMIN_USERNAME=ADMIN
TOMATOPLAN_DEFAULT_ADMIN_ENABLED=true

# Logs
TOMATOPLAN_LOG_LEVEL=INFO
TOMATOPLAN_LOG_FILE=/opt/tomatoplan/logs/server.log

# Backup
TOMATOPLAN_BACKUP_DIR=/opt/tomatoplan/backups
TOMATOPLAN_BACKUP_RETENTION_DAYS=30
TOMATOPLAN_AUTO_BACKUP_ENABLED=true
TOMATOPLAN_AUTO_BACKUP_HOUR=3
EOF
```

### 4.4 Générer une clé secrète sécurisée

```bash
# Générer une clé aléatoire
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

**Copiez le résultat et remplacez `REMPLACEZ_PAR_UNE_CLE_ALEATOIRE_LONGUE` dans .env**

### 4.5 Créer les dossiers

```bash
mkdir -p /opt/tomatoplan/{data,logs,backups}
```

### 4.6 Initialiser la base de données

```bash
source venv/bin/activate
python3 -c "
import asyncio
from server.database import init_db, engine, Base
from server.models import *

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Base de données initialisée')

asyncio.run(init())
"
```

### 4.7 Créer le service systemd

```bash
# Revenir en root
exit

# Créer le fichier service
cat > /etc/systemd/system/tomatoplan.service << 'EOF'
[Unit]
Description=TomatoPlan Server
After=network.target

[Service]
Type=simple
User=tomatoplan
Group=tomatoplan
WorkingDirectory=/opt/tomatoplan
Environment="PATH=/opt/tomatoplan/venv/bin"
ExecStart=/opt/tomatoplan/venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

# Sécurité
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Activer et démarrer
systemctl daemon-reload
systemctl enable tomatoplan
systemctl start tomatoplan

# Vérifier
systemctl status tomatoplan
```

---

## 5. Configuration nginx

### 5.1 Créer la configuration nginx

```bash
cat > /etc/nginx/sites-available/tomatoplan << 'EOF'
# TomatoPlan - Configuration nginx

# Limiter les requêtes (protection anti-bruteforce)
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;

server {
    listen 80;
    server_name _;  # Remplacer par votre domaine si vous en avez un

    # Redirection HTTP -> HTTPS
    location / {
        return 301 https://$host$request_uri;
    }

    # Pour Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}

server {
    listen 443 ssl http2;
    server_name _;  # Remplacer par votre domaine

    # Certificats SSL (sera configuré par certbot ou manuellement)
    ssl_certificate /etc/nginx/ssl/tomatoplan.crt;
    ssl_certificate_key /etc/nginx/ssl/tomatoplan.key;

    # Configuration SSL sécurisée
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;

    # En-têtes de sécurité
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # Logs
    access_log /var/log/nginx/tomatoplan_access.log;
    error_log /var/log/nginx/tomatoplan_error.log;

    # Taille max des requêtes
    client_max_body_size 10M;

    # Rate limiting pour login
    location /auth/login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API avec rate limiting modéré
    location / {
        limit_req zone=api burst=50 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check (pas de rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
EOF
```

### 5.2 Activer la configuration

```bash
# Créer le lien symbolique
ln -sf /etc/nginx/sites-available/tomatoplan /etc/nginx/sites-enabled/

# Supprimer la config par défaut
rm -f /etc/nginx/sites-enabled/default
```

---

## 6. Configuration HTTPS

### Option A: Certificat Let's Encrypt (gratuit, recommandé si vous avez un domaine)

```bash
# Installer certbot nginx
certbot --nginx -d votre-domaine.com

# Le certificat sera renouvelé automatiquement
```

### Option B: Certificat auto-signé (si pas de domaine)

```bash
# Créer le dossier pour les certificats
mkdir -p /etc/nginx/ssl

# Générer un certificat auto-signé (valide 1 an)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/tomatoplan.key \
    -out /etc/nginx/ssl/tomatoplan.crt \
    -subj "/C=BE/ST=Brabant/L=Brussels/O=TomatoPlan/CN=tomatoplan"

# Sécuriser les fichiers
chmod 600 /etc/nginx/ssl/*
```

### 6.1 Tester et redémarrer nginx

```bash
# Tester la configuration
nginx -t

# Redémarrer nginx
systemctl restart nginx
systemctl status nginx
```

---

## 7. Configuration firewall

### Debian/Ubuntu (UFW)

```bash
# Activer UFW
ufw default deny incoming
ufw default allow outgoing

# Autoriser SSH
ufw allow ssh

# Autoriser HTTPS
ufw allow 443/tcp

# Autoriser HTTP (pour redirection et Let's Encrypt)
ufw allow 80/tcp

# Activer
ufw enable

# Vérifier
ufw status
```

### RHEL/CentOS (firewalld)

```bash
# Démarrer firewalld
systemctl enable firewalld
systemctl start firewalld

# Autoriser les services
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https

# Recharger
firewall-cmd --reload

# Vérifier
firewall-cmd --list-all
```

---

## 8. Création du premier utilisateur

### 8.1 Créer l'admin avec un mot de passe

```bash
# Se connecter en tant que tomatoplan
su - tomatoplan
cd /opt/tomatoplan
source venv/bin/activate

# Créer l'admin
python3 << 'EOF'
import asyncio
from server.database import async_session_maker, init_db
from server.services.auth_service import AuthService
from server.models import UserRole
from sqlalchemy import select

async def create_admin():
    # Initialiser la base
    await init_db()

    async with async_session_maker() as db:
        # Vérifier si l'admin existe
        existing = await AuthService.get_user_by_username(db, "ADMIN")
        if existing:
            # Réinitialiser le mot de passe
            temp_pwd = await AuthService.admin_reset_password(db, existing)
            print(f"\n{'='*50}")
            print("Admin existant - Mot de passe réinitialisé")
            print(f"{'='*50}")
            print(f"Utilisateur: ADMIN")
            print(f"Mot de passe temporaire: {temp_pwd}")
            print(f"{'='*50}\n")
        else:
            # Créer l'admin
            user, temp_pwd = await AuthService.create_user(
                db=db,
                username="ADMIN",
                role_name="admin",
                display_name="Administrateur",
                is_system_admin=True
            )
            print(f"\n{'='*50}")
            print("Admin créé avec succès!")
            print(f"{'='*50}")
            print(f"Utilisateur: {user.username}")
            print(f"Mot de passe temporaire: {temp_pwd}")
            print(f"{'='*50}")
            print("IMPORTANT: Changez ce mot de passe à la première connexion!")
            print(f"{'='*50}\n")

asyncio.run(create_admin())
EOF
```

**NOTEZ LE MOT DE PASSE TEMPORAIRE!**

### 8.2 Créer d'autres utilisateurs

```bash
python3 << 'EOF'
import asyncio
from server.database import async_session_maker
from server.services.auth_service import AuthService

async def create_user():
    async with async_session_maker() as db:
        # Remplacez ces valeurs
        USERNAME = "JEAN.DUPONT"  # Identifiant de l'utilisateur
        ROLE = "planner"          # viewer, planner, admin, etc.
        DISPLAY_NAME = "Jean Dupont"

        user, temp_pwd = await AuthService.create_user(
            db=db,
            username=USERNAME,
            role_name=ROLE,
            display_name=DISPLAY_NAME
        )
        print(f"\nUtilisateur créé: {user.username}")
        print(f"Rôle: {ROLE}")
        print(f"Mot de passe temporaire: {temp_pwd}")
        print("L'utilisateur devra changer son mot de passe à la première connexion.\n")

asyncio.run(create_user())
EOF
```

---

## 9. Configuration du client Windows

### 9.1 Copier le client

Copiez le dossier `client_example/` sur les postes Windows.

### 9.2 Modifier api_client.py

Ouvrez `api_client.py` et modifiez l'URL du serveur:

```python
# Configuration - À MODIFIER
SERVER_URL = "https://VOTRE_IP_OU_DOMAINE"  # Exemple: https://203.0.113.50
```

### 9.3 Test de connexion

Créez un fichier `test_connexion.py`:

```python
from api_client import TomatoPlanClient
import getpass

# Configuration
SERVER_URL = "https://VOTRE_IP_OU_DOMAINE"

# Créer le client
client = TomatoPlanClient(SERVER_URL)

# Vérifier le serveur
print("Test de connexion au serveur...")
status = client.check_server()
if status.get("status") == "healthy":
    print(f"  ✓ Serveur accessible (uptime: {status.get('uptime_formatted')})")
else:
    print(f"  ✗ Erreur: {status}")
    exit(1)

# Demander les identifiants
print("\nConnexion...")
username = input("Identifiant: ")
password = getpass.getpass("Mot de passe: ")

# Se connecter
try:
    result = client._request("POST", "/auth/login", {
        "username": username,
        "password": password
    })

    client.token = result["access_token"]
    client.user_info = result["user"]

    print(f"\n✓ Connecté en tant que: {client.user_info['username']}")
    print(f"  Rôle: {client.user_info['role']}")

    if result.get("must_change_password"):
        print("\n⚠ Vous devez changer votre mot de passe!")

    # Tester l'accès aux données
    voyages = client.get_voyages()
    print(f"\n  Voyages disponibles: {len(voyages)}")

    client.logout()
    print("\n✓ Déconnecté.")

except Exception as e:
    print(f"\n✗ Erreur: {e}")
```

### 9.4 Gestion du certificat auto-signé

Si vous utilisez un certificat auto-signé, le client affichera une erreur SSL.

**Option 1: Désactiver la vérification SSL (déconseillé en production)**

Dans `api_client.py`, modifiez la méthode `_request`:

```python
response = self._session.request(
    method=method,
    url=url,
    headers=self._headers(),
    json=data,
    params=params,
    timeout=self.timeout,
    verify=False  # Désactive la vérification SSL
)
```

**Option 2: Importer le certificat sur les postes clients (recommandé)**

1. Copiez `/etc/nginx/ssl/tomatoplan.crt` sur le poste Windows
2. Double-cliquez sur le fichier .crt
3. Cliquez sur "Installer le certificat"
4. Sélectionnez "Ordinateur local"
5. Placez-le dans "Autorités de certification racines de confiance"

---

## 10. Sécurisation finale

### 10.1 Checklist de sécurité

- [ ] Clé secrète unique générée dans `.env`
- [ ] HTTPS actif (port 443)
- [ ] HTTP redirige vers HTTPS
- [ ] Firewall configuré (seuls ports 22, 80, 443 ouverts)
- [ ] Rate limiting actif sur `/auth/login`
- [ ] Mot de passe admin changé
- [ ] Logs activés
- [ ] Backup automatique configuré

### 10.2 Désactiver la création automatique d'utilisateurs

Une fois les utilisateurs créés, éditez `.env`:

```bash
# Dans /opt/tomatoplan/.env
TOMATOPLAN_DEFAULT_ADMIN_ENABLED=false
```

Puis redémarrez:

```bash
systemctl restart tomatoplan
```

### 10.3 Vérifier les logs régulièrement

```bash
# Logs TomatoPlan
tail -f /opt/tomatoplan/logs/server.log

# Logs nginx
tail -f /var/log/nginx/tomatoplan_access.log
tail -f /var/log/nginx/tomatoplan_error.log

# Tentatives de connexion échouées
grep "LOGIN_FAILED" /opt/tomatoplan/logs/server.log
```

---

## 11. Maintenance

### 11.1 Redémarrer le serveur

```bash
systemctl restart tomatoplan
systemctl restart nginx
```

### 11.2 Voir les logs en temps réel

```bash
journalctl -u tomatoplan -f
```

### 11.3 Backup manuel

```bash
su - tomatoplan
cd /opt/tomatoplan
cp data/tomatoplan.db backups/tomatoplan_$(date +%Y%m%d_%H%M%S).db
```

### 11.4 Mise à jour du serveur

```bash
su - tomatoplan
cd /opt/tomatoplan

# Sauvegarder
cp data/tomatoplan.db data/tomatoplan_backup.db

# Mettre à jour
git pull

# Mettre à jour les dépendances
source venv/bin/activate
pip install -r requirements.txt

# Redémarrer
exit
systemctl restart tomatoplan
```

### 11.5 Renouveler le certificat Let's Encrypt

```bash
certbot renew
```

### 11.6 Réinitialiser un mot de passe utilisateur

```bash
su - tomatoplan
cd /opt/tomatoplan
source venv/bin/activate

python3 << 'EOF'
import asyncio
from server.database import async_session_maker
from server.services.auth_service import AuthService

async def reset_password():
    async with async_session_maker() as db:
        USERNAME = "JEAN.DUPONT"  # Utilisateur à réinitialiser

        user = await AuthService.get_user_by_username(db, USERNAME)
        if user:
            temp_pwd = await AuthService.admin_reset_password(db, user)
            print(f"Nouveau mot de passe pour {USERNAME}: {temp_pwd}")
        else:
            print(f"Utilisateur {USERNAME} non trouvé")

asyncio.run(reset_password())
EOF
```

---

## Résumé des accès

| Service | URL | Port |
|---------|-----|------|
| API HTTPS | https://VOTRE_IP/api | 443 |
| Documentation | https://VOTRE_IP/docs | 443 |
| Health check | https://VOTRE_IP/health | 443 |

---

## Support

En cas de problème:

1. Vérifier les logs: `journalctl -u tomatoplan -n 50`
2. Vérifier nginx: `nginx -t && systemctl status nginx`
3. Vérifier le firewall: `ufw status` ou `firewall-cmd --list-all`
4. Tester en local: `curl http://127.0.0.1:8000/health`

---

*Guide pour TomatoPlan Server v1.0.0 - Déploiement Internet sécurisé*
