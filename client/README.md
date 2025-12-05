# TomatoPlan Client

Client Python pour TomatoPlan avec architecture client-serveur.

## Pre-requis

- Windows 10/11
- Python 3.8 ou superieur
- Connexion Internet

## Installation

### Methode 1: Automatique (recommandee)

1. Telecharger le dossier `client/` sur votre PC
2. Double-cliquer sur `install_windows.bat`
3. Suivre les instructions

### Methode 2: Manuelle

1. Installer Python depuis https://www.python.org/downloads/
   - **Important**: Cocher "Add Python to PATH"

2. Ouvrir un terminal (cmd) et installer les dependances:
   ```
   cd chemin/vers/client
   pip install -r requirements.txt
   ```

3. Lancer l'application:
   ```
   python PTT_Client.py
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

### Interface

L'interface est identique a l'application PTT originale avec:
- **Planning**: Gestion des missions par date
- **Chauffeurs**: Liste et gestion des chauffeurs
- **Voyages**: Configuration des destinations

## Configuration

Pour modifier l'adresse du serveur, editez le fichier `PTT_Client.py`:

```python
SERVER_URL = "https://54.37.231.92"  # Votre serveur
VERIFY_SSL = False  # False pour certificats auto-signes
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

## Support

Contactez l'administrateur systeme pour:
- Creation de compte
- Reinitialisation de mot de passe
- Problemes de connexion
