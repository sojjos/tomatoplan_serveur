#!/bin/bash
#
# TomatoPlan Server - Script d'installation
#
# Usage: ./install.sh [options]
#
# Options:
#   --port PORT       Port d'écoute (défaut: 8000)
#   --db-path PATH    Chemin de la base de données (défaut: ./data/tomatoplan.db)
#   --admin USER      Nom d'utilisateur admin par défaut (défaut: ADMIN)
#   --import-dir DIR  Dossier contenant les fichiers JSON à importer
#   --no-service      Ne pas installer le service systemd
#   --help            Afficher l'aide
#

set -e

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration par défaut
PORT=8000
DB_PATH="./data/tomatoplan.db"
ADMIN_USER="ADMIN"
IMPORT_DIR=""
INSTALL_SERVICE=true
INSTALL_DIR=$(pwd)

# Fonction d'affichage
print_header() {
    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}   TomatoPlan Server - Installation${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[*]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[X]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

# Afficher l'aide
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --port PORT       Port d'écoute (défaut: 8000)"
    echo "  --db-path PATH    Chemin de la base de données"
    echo "  --admin USER      Nom d'utilisateur admin par défaut"
    echo "  --import-dir DIR  Dossier contenant les fichiers JSON à importer"
    echo "  --no-service      Ne pas installer le service systemd"
    echo "  --help            Afficher cette aide"
    echo ""
    echo "Exemple:"
    echo "  $0 --port 8080 --admin MON_USER"
    exit 0
}

# Parser les arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --db-path)
            DB_PATH="$2"
            shift 2
            ;;
        --admin)
            ADMIN_USER="$2"
            shift 2
            ;;
        --import-dir)
            IMPORT_DIR="$2"
            shift 2
            ;;
        --no-service)
            INSTALL_SERVICE=false
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            print_error "Option inconnue: $1"
            show_help
            ;;
    esac
done

print_header

# Vérifier qu'on est root pour installer le service
if [ "$INSTALL_SERVICE" = true ] && [ "$EUID" -ne 0 ]; then
    print_warning "Pour installer le service systemd, exécutez avec sudo"
    print_warning "Ou utilisez --no-service pour ignorer"
    INSTALL_SERVICE=false
fi

# Étape 1: Vérifier Python
print_step "Vérification de Python..."
if command -v python3 &> /dev/null; then
    PYTHON=$(command -v python3)
    PYTHON_VERSION=$($PYTHON --version 2>&1)
    print_success "Python trouvé: $PYTHON_VERSION"
else
    print_error "Python 3 n'est pas installé!"
    echo "Installez Python 3.9+ avec:"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-pip python3-venv"
    echo "  RHEL/CentOS:   sudo dnf install python3 python3-pip"
    exit 1
fi

# Vérifier la version de Python (3.9+)
PYTHON_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    print_error "Python 3.9+ requis (trouvé: $PYTHON_MAJOR.$PYTHON_MINOR)"
    exit 1
fi

# Étape 2: Créer l'environnement virtuel
print_step "Création de l'environnement virtuel..."
if [ -d "venv" ]; then
    print_warning "Environnement virtuel existant trouvé"
else
    $PYTHON -m venv venv
    print_success "Environnement virtuel créé"
fi

# Activer l'environnement virtuel
source venv/bin/activate

# Étape 3: Installer les dépendances
print_step "Installation des dépendances Python..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    print_success "Dépendances installées"
else
    print_error "Erreur lors de l'installation des dépendances"
    exit 1
fi

# Étape 4: Créer les dossiers nécessaires
print_step "Création des dossiers..."
mkdir -p data logs backups
print_success "Dossiers créés: data/, logs/, backups/"

# Étape 5: Créer le fichier de configuration
print_step "Configuration du serveur..."
cat > .env << EOF
# TomatoPlan Server Configuration
# Généré le $(date)

# Serveur
TOMATOPLAN_HOST=0.0.0.0
TOMATOPLAN_PORT=$PORT
TOMATOPLAN_DEBUG=false

# Base de données
TOMATOPLAN_DATABASE_PATH=$DB_PATH

# Admin par défaut
TOMATOPLAN_DEFAULT_ADMIN_USERNAME=$ADMIN_USER
TOMATOPLAN_DEFAULT_ADMIN_ENABLED=true

# Logs
TOMATOPLAN_LOG_LEVEL=INFO
TOMATOPLAN_LOG_FILE=./logs/server.log

# Backup
TOMATOPLAN_BACKUP_DIR=./backups
TOMATOPLAN_BACKUP_RETENTION_DAYS=30
TOMATOPLAN_AUTO_BACKUP_ENABLED=true
TOMATOPLAN_AUTO_BACKUP_HOUR=2
EOF

if [ -n "$IMPORT_DIR" ]; then
    echo "TOMATOPLAN_JSON_IMPORT_DIR=$IMPORT_DIR" >> .env
fi

print_success "Configuration créée: .env"

# Étape 6: Initialiser la base de données
print_step "Initialisation de la base de données..."
$PYTHON -c "
import asyncio
from server.database import init_db, engine, Base
from server.models import *

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Tables créées')

asyncio.run(init())
"

if [ $? -eq 0 ]; then
    print_success "Base de données initialisée"
else
    print_error "Erreur lors de l'initialisation de la base de données"
fi

# Étape 7: Importer les données JSON si spécifié
if [ -n "$IMPORT_DIR" ] && [ -d "$IMPORT_DIR" ]; then
    print_step "Import des données JSON depuis $IMPORT_DIR..."
    # Le script d'import sera créé séparément
    print_warning "Import automatique non implémenté - utilisez l'API /admin/import"
fi

# Étape 8: Installer le service systemd
if [ "$INSTALL_SERVICE" = true ]; then
    print_step "Installation du service systemd..."

    SERVICE_FILE="/etc/systemd/system/tomatoplan.service"
    CURRENT_USER=$(whoami)

    cat > /tmp/tomatoplan.service << EOF
[Unit]
Description=TomatoPlan Server
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo mv /tmp/tomatoplan.service $SERVICE_FILE
    sudo systemctl daemon-reload
    sudo systemctl enable tomatoplan

    print_success "Service systemd installé"
    echo ""
    echo "  Commandes utiles:"
    echo "    sudo systemctl start tomatoplan    # Démarrer le serveur"
    echo "    sudo systemctl stop tomatoplan     # Arrêter le serveur"
    echo "    sudo systemctl restart tomatoplan  # Redémarrer"
    echo "    sudo systemctl status tomatoplan   # Voir le statut"
    echo "    journalctl -u tomatoplan -f        # Voir les logs"
fi

# Étape 9: Créer le script de démarrage manuel
print_step "Création du script de démarrage..."
cat > start.sh << 'EOF'
#!/bin/bash
# Démarrer TomatoPlan Server
cd "$(dirname "$0")"
source venv/bin/activate
python -m uvicorn server.main:app --host 0.0.0.0 --port ${TOMATOPLAN_PORT:-8000}
EOF
chmod +x start.sh

cat > start_dev.sh << 'EOF'
#!/bin/bash
# Démarrer TomatoPlan Server en mode développement (avec reload)
cd "$(dirname "$0")"
source venv/bin/activate
python -m uvicorn server.main:app --host 0.0.0.0 --port ${TOMATOPLAN_PORT:-8000} --reload
EOF
chmod +x start_dev.sh

print_success "Scripts créés: start.sh, start_dev.sh"

# Résumé final
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Installation terminée avec succès!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Configuration:"
echo "  Port:           $PORT"
echo "  Base de données: $DB_PATH"
echo "  Admin:          $ADMIN_USER"
echo ""
echo "Pour démarrer le serveur:"
if [ "$INSTALL_SERVICE" = true ]; then
    echo "  sudo systemctl start tomatoplan"
else
    echo "  ./start.sh"
fi
echo ""
echo "L'interface admin sera disponible sur:"
echo -e "  ${BLUE}http://localhost:$PORT${NC}"
echo ""
echo "Documentation API:"
echo -e "  ${BLUE}http://localhost:$PORT/docs${NC}"
echo ""
