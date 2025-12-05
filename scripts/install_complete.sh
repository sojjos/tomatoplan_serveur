#!/bin/bash
#
# TomatoPlan - Script d'installation automatique complète
# Pour Ubuntu Server 22.04 LTS
#
# Usage: sudo bash install_complete.sh
#
# IP du serveur: 54.37.231.92
#

set -e

# ============================================================
# CONFIGURATION - MODIFIEZ SI NÉCESSAIRE
# ============================================================
SERVER_IP="54.37.231.92"
APP_USER="tomatoplan"
APP_DIR="/home/${APP_USER}/tomatoplan_serveur"
REPO_URL="https://github.com/sojjos/tomatoplan_serveur.git"
ADMIN_USERNAME="ADMIN"

# ============================================================
# COULEURS
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() {
    echo -e "\n${BLUE}===================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}===================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ============================================================
# VÉRIFICATIONS
# ============================================================
if [ "$EUID" -ne 0 ]; then
    print_error "Ce script doit être exécuté en tant que root (sudo)"
    exit 1
fi

if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    print_warning "Ce script est conçu pour Ubuntu. Continuez à vos risques."
fi

print_step "Installation TomatoPlan sur ${SERVER_IP}"
echo "Ce script va installer et configurer automatiquement :"
echo "  - Python 3, pip, venv"
echo "  - nginx avec HTTPS (certificat auto-signé)"
echo "  - Pare-feu UFW"
echo "  - Service systemd"
echo "  - TomatoPlan Server"
echo ""
read -p "Continuer ? (o/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Oo]$ ]]; then
    exit 1
fi

# ============================================================
# ÉTAPE 1 : Mise à jour système
# ============================================================
print_step "Étape 1/10 : Mise à jour du système"
apt update
apt upgrade -y
print_success "Système mis à jour"

# ============================================================
# ÉTAPE 2 : Installation des dépendances
# ============================================================
print_step "Étape 2/10 : Installation des dépendances"
apt install -y python3 python3-pip python3-venv git nginx ufw openssl curl
print_success "Dépendances installées"

# ============================================================
# ÉTAPE 3 : Création de l'utilisateur
# ============================================================
print_step "Étape 3/10 : Création de l'utilisateur ${APP_USER}"
if id "$APP_USER" &>/dev/null; then
    print_warning "L'utilisateur ${APP_USER} existe déjà"
else
    useradd -m -s /bin/bash "$APP_USER"
    print_success "Utilisateur ${APP_USER} créé"
fi

# ============================================================
# ÉTAPE 4 : Configuration du pare-feu
# ============================================================
print_step "Étape 4/10 : Configuration du pare-feu"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
print_success "Pare-feu configuré (SSH, HTTP, HTTPS)"

# ============================================================
# ÉTAPE 5 : Téléchargement du projet
# ============================================================
print_step "Étape 5/10 : Téléchargement du projet"
if [ -d "$APP_DIR" ]; then
    print_warning "Le dossier existe, mise à jour..."
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull || true
else
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
fi
print_success "Projet téléchargé"

# ============================================================
# ÉTAPE 6 : Configuration Python
# ============================================================
print_step "Étape 6/10 : Configuration de l'environnement Python"
cd "$APP_DIR"

# Créer l'environnement virtuel
sudo -u "$APP_USER" python3 -m venv venv

# Installer les dépendances
sudo -u "$APP_USER" ./venv/bin/pip install --upgrade pip
sudo -u "$APP_USER" ./venv/bin/pip install -r requirements.txt

print_success "Environnement Python configuré"

# ============================================================
# ÉTAPE 7 : Configuration de l'application
# ============================================================
print_step "Étape 7/10 : Configuration de l'application"

# Générer une clé secrète
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

# Créer le fichier .env
cat > "$APP_DIR/.env" << EOF
# Configuration TomatoPlan
# Généré automatiquement le $(date)

# Serveur
TOMATOPLAN_HOST=127.0.0.1
TOMATOPLAN_PORT=8000

# Sécurité
TOMATOPLAN_SECRET_KEY=${SECRET_KEY}

# Base de données
TOMATOPLAN_DATABASE_PATH=./data/tomatoplan.db

# Admin par défaut
TOMATOPLAN_DEFAULT_ADMIN_USERNAME=${ADMIN_USERNAME}

# Logs
TOMATOPLAN_LOG_LEVEL=INFO
EOF

# Créer les dossiers
sudo -u "$APP_USER" mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/backups"

# Permissions
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

print_success "Application configurée"

# ============================================================
# ÉTAPE 8 : Certificat SSL auto-signé
# ============================================================
print_step "Étape 8/10 : Création du certificat SSL"
mkdir -p /etc/nginx/ssl

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/tomatoplan.key \
    -out /etc/nginx/ssl/tomatoplan.crt \
    -subj "/CN=${SERVER_IP}/O=TomatoPlan/C=FR" 2>/dev/null

chmod 600 /etc/nginx/ssl/tomatoplan.key
print_success "Certificat SSL créé"

# ============================================================
# ÉTAPE 9 : Configuration nginx
# ============================================================
print_step "Étape 9/10 : Configuration de nginx"

cat > /etc/nginx/sites-available/tomatoplan << EOF
# TomatoPlan - Configuration nginx
# Serveur: ${SERVER_IP}

limit_req_zone \$binary_remote_addr zone=api:10m rate=10r/s;

server {
    listen 443 ssl;
    server_name ${SERVER_IP};

    ssl_certificate /etc/nginx/ssl/tomatoplan.crt;
    ssl_certificate_key /etc/nginx/ssl/tomatoplan.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    client_max_body_size 10M;

    location / {
        limit_req zone=api burst=20 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}

server {
    listen 80;
    server_name ${SERVER_IP};
    return 301 https://\$server_name\$request_uri;
}
EOF

# Activer le site
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/tomatoplan /etc/nginx/sites-enabled/

# Tester et redémarrer
nginx -t
systemctl restart nginx
systemctl enable nginx

print_success "nginx configuré"

# ============================================================
# ÉTAPE 10 : Service systemd
# ============================================================
print_step "Étape 10/10 : Configuration du service systemd"

cat > /etc/systemd/system/tomatoplan.service << EOF
[Unit]
Description=TomatoPlan API Server
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tomatoplan
systemctl start tomatoplan

# Attendre que le service démarre
sleep 3

print_success "Service tomatoplan configuré et démarré"

# ============================================================
# VÉRIFICATION FINALE
# ============================================================
print_step "Vérification de l'installation"

# Vérifier le service
if systemctl is-active --quiet tomatoplan; then
    print_success "Service TomatoPlan: ACTIF"
else
    print_error "Service TomatoPlan: INACTIF"
    journalctl -u tomatoplan -n 20
fi

# Vérifier nginx
if systemctl is-active --quiet nginx; then
    print_success "Service nginx: ACTIF"
else
    print_error "Service nginx: INACTIF"
fi

# Tester l'API
sleep 2
if curl -sk "https://127.0.0.1/health" | grep -q "healthy"; then
    print_success "API: FONCTIONNELLE"
else
    print_warning "API: En attente de démarrage..."
fi

# ============================================================
# RÉCUPÉRER LE MOT DE PASSE ADMIN
# ============================================================
print_step "Informations de connexion"

echo -e "${YELLOW}Recherche du mot de passe admin temporaire...${NC}"
sleep 2

# Chercher dans les logs
TEMP_PASSWORD=$(journalctl -u tomatoplan --no-pager | grep -oP "(?<=temporaire[: ]+)[A-Za-z0-9_-]{12,}" | tail -1)

if [ -z "$TEMP_PASSWORD" ]; then
    TEMP_PASSWORD=$(journalctl -u tomatoplan --no-pager | grep -oP "(?<=password[: ]+)[A-Za-z0-9_-]{12,}" | tail -1)
fi

# ============================================================
# RÉSUMÉ FINAL
# ============================================================
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  INSTALLATION TERMINÉE !${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  ${BLUE}Serveur:${NC} https://${SERVER_IP}"
echo -e "  ${BLUE}API Docs:${NC} https://${SERVER_IP}/docs"
echo -e "  ${BLUE}Admin:${NC} https://${SERVER_IP}/admin"
echo ""
echo -e "  ${BLUE}Identifiants admin:${NC}"
echo -e "    Username: ${YELLOW}${ADMIN_USERNAME}${NC}"
if [ -n "$TEMP_PASSWORD" ]; then
    echo -e "    Password: ${YELLOW}${TEMP_PASSWORD}${NC}"
else
    echo -e "    Password: ${YELLOW}(voir les logs ci-dessous)${NC}"
    echo ""
    echo -e "  Pour voir le mot de passe temporaire:"
    echo -e "    ${BLUE}sudo journalctl -u tomatoplan | grep -i password${NC}"
fi
echo ""
echo -e "  ${RED}IMPORTANT: Changez le mot de passe après la première connexion !${NC}"
echo ""
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  ${BLUE}Commandes utiles:${NC}"
echo -e "    Voir les logs:      sudo journalctl -u tomatoplan -f"
echo -e "    Redémarrer:         sudo systemctl restart tomatoplan"
echo -e "    Status:             sudo systemctl status tomatoplan"
echo ""
echo -e "  ${BLUE}Configuration client Windows:${NC}"
echo -e "    SERVER_URL = \"https://${SERVER_IP}\""
echo -e "    client = TomatoPlanClient(SERVER_URL, verify_ssl=False)"
echo ""
