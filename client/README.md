# TomatoPlan Client

Client Python pour TomatoPlan avec architecture client-serveur et synchronisation temps reel multi-utilisateur.

## Structure

```
client/
├── TomatoPlan_Client.py   # Application principale (point d'entree)
├── config.py              # Configuration (serveur, timeouts, etc.)
├── api_client.py          # Client API et WebSocket
├── requirements.txt       # Dependances Python
└── README.md              # Documentation
```

## Pre-requis

- Windows 10/11 (ou Linux/Mac)
- Python 3.8 ou superieur
- PTT_v0.6.0.py dans le dossier parent
- Connexion Internet

## Installation

### Methode 1: Script automatique (Windows)

1. Telecharger le depot complet
2. Aller dans le dossier `client/`
3. Double-cliquer sur `install_windows.bat`
4. Suivre les instructions

### Methode 2: Manuelle

1. Installer Python depuis https://www.python.org/downloads/
   - **Important**: Cocher "Add Python to PATH"

2. Installer les dependances:
   ```bash
   cd chemin/vers/tomatoplan_serveur/client
   pip install -r requirements.txt
   ```

3. Lancer l'application:
   ```bash
   python TomatoPlan_Client.py
   ```

## Lancement

```bash
python TomatoPlan_Client.py
```

Ou via le fichier `Lancer_TomatoPlan.bat` (Windows).

## Configuration

Editez `config.py` pour modifier les parametres:

```python
# URL du serveur TomatoPlan
SERVER_URL = "https://54.37.231.92"

# Verification SSL (False pour certificats auto-signes)
VERIFY_SSL = False

# Timeout des requetes (secondes)
TIMEOUT = 30
```

## Utilisation

### Connexion

1. Lancer l'application
2. Entrer votre nom d'utilisateur
3. Entrer votre mot de passe
4. Cliquer sur "Connexion"

### Premiere connexion

1. Utilisez le mot de passe temporaire fourni par l'administrateur
2. L'application vous demandera de changer votre mot de passe
3. Le nouveau mot de passe doit contenir:
   - Au moins 8 caracteres
   - Une majuscule, une minuscule, un chiffre

### Synchronisation temps reel

L'application se synchronise automatiquement:
- Indicateur de statut: **En ligne** / **Hors ligne**
- Nombre d'utilisateurs connectes affiche
- Rafraichissement automatique quand un autre utilisateur modifie des donnees

### Fonctionnalites

Interface 100% identique a PTT v0.6.0:

- **Planning** - Gestion des missions par date
- **Suivi missions** - Suivi en temps reel
- **Chauffeurs** - Gestion et disponibilites
- **Voyages** - Configuration des destinations
- **Finance** - Tarifs SST, revenus palettes
- **Analyse** - Graphiques et statistiques
- **Admin** - Generation de planning
- **Droits** - Gestion des utilisateurs
- **SAURON** - Logs d'activite

## Dependances

**Requises:**
- requests
- urllib3
- websocket-client

**Optionnelles (pour toutes les fonctionnalites PTT):**
```bash
pip install openpyxl    # Export Excel
pip install reportlab   # Export PDF
pip install matplotlib  # Graphiques
pip install pywin32     # Integration Outlook (Windows)
```

## Problemes courants

### "Impossible de se connecter au serveur"
- Verifiez votre connexion Internet
- Verifiez que le serveur est accessible

### "PTT_v0.6.0.py non trouve"
- Assurez-vous que PTT_v0.6.0.py est dans le dossier parent de client/

### "Module not found"
- Lancez depuis le dossier client/
- Ou utilisez le fichier .bat fourni

### "Certificat SSL invalide"
- Normal pour les certificats auto-signes
- VERIFY_SSL = False est deja configure

## Support

Contactez l'administrateur systeme pour:
- Creation de compte
- Reinitialisation de mot de passe
- Problemes de connexion
