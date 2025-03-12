# Sécurisation des Secrets avec Variables d'Environnement

Ce document explique comment les informations sensibles comme les clés API ont été sécurisées en les déplaçant du fichier `config.toml` vers un fichier `.env` protégé.

## Vue d'ensemble

Le système utilise désormais un fichier `.env` pour stocker les informations sensibles (comme les clés API), tandis que le fichier `config.toml` contient uniquement des références à ces variables d'environnement.

## Fichiers créés ou modifiés

1. **`.env`** - Stocke les secrets et informations sensibles
2. **`env_loader.py`** - Charge les variables d'environnement depuis `.env`
3. **`config_loader.py`** - Charge la configuration depuis `config.toml` et remplace les références aux variables d'environnement
4. **`config/config.toml`** - Modifié pour utiliser des références aux variables d'environnement
5. **`config/config.example.toml`** - Exemple de configuration mis à jour
6. **`requirements.txt`** - Ajout des dépendances `python-dotenv` et `tomli`

## Configuration

### 1. Fichier .env

Le fichier `.env` contient toutes les variables sensibles :

```
# OpenAI API Configuration
OPENAI_API_KEY=sk-...

# Azure OpenAI Configuration
AZURE_API_KEY=YOUR_AZURE_API_KEY
AZURE_ENDPOINT=YOUR_AZURE_ENDPOINT
AZURE_DEPLOYMENT_ID=AZURE_DEPOLYMENT_ID
AZURE_API_VERSION=2024-08-01-preview

# Amazon API Configuration
AMAZON_API_KEY=your-amazon-api-key
AMAZON_API_SECRET=your-amazon-api-secret

# OVH API Configuration
OVH_API_KEY=your-ovh-api-key
OVH_APP_SECRET=your-ovh-app-secret
OVH_CONSUMER_KEY=your-ovh-consumer-key

# Mistral AI Configuration
MISTRAL_API_KEY=your-mistral-api-key

# Anthropic Claude Configuration
CLAUDE_API_KEY=your-claude-api-key

# Fluke API Configuration
FLUKE_API_KEY=your-fluke-api-key
```

### 2. Fichier config.toml

Le fichier `config.toml` utilise maintenant des références aux variables d'environnement :

```toml
[llm]
model = "claude-3-5-sonnet"
base_url = "https://api.openai.com/v1"
api_key = "${OPENAI_API_KEY}"
max_tokens = 4096
temperature = 0.0

# ...
```

## Utilisation

### Chargement de la configuration

Pour charger la configuration avec les variables d'environnement résolues :

```python
import config_loader

# Charger la configuration
config = config_loader.load_config()

# Utiliser la configuration
openai_api_key = config["llm"]["api_key"]
```

### Ajout de nouvelles variables sensibles

1. Ajoutez la variable dans le fichier `.env` :
   ```
   NOUVELLE_VARIABLE_SECRETE=valeur_secrete
   ```

2. Référencez-la dans `config.toml` en utilisant la syntaxe `${VARIABLE}` :
   ```toml
   nouvelle_option = "${NOUVELLE_VARIABLE_SECRETE}"
   ```

## Services externes configurés

Le système prend en charge les services externes suivants :

- **OpenAI API** : Accès aux modèles GPT via l'API OpenAI
- **Azure OpenAI** : Accès aux modèles GPT hébergés sur Azure
- **Amazon** : Services AWS nécessitant une authentification
- **OVH** : Services d'hébergement et API OVH
- **Mistral AI** : Accès aux modèles d'IA de Mistral
- **Anthropic Claude** : Accès aux modèles d'IA Claude d'Anthropic
- **Fluke** : Services et API Fluke

## Sécurité

- Le fichier `.env` est automatiquement ignoré par Git grâce à l'entrée dans `.gitignore`.
- Ne committez jamais le fichier `.env` dans le dépôt Git.
- Pour le déploiement, configurez les variables d'environnement directement sur le serveur plutôt que de copier le fichier `.env`.

## Recommandations pour le développement local

1. Copiez le fichier `.env.example` en `.env` :
   ```bash
   cp .env.example .env
   ```

2. Modifiez le fichier `.env` pour y mettre vos propres valeurs.

3. Assurez-vous de ne jamais committer le fichier `.env` dans le dépôt Git.

## Dépendances

- `python-dotenv` : Pour charger les variables d'environnement depuis `.env`
- `tomli` : Pour lire les fichiers TOML