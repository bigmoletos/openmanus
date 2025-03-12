import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configuration du logger
logger = logging.getLogger(__name__)

def load_environment_variables(env_path=None):
    """
    Charge les variables d'environnement depuis un fichier .env.

    Args:
        env_path (str, optional): Chemin vers le fichier .env.
            Si None, recherche dans le répertoire courant.

    Returns:
        bool: True si le chargement a réussi, False sinon.
    """
    try:
        # Si aucun chemin spécifique n'est fourni, utiliser le répertoire courant
        if env_path is None:
            env_path = Path('.env')

        # Charger les variables d'environnement
        load_result = load_dotenv(env_path)

        if load_result:
            logger.info(f"Variables d'environnement chargées avec succès depuis {env_path}")
        else:
            logger.warning(f"Aucune variable d'environnement chargée depuis {env_path}")

        return load_result

    except Exception as e:
        logger.error(f"Erreur lors du chargement des variables d'environnement: {e}")
        return False

# Charger les variables d'environnement au moment de l'importation du module
load_environment_variables()