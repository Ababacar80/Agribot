import json
import logging
from pymongo import MongoClient
from pymongo.errors import OperationFailure

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration de la base de données
DB_NAME = 'agricultural_data'
MONGO_URI = 'mongodb://localhost:27017/'
DEFAULT_JSON_PATH = "C:/Users/asus/Documents/Agribot/agribot/actions/agricultural_data.json"


def migrate_json_to_mongodb(source_file: str) -> bool:
    """Migre les données d'un fichier JSON vers MongoDB."""
    try:
        # Lire le fichier JSON
        logger.info(f"Lecture du fichier JSON: {source_file}")
        with open(source_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # Établir la connexion MongoDB
        mongo_client = MongoClient(MONGO_URI)
        agricultural_db = mongo_client[DB_NAME]

        # Migration des données de suggestion de culture
        logger.info("Migration des données de suggestion de culture...")
        for zone, data in json_data.get('suggerer_culture', {}).items():
            agricultural_db.suggerer_culture.insert_one({
                'zone': zone,
                'data': data
            })

        # Migration des problèmes courants
        logger.info("Migration des données des problèmes courants...")
        agricultural_db.problemes_courants.insert_one({
            'maladies': json_data.get('problemes_courants', {}).get('maladies', {})
        })

        # Migration des conseils de culture
        logger.info("Migration des conseils de culture...")
        for culture, data in json_data.get('conseils_culture', {}).items():
            agricultural_db.conseils_culture.insert_one({
                'culture': culture,
                'data': data
            })

        # Vérification de la migration
        suggest_count = agricultural_db.suggerer_culture.count_documents({})
        problemes_count = agricultural_db.problemes_courants.count_documents({})
        conseils_count = agricultural_db.conseils_culture.count_documents({})

        logger.info("Migration terminée avec succès:")
        logger.info(f"- {suggest_count} zones dans suggerer_culture")
        logger.info(f"- {problemes_count} documents dans problemes_courants")
        logger.info(f"- {conseils_count} cultures dans conseils_culture")

        # Vérification des données migrées
        verify_data_integrity(agricultural_db, json_data)

        return True

    except FileNotFoundError:
        logger.error(f"Fichier JSON non trouvé: {source_file}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Erreur de décodage JSON: {str(e)}")
        return False
    except ConnectionError as e:
        logger.error(f"Erreur de connexion à MongoDB: {str(e)}")
        return False
    except OperationFailure as e:
        logger.error(f"Erreur d'opération MongoDB: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Erreur inattendue lors de la migration: {str(e)}")
        return False


def verify_data_integrity(database, original_data: dict) -> bool:
    """Vérifie l'intégrité des données migrées."""
    try:
        # Vérification des suggestions de culture
        zones_count = len(original_data.get('suggerer_culture', {}))
        migrated_zones = database.suggerer_culture.count_documents({})
        if zones_count != migrated_zones:
            logger.warning(f"Différence dans le nombre de zones: {zones_count} (original) vs {migrated_zones} (migré)")
            return False

        # Vérification des problèmes courants
        if not database.problemes_courants.find_one({}):
            logger.warning("Données des problèmes courants manquantes")
            return False

        # Vérification des conseils de culture
        cultures_count = len(original_data.get('conseils_culture', {}))
        migrated_cultures = database.conseils_culture.count_documents({})
        if cultures_count != migrated_cultures:
            logger.warning(
                f"Différence dans le nombre de cultures: {cultures_count} (original) vs {migrated_cultures} (migré)")
            return False

        logger.info("Vérification de l'intégrité des données réussie")
        return True

    except Exception as e:
        logger.error(f"Erreur lors de la vérification des données: {str(e)}")
        return False


if __name__ == "__main__":
    # Lancer la migration
    migration_success = migrate_json_to_mongodb(DEFAULT_JSON_PATH)

    if migration_success:
        print("Migration terminée avec succès! Vérifiez les logs pour les détails.")
    else:
        print("La migration a échoué. Consultez les logs pour plus de détails.")
