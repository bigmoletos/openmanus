import os
import re
import tomli
import logging
from pathlib import Path

# Import du module de chargement des variables d'environnement
import env_loader

# Configuration du logger
logger = logging.getLogger(__name__)

def load_config(config_path="config/config.toml"):
    """
    Charge la configuration depuis un fichier TOML et remplace les variables
    d'environnement référencées.

    Args:
        config_path (str): Chemin vers le fichier de configuration TOML.

    Returns:
        dict: Configuration avec les variables d'environnement substituées.

    Raises:
        FileNotFoundError: Si le fichier de configuration n'existe pas.
        ValueError: Si une variable d'environnement référencée n'est pas définie.
    """
    try:
        # Vérifier que le fichier existe
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Le fichier de configuration {config_path} n'existe pas.")

        # Lire le fichier de configuration
        with open(config_file, "rb") as f:
            config = tomli.load(f)

        # Parcourir récursivement la configuration pour remplacer les variables d'environnement
        config = _substitute_env_vars(config)

        logger.info(f"Configuration chargée avec succès depuis {config_path}")
        return config

    except Exception as e:
        logger.error(f"Erreur lors du chargement de la configuration: {e}")
        raise

def _substitute_env_vars(config):
    """
    Substitue récursivement les références aux variables d'environnement dans la configuration.

    Args:
        config: Élément de configuration (dictionnaire, liste, chaîne, etc.)

    Returns:
        Le même type d'élément avec les variables d'environnement substituées.
    """
    if isinstance(config, dict):
        return {k: _substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_substitute_env_vars(v) for v in config]
    elif isinstance(config, str):
        # Remplacer ${VAR} par la valeur de la variable d'environnement
        pattern = r'\${([A-Za-z0-9_]+)}'

        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                logger.warning(f"Variable d'environnement '{var_name}' non définie")
                return f"${{{var_name}}}"  # Garder la référence si la variable n'est pas définie
            return env_value

        return re.sub(pattern, replace_env_var, config)
    else:
        return config

# Exemple d'utilisation
if __name__ == "__main__":
    # Configuration basique du logging
    logging.basicConfig(level=logging.INFO)

    try:
        # Charger la configuration
        config = load_config()
        print("Configuration chargée avec succès !")

        # Afficher la configuration chargée (sans les clés API pour la sécurité)
        safe_config = config.copy()
        if "llm" in safe_config and "api_key" in safe_config["llm"]:
            safe_config["llm"]["api_key"] = "[MASQUÉ]"
        if "llm" in safe_config and "vision" in safe_config["llm"] and "api_key" in safe_config["llm"]["vision"]:
            safe_config["llm"]["vision"]["api_key"] = "[MASQUÉ]"

        import json
        print(json.dumps(safe_config, indent=2))

    except Exception as e:
        logger.error(f"Erreur: {e}")