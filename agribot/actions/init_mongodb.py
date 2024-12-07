from pymongo import MongoClient
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration de la base de données
DB_NAME = 'AGRICULTURAL_DATA'
MONGO_URI = 'mongodb://localhost:27017/'


def init_mongodb():
    """Initialise la base de données MongoDB avec la structure requise."""
    try:
        # Connexion à MongoDB
        mongo_client = MongoClient(MONGO_URI)
        agricultural_db = mongo_client[DB_NAME]

        # Créer ou vider les collections
        agricultural_db.suggerer_culture.drop()
        agricultural_db.problemes_courants.drop()
        agricultural_db.conseils_culture.drop()
        agricultural_db.conversations.drop()

        # Créer les collections avec validation
        agricultural_db.create_collection('suggerer_culture', validator={
            '$jsonSchema': {
                'bsonType': 'object',
                'required': ['zone'],
                'properties': {
                    'zone': {
                        'bsonType': 'string',
                        'description': 'Nom de la zone agricole'
                    },
                    'data': {
                        'bsonType': 'object',
                        'description': 'Données de culture par zone'
                    }
                }
            }
        })

        agricultural_db.create_collection('problemes_courants', validator={
            '$jsonSchema': {
                'bsonType': 'object',
                'properties': {
                    'maladies': {
                        'bsonType': 'object',
                        'description': 'Informations sur les maladies des cultures'
                    }
                }
            }
        })

        agricultural_db.create_collection('conseils_culture', validator={
            '$jsonSchema': {
                'bsonType': 'object',
                'required': ['culture', 'data'],
                'properties': {
                    'culture': {
                        'bsonType': 'string',
                        'description': 'Nom de la culture'
                    },
                    'data': {
                        'bsonType': 'object',
                        'description': 'Conseils pour la culture'
                    }
                }
            }
        })

        agricultural_db.create_collection('conversations', validator={
            '$jsonSchema': {
                'bsonType': 'object',
                'required': ['conversation_id', 'timestamp', 'history'],
                'properties': {
                    'conversation_id': {
                        'bsonType': 'string',
                        'description': 'Identifiant unique de la conversation'
                    },
                    'timestamp': {
                        'bsonType': 'string',
                        'description': 'Date et heure de la conversation'
                    },
                    'slots': {
                        'bsonType': 'object',
                        'description': 'État des slots pendant la conversation'
                    },
                    'history': {
                        'bsonType': 'array',
                        'description': 'Historique des messages'
                    }
                }
            }
        })

        logger.info(f"Base de données '{DB_NAME}' initialisée avec succès!")

        # Créer les index
        agricultural_db.suggerer_culture.create_index('zone', unique=True)
        agricultural_db.conseils_culture.create_index('culture', unique=True)
        agricultural_db.conversations.create_index('conversation_id')
        agricultural_db.conversations.create_index('timestamp')

        logger.info("Index créés avec succès!")

        return True, agricultural_db

    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {str(e)}")
        return False, None


def verify_mongodb_structure(database):
    """Vérifie que la structure de la base de données est correcte."""
    try:
        # Vérifier les collections
        collections = database.list_collection_names()
        required_collections = [
            'suggerer_culture',
            'problemes_courants',
            'conseils_culture',
            'conversations'
        ]

        for collection in required_collections:
            if collection not in collections:
                logger.error(f"Collection manquante: {collection}")
                return False

            # Vérifier qu'il y a des documents dans chaque collection
            count = database[collection].count_documents({})
            logger.info(f"Collection {collection}: {count} documents")

        return True

    except Exception as e:
        logger.error(f"Erreur lors de la vérification: {str(e)}")
        return False


if __name__ == "__main__":
    # Initialiser la base de données
    initialization_success, created_db = init_mongodb()

    if initialization_success and created_db is not None:
        print(f"Base de données '{DB_NAME}' initialisée avec succès!")

        # Vérifier la structure
        if verify_mongodb_structure(created_db):
            print("Structure de la base de données vérifiée avec succès!")
        else:
            print("Erreur lors de la vérification de la structure.")
    else:
        print("Erreur lors de l'initialisation de la base de données.")
