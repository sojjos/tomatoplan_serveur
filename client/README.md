# TomatoPlan Client

Client Python pour TomatoPlan avec architecture client-serveur.

## Versions disponibles

| Version | Fichier | Description |
|---------|---------|-------------|
| **Complet** | `PTT_Client_Full.py` | Interface 100% identique a PTT v0.6.0 original |
| Simple | `PTT_Client.py` | Interface allegee |

## Pre-requis

- Windows 10/11
- Python 3.8 ou superieur
- Connexion Internet

## Installation

### Methode 1: Automatique (recommandee)

1. Telecharger le depot complet sur votre PC
2. Aller dans le dossier `client/`
3. Double-cliquer sur `install_windows.bat`
4. Suivre les instructions

### Methode 2: Manuelle

1. Installer Python depuis https://www.python.org/downloads/
   - **Important**: Cocher "Add Python to PATH"

2. Ouvrir un terminal (cmd) et installer les dependances:
   ```
   cd chemin/vers/tomatoplan_serveur/client
   pip install -r requirements.txt
   ```

3. Lancer l'application:
   ```
   python PTT_Client_Full.py
   ```

## Lancement

Apres installation, utilisez:

- **`Lancer_TomatoPlan.bat`** - Version complete (recommandee)
- `Lancer_TomatoPlan_Simple.bat` - Version simplifiee

Ou en ligne de commande:
```
python PTT_Client_Full.py    # Version complete
python PTT_Client.py         # Version simplifiee
```

## Utilisation

### Connexion

1. Lancer l'application
2. Entrer votre nom d'utilisateur (par defaut: votre login Windows)
3. Entrer votre mot de passe
4. Cliquer sur "Connexion"

### Premiere connexion

Si c'est votre premiere connexion:
1. Utilisez le mot de passe temporaire fourni par l'administrateur
2. L'application vous demandera de changer votre mot de passe
3. Le nouveau mot de passe doit contenir:
   - Au moins 8 caracteres
   - Une majuscule
   - Une minuscule
   - Un chiffre

### Fonctionnalites (Version Complete)

L'interface est 100% identique a PTT v0.6.0 avec tous les onglets:

- **Planning** - Gestion des missions par date
- **Suivi missions** - Suivi en temps reel
- **Chauffeurs** - Gestion des chauffeurs et disponibilites
- **Voyages** - Configuration des destinations
- **Finance** - Tarifs SST, revenus palettes
- **Analyse** - Graphiques et statistiques
- **Admin** - Generation de planning
- **Droits** - Gestion des utilisateurs
- **SAURON** - Logs d'activite

## Configuration

Pour modifier l'adresse du serveur, editez le fichier `api_adapter.py`:

```python
SERVER_URL = "https://54.37.231.92"  # Votre serveur
VERIFY_SSL = False  # False pour certificats auto-signes
```

## Dependances optionnelles

Pour toutes les fonctionnalites:

```
pip install openpyxl    # Export Excel
pip install reportlab   # Export PDF
pip install matplotlib  # Graphiques d'analyse
pip install pywin32     # Integration Outlook
```

## Problemes courants

### "Impossible de se connecter au serveur"
- Verifiez votre connexion Internet
- Verifiez que le serveur est accessible

### "Acces refuse"
- Verifiez vos identifiants
- Contactez l'administrateur pour verifier vos droits

### "Certificat SSL invalide"
- Normal pour les certificats auto-signes
- `VERIFY_SSL = False` est deja configure

### "Module not found: api_adapter"
- Assurez-vous de lancer depuis le dossier client/
- Ou utilisez le fichier .bat fourni

## Support

Contactez l'administrateur systeme pour:
- Creation de compte
- Reinitialisation de mot de passe
- Problemes de connexion
