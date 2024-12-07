import logging
import traceback
from datetime import datetime
from multiprocessing import process
from typing import Any, Text, Dict, List, Optional, Tuple

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset
from thefuzz import fuzz, process

from pymongo import MongoClient

# Configuration MongoDB
DB_NAME = 'agricultural_data'
MONGO_URI = 'mongodb://localhost:27017/'

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Au début du fichier, juste après les imports et la configuration MongoDB
class DataManager:
    _instance = None
    _data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._data is None:
            self._data = self.load_agricultural_data()

    @staticmethod
    def load_agricultural_data() -> Dict:
        """Charge les données agricoles depuis MongoDB."""
        try:
            mongo_client = MongoClient(MONGO_URI)
            db = mongo_client[DB_NAME]

            data = {
                'suggerer_culture': {},
                'problemes_courants': {'maladies': {}},
                'conseils_culture': {}
            }

            # Récupérer les données de suggestion de culture
            for doc in db.suggerer_culture.find({}, {'_id': 0}):
                if 'zone' in doc and 'data' in doc:
                    data['suggerer_culture'][doc['zone']] = doc['data']

            # Récupérer les problèmes courants
            problemes = db.problemes_courants.find_one({}, {'_id': 0})
            if problemes and 'maladies' in problemes:
                data['problemes_courants']['maladies'] = problemes['maladies']

            # Récupérer les conseils de culture
            for doc in db.conseils_culture.find({}, {'_id': 0}):
                if 'culture' in doc and 'data' in doc:
                    data['conseils_culture'][doc['culture']] = doc['data']

            logger.info(f"Données chargées avec succès: {len(data['suggerer_culture'])} zones")
            return data

        except Exception as e:
            logger.error(f"Erreur lors du chargement des données: {str(e)}")
            return {}

    def get_data(self):
        return self._data

    def reload_data(self):
        self._data = self.load_agricultural_data()


# Initialiser les données globales
AGRICULTURAL_DATA = DataManager().get_data()


class ValidateConseilCultureForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_conseil_culture_form"

    @staticmethod
    def fuzzy_match_value(value: str, valid_values: List[str], threshold: int = 70) -> Optional[str]:
        """Utilise fuzzy matching pour valider les entrées."""
        if not value:
            return None
        try:
            match = process.extractOne(value.lower(), valid_values)
            if match and match[1] >= threshold:
                logger.debug(f"Fuzzy match pour '{value}': Meilleur match='{match[0]}' avec score={match[1]}")
                return match[0]
            logger.debug(f"Pas de match suffisant pour '{value}' (meilleur score: {match[1] if match else 'N/A'})")
            return None
        except Exception as e:
            logger.error(f"Erreur fuzzy matching: {str(e)}")
            return None

    async def validate_zone(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Valide la zone de culture."""
        zones_valides = list(AGRICULTURAL_DATA.get('suggerer_culture', {}).keys())
        matched_zone = self.fuzzy_match_value(str(slot_value), zones_valides)

        if matched_zone:
            logger.debug(f"Zone validée: {matched_zone}")
            return {"zone": matched_zone}

        zones_list = ', '.join(zones_valides)
        dispatcher.utter_message(text=f"Zone non reconnue. Choisissez parmi : {zones_list}")
        return {"zone": None}

    async def validate_saison(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Valide la saison de culture."""
        saisons_valides = ["saison des pluies", "saison sèche"]
        matched_saison = self.fuzzy_match_value(str(slot_value), saisons_valides)

        if matched_saison:
            logger.debug(f"Saison validée: {matched_saison}")
            return {"saison": matched_saison}

        dispatcher.utter_message(text="Choisissez entre 'saison des pluies' et 'saison sèche'")
        return {"saison": None}

    async def validate_type_sol(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Valide le type de sol."""
        sols_valides = ["argileux", "sableux"]
        matched_sol = self.fuzzy_match_value(str(slot_value), sols_valides)

        if matched_sol:
            logger.debug(f"Type de sol validé: {matched_sol}")
            return {"type_sol": matched_sol}

        dispatcher.utter_message(text="Choisissez entre 'argileux' et 'sableux'")
        return {"type_sol": None}

    async def validate_objectif_agricole(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Valide l'objectif agricole."""
        if not slot_value:
            dispatcher.utter_message(text="Choisissez entre 'cultures vivrières' et 'cultures de rente'")
            return {"objectif_agricole": None}

        # Normalisation et validation de l'objectif
        value = slot_value.lower().strip()

        # Matching direct
        if "rente" in value:
            logger.debug("Objectif validé: cultures de rente")
            return {"objectif_agricole": "cultures de rente"}
        elif any(x in value for x in ["vivrière", "vivriere", "vivrier"]):
            logger.debug("Objectif validé: cultures vivrières")
            return {"objectif_agricole": "cultures vivrières"}

        # Fuzzy matching si pas de match direct
        objectifs_valides = ["cultures de rente", "cultures vivrières"]
        matched_objectif = self.fuzzy_match_value(value, objectifs_valides, threshold=60)

        if matched_objectif:
            logger.debug(f"Objectif validé par fuzzy matching: {matched_objectif}")
            return {"objectif_agricole": matched_objectif}

        dispatcher.utter_message(text="Choisissez entre 'cultures vivrières' et 'cultures de rente'")
        return {"objectif_agricole": None}

    async def required_slots(
            self,
            domain_slots: List[Text],
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Text]:
        """Définit les slots requis et leur ordre."""
        return ["zone", "saison", "type_sol", "objectif_agricole"]


class ActionSuggererCultures(Action):
    def name(self) -> Text:
        return "action_suggerer_cultures"

    @staticmethod
    def fuzzy_match(input_value: str, choices: list, threshold: int = 70) -> Optional[str]:
        """Fuzzy matching amélioré pour trouver la meilleure correspondance."""
        if not input_value:
            return None
        try:
            match = process.extractOne(input_value.lower(), choices, scorer=fuzz.ratio)
            if match and match[1] >= threshold:
                logger.debug(f"Fuzzy match pour '{input_value}': Meilleur match='{match[0]}' avec score={match[1]}")
                return match[0]
            logger.debug(f"Pas de match suffisant pour '{input_value}'")
            return None
        except Exception as e:
            logger.error(f"Erreur fuzzy matching: {str(e)}")
            return None

    def normalize_parameters(self, tracker: Tracker) -> Dict[str, Optional[str]]:
        """Normalise les paramètres avec fuzzy matching."""
        # Récupération des slots
        zone = tracker.get_slot("zone")
        saison = tracker.get_slot("saison")
        type_sol = tracker.get_slot("type_sol")
        objectif = tracker.get_slot("objectif_agricole")

        # Log des valeurs reçues
        logger.debug(
            f"Valeurs reçues des slots:\nzone: {zone}\nsaison: {saison}\ntype_sol: {type_sol}\nobjectif: {objectif}")

        # Définition des valeurs valides
        zones_valides = list(AGRICULTURAL_DATA.get('suggerer_culture', {}).keys())
        saisons_valides = ["saison des pluies", "saison sèche"]
        sols_valides = ["argileux", "sableux"]

        # Log des valeurs valides
        logger.debug(f"Valeurs valides:\nzones: {zones_valides}\nsaisons: {saisons_valides}\nsols: {sols_valides}")

        # Normalisation de l'objectif
        objectif_norm = None
        if objectif:
            objectif = objectif.lower().strip()
            if "rente" in objectif:
                objectif_norm = "cultures de rente"
            elif any(x in objectif for x in ["vivrière", "vivriere", "vivrier"]):
                objectif_norm = "cultures vivrières"
            else:
                choices = ["cultures de rente", "cultures vivrières"]
                match = process.extractOne(objectif, choices, scorer=fuzz.token_set_ratio)
                if match and match[1] >= 60:
                    objectif_norm = match[0]
                    logger.debug(f"Fuzzy match pour objectif: '{objectif}' -> '{objectif_norm}' (score: {match[1]})")

        # Normalisation avec fuzzy matching pour les autres paramètres
        zone_norm = self.fuzzy_match(zone, zones_valides, threshold=60) if zone else None  # Seuil abaissé pour zone
        saison_norm = self.fuzzy_match(saison, saisons_valides, threshold=60) if saison else None
        type_sol_norm = self.fuzzy_match(type_sol, sols_valides) if type_sol else None

        # Log détaillé des résultats
        logger.debug(
            f"Résultats de la normalisation:\n"
            f"Zone: {zone} -> {zone_norm} (valides: {zones_valides})\n"
            f"Saison: {saison} -> {saison_norm}\n"
            f"Type de sol: {type_sol} -> {type_sol_norm}\n"
            f"Objectif: {objectif} -> {objectif_norm}"
        )

        return {
            "zone": zone_norm,
            "saison": saison_norm,
            "type_sol": type_sol_norm,
            "objectif": objectif_norm
        }

    @staticmethod
    def get_cultures_data(params: Dict[str, str]) -> Optional[List[Dict]]:
        """Récupère les données des cultures pour les paramètres donnés."""
        try:
            return AGRICULTURAL_DATA.get('suggerer_culture', {}).get(params['zone'], {}).get(params['saison'], {}).get(
                params['type_sol'], {}).get(params['objectif'])
        except KeyError as e:
            logger.debug(f"KeyError dans get_cultures_data: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur dans get_cultures_data: {str(e)}")
            return None

    @staticmethod
    def format_culture_message(cultures: List[Dict], params: Dict[str, str]) -> str:
        """Formate le message de recommandation des cultures."""
        message = (f"Pour votre zone {params['zone']} en {params['saison']} "
                   f"avec un sol {params['type_sol']}, voici les cultures "
                   f"recommandées pour {params['objectif']}:\n\n")

        for culture in cultures:
            details = culture.get('details', {})
            message += f"🌱 {culture['nom'].capitalize()}:\n"
            message += f"• Période de plantation: {details.get('periode_plantation')}\n"
            message += f"• Durée du cycle: {details.get('duree_cycle')}\n"
            message += f"• Besoins en eau: {details.get('besoins_eau')}\n"

            if conseils := details.get('conseils'):
                message += "• Conseils de culture:\n"
                for conseil in conseils:
                    message += f"  - {conseil}\n"
            message += "\n"

        return message

    @staticmethod
    def suggest_alternatives(zone: str, saison: str, type_sol: str) -> str:
        """Suggère des alternatives quand la combinaison n'existe pas."""
        suggestions = []

        # Vérifie les sols disponibles pour cette zone et saison
        if zone in AGRICULTURAL_DATA.get('suggerer_culture', {}):
            data_zone = AGRICULTURAL_DATA['suggerer_culture'][zone]
            if saison in data_zone:
                sols_disponibles = list(data_zone[saison].keys())
                if sols_disponibles:
                    suggestions.append(
                        f"Pour {zone} en {saison}, les sols disponibles sont : {', '.join(sols_disponibles)}")

        # Cherche d'autres zones avec le même type de sol
        zones_compatibles = []
        for autre_zone in AGRICULTURAL_DATA.get('suggerer_culture', {}):
            data_zone = AGRICULTURAL_DATA['suggerer_culture'][autre_zone]
            if saison in data_zone:
                if type_sol in data_zone.get(saison, {}):
                    zones_compatibles.append(autre_zone)

        if zones_compatibles:
            suggestions.append(
                f"Le sol {type_sol} est adapté dans ces zones : {', '.join(zones_compatibles)}")

        if not suggestions:
            suggestions.append(
                "Je suggère de consulter un agent agricole local pour des recommandations adaptées.")

        return "\n".join(suggestions)

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        try:
            # Normalisation des paramètres avec fuzzy matching
            params = self.normalize_parameters(tracker)
            logger.debug(f"Paramètres normalisés: {params}")

            # Vérification que tous les paramètres sont valides
            missing_params = [k for k, v in params.items() if v is None]
            if missing_params:
                message = (f"Je n'ai pas bien compris les informations suivantes : "
                           f"{', '.join(missing_params)}. Je peux pas vous fournir de suggestions.")
                dispatcher.utter_message(text=message)
                return [AllSlotsReset()]

            # Récupération des cultures
            cultures = self.get_cultures_data(params)
            if not cultures:
                alternatives = self.suggest_alternatives(
                    params["zone"], params["saison"], params["type_sol"])
                dispatcher.utter_message(
                    text=f"Pas de cultures disponibles pour cette combinaison.\n{alternatives}")
                return [AllSlotsReset()]

            # Formation et envoi du message
            message = self.format_culture_message(cultures, params)
            dispatcher.utter_message(text=message)

            return [SlotSet("cultures_suggerees", [c['nom'] for c in cultures])]

        except Exception as e:
            logger.error(f"Erreur: {str(e)}\n{traceback.format_exc()}")
            dispatcher.utter_message(
                text="Une erreur s'est produite. Pouvons-nous recommencer ?")
            return [AllSlotsReset()]


class ActionConseilSpecifique(Action):
    def name(self) -> Text:
        return "action_conseil_specifique"

    @staticmethod
    def fuzzy_match_culture(value: str, cultures: List[str], threshold: int = 60) -> Optional[str]:
        """Utilise fuzzy matching pour identifier la culture."""
        if not value:
            return None
        try:
            match = process.extractOne(value.lower(), cultures, scorer=fuzz.ratio)
            if match and match[1] >= threshold:
                logger.debug(f"Fuzzy match pour culture '{value}': Meilleur match='{match[0]}' avec score={match[1]}")
                return match[0]
            logger.debug(f"Pas de match suffisant pour la culture '{value}'")
            return None
        except Exception as e:
            logger.error(f"Erreur fuzzy matching culture: {str(e)}")
            return None

    @staticmethod
    def get_culture_info(culture: str) -> Dict:
        """Récupère tous les conseils disponibles pour une culture depuis le JSON."""
        try:
            # Log de la culture demandée
            logger.debug(f"Recherche des conseils pour la culture: {culture}")

            # Récupérer la liste des cultures disponibles depuis conseils_culture
            cultures_disponibles = list(AGRICULTURAL_DATA.get('conseils_culture', {}).keys())
            logger.debug(f"Cultures disponibles dans conseils_culture: {cultures_disponibles}")

            # Fuzzy matching sur le nom de la culture
            matched_culture = process.extractOne(culture.lower(), cultures_disponibles, scorer=fuzz.ratio)

            if matched_culture and matched_culture[1] >= 60:
                logger.debug(f"Culture trouvée dans conseils: {matched_culture[0]} (score: {matched_culture[1]})")
                return AGRICULTURAL_DATA['conseils_culture'][matched_culture[0]]

            logger.debug(f"Aucune correspondance trouvée pour la culture: {culture}")
            return {}

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des conseils: {str(e)}")
            return {}

    @staticmethod
    def format_conseils(culture: str, conseils: Dict) -> str:
        """Formate les conseils pour l'affichage."""
        try:
            if not conseils:
                cultures_disponibles = AGRICULTURAL_DATA.get('conseils_culture', {}).keys()
                return (f"Je n'ai pas d'informations spécifiques pour la culture de {culture}. "
                        f"Je peux vous conseiller sur : {', '.join(cultures_disponibles)}")

            reponse = f"Voici les conseils pour votre culture de {culture} :\n\n"

            sections = {
                "preparation_sol": "👉 Préparation du sol",
                "plantation": "🌱 Plantation",
                "entretien": "🛠️ Entretien",
                "prevention": "🛡️ Prévention"
            }

            for section, titre in sections.items():
                if conseils_section := conseils.get(section, []):
                    reponse += f"{titre} :\n"
                    for conseil in conseils_section:
                        reponse += f"• {conseil}\n"
                    reponse += "\n"

            return reponse

        except Exception as e:
            logger.error(f"Erreur lors du formatage des conseils: {str(e)}")
            return "Désolé, une erreur est survenue lors du formatage des conseils."

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        try:
            # Récupérer le message de l'utilisateur
            message = tracker.latest_message.get('text', '').lower()
            logger.debug(f"Message reçu: {message}")

            # D'abord, essayer d'obtenir la culture depuis le slot
            culture = tracker.get_slot("type_culture")
            logger.debug(f"Culture depuis le slot: {culture}")

            # Si pas dans le slot, essayer depuis les entités
            if not culture:
                entities = tracker.latest_message.get('entities', [])
                logger.debug(f"Entités trouvées: {entities}")
                culture = next(
                    (e["value"] for e in entities if e["entity"] == "type_culture"),
                    None
                )
                logger.debug(f"Culture depuis les entités: {culture}")

            # Si toujours pas trouvé, essayer fuzzy match sur le message
            if not culture:
                cultures_disponibles = list(AGRICULTURAL_DATA.get('conseils_culture', {}).keys())
                culture = self.fuzzy_match_culture(message, cultures_disponibles)
                logger.debug(f"Culture après fuzzy match: {culture}")

            if not culture:
                cultures_disponibles = list(AGRICULTURAL_DATA.get('conseils_culture', {}).keys())
                dispatcher.utter_message(
                    text=f"Pour quelle culture souhaitez-vous des conseils ? Je peux vous aider avec : {', '.join(cultures_disponibles)}"
                )
                return []

            # Récupérer et formater les conseils
            conseils = self.get_culture_info(culture)
            if not conseils:
                cultures_disponibles = list(AGRICULTURAL_DATA.get('conseils_culture', {}).keys())
                dispatcher.utter_message(
                    text=f"Désolé, je n'ai pas de conseils spécifiques pour {culture}. "
                         f"Je peux vous conseiller sur : {', '.join(cultures_disponibles)}"
                )
                return []

            reponse = self.format_conseils(culture, conseils)
            dispatcher.utter_message(text=reponse)

            # Sauvegarder la culture dans les slots
            return [
                SlotSet("last_culture", culture),
                SlotSet("type_culture", culture)
            ]

        except Exception as e:
            logger.error(f"Erreur lors de la génération des conseils: {str(e)}\n{traceback.format_exc()}")
            dispatcher.utter_message(
                text="Désolé, je n'ai pas pu générer les conseils. Veuillez réessayer."
            )
            return [AllSlotsReset()]


class ActionTraiterUrgence(Action):
    def name(self) -> Text:
        return "action_traiter_urgence"

    @staticmethod
    def fuzzy_match_symptom(description: str, symptomes_connus: List[str], threshold: int = 60) -> Optional[str]:
        """Utilise fuzzy matching pour identifier le symptôme le plus proche."""
        try:
            # Normaliser la description
            description = description.lower().strip()

            # Patterns de reconnaissance pour les symptômes courants
            patterns = {
                "tomate_taches_noires": ["tache noir", "point noir", "marque sombre", "tache sombre"],
                "tomate_jaunissement": ["jaune", "jaunisse", "jaunâtre"],
                "tomate_fletrissement": ["fane", "fletri", "fletrisse", "mou"],
                "tomate_pourriture": ["pourri", "decompose", "pourritur"],
                "oignon_pourriture": ["pourri", "decompose", "pourritur"],
                "oignon_jaunissement": ["jaune", "jaunisse", "jaunâtre"],
                "oignon_mou": ["mou", "ramolli", "amolli"],
                "oignon_taches_blanches": ["tache blanche", "point blanc", "marque blanche"]
            }

            # Chercher la meilleure correspondance avec les patterns
            best_score = 0
            best_match = None

            for symptome, patterns_list in patterns.items():
                for pattern in patterns_list:
                    score = fuzz.partial_ratio(description, pattern)
                    if score > best_score and score >= threshold:
                        best_score = score
                        best_match = symptome

            if best_match:
                logger.debug(f"Fuzzy match pour '{description}': Meilleur match='{best_match}' avec score={best_score}")
                return best_match

            # Si aucun pattern ne correspond, essayer le matching direct
            match = process.extractOne(description, symptomes_connus, scorer=fuzz.token_set_ratio)
            if match and match[1] >= threshold:
                logger.debug(f"Fuzzy match direct pour '{description}': Match='{match[0]}' avec score={match[1]}")
                return match[0]

            logger.debug(f"Pas de match suffisant pour '{description}'")
            return None

        except Exception as e:
            logger.error(f"Erreur fuzzy matching symptôme: {str(e)}")
            return None

    def identifier_symptome_et_culture(self, tracker: Tracker) -> Tuple[Optional[str], Optional[str]]:
        """Identifie le symptôme et la culture en utilisant fuzzy matching."""
        try:
            message = tracker.latest_message.get("text", "").lower()
            entities = tracker.latest_message.get("entities", [])

            # Extraire tous les symptômes connus
            symptomes_connus = []
            for culture in AGRICULTURAL_DATA.get('problemes_courants', {}).get('maladies', {}):
                symptomes_connus.extend(
                    AGRICULTURAL_DATA['problemes_courants']['maladies'][culture]['symptomes'].keys()
                )

            # Essayer d'abord avec l'entité symptome si elle existe
            symptome = next((e["value"] for e in entities if e["entity"] == "symptome"), None)

            # Si pas d'entité symptome, utiliser fuzzy matching
            if not symptome:
                symptome = self.fuzzy_match_symptom(message, symptomes_connus)

            if symptome:
                # Extraire la culture du symptôme (ex : tomate_fletrissement -> tomates)
                culture = symptome.split('_')[0] + 's'
                logger.info(f"Symptôme identifié: {symptome}, Culture: {culture}")
                return symptome, culture

            logger.warning("Impossible d'identifier le symptôme et la culture")
            return None, None

        except Exception as e:
            logger.error(f"Erreur dans l'identification symptôme/culture: {str(e)}")
            return None, None

    @staticmethod
    def get_symptom_info(culture: str, symptome: str) -> Optional[Dict]:
        """Récupère les informations détaillées sur le symptôme."""
        try:
            info = (AGRICULTURAL_DATA.get('problemes_courants', {})
                    .get('maladies', {})
                    .get(culture, {})
                    .get('symptomes', {})
                    .get(symptome))
            logger.info(f"Informations trouvées pour {culture} - {symptome}")
            return info
        except KeyError:
            logger.warning(f"Pas d'information trouvée pour {culture} - {symptome}")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos: {str(e)}")
            return None

    @staticmethod
    def format_response(culture: str, symptom_info: Dict) -> Dict[str, str]:
        """Formate les différentes parties de la réponse."""
        try:
            # Message principal
            main_response = f"Pour ce problème sur vos {culture}:\n\n"
            main_response += f"Description: {symptom_info.get('description', 'Non spécifiée')}\n"
            main_response += f"Niveau de gravité: {symptom_info.get('gravite', 'Non spécifié')}\n\n"

            # Solutions
            solutions = "Solutions recommandées:\n"
            for solution in symptom_info.get('solutions', []):
                solutions += f"• {solution}\n"

            # Prévention
            prevention = "\nConseils de prévention générale:\n"
            for conseil in (AGRICULTURAL_DATA.get('problemes_courants', {}).get('maladies', {}).get(culture, {}).get('prevention_generale', [])):
                prevention += f"• {conseil}\n"

            # Message expert si nécessaire
            expert_message = None
            if symptom_info.get('necessite_expert', False):
                expert_message = (
                    "⚠️ Ce problème nécessite l'intervention d'un expert.\n"
                    "En attendant, appliquez les mesures préventives indiquées."
                )

            return {
                "main": main_response,
                "solutions": solutions,
                "prevention": prevention,
                "expert_message": expert_message
            }

        except Exception as e:
            logger.error(f"Erreur lors du formatage de la réponse: {str(e)}")
            return {
                "main": "Une erreur est survenue lors de la préparation de la réponse.",
                "solutions": "",
                "prevention": "",
                "expert_message": None
            }

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        try:
            # Identifier le symptôme et la culture
            symptome, culture = self.identifier_symptome_et_culture(tracker)

            if not symptome or not culture:
                dispatcher.utter_message(
                    text="Je n'ai pas bien compris le problème. Pouvez-vous préciser quel type de symptôme vous observez sur quelle culture ?"
                )
                return []

            # Récupérer les informations sur le symptôme
            symptom_info = self.get_symptom_info(culture, symptome)

            if not symptom_info:
                dispatcher.utter_message(
                    text=f"Je n'ai pas d'informations sur ce problème spécifique. Je vous conseille de contacter un expert pour un diagnostic précis."
                )
                return []

            # Formater la réponse
            response_parts = self.format_response(culture, symptom_info)

            # Envoyer la réponse
            full_response = response_parts["main"] + "\n" + response_parts["solutions"]
            if response_parts["expert_message"]:
                full_response = response_parts["expert_message"] + "\n\n" + full_response
            full_response += response_parts["prevention"]

            dispatcher.utter_message(text=full_response)
            return []

        except Exception as e:
            logger.error(f"Erreur dans le traitement de l'urgence: {str(e)}")
            dispatcher.utter_message(
                text="Une erreur s'est produite. Pour votre sécurité, je vous conseille de contacter un expert."
            )
            return []


class ActionLogConversation(Action):
    def name(self) -> Text:
        return "action_log_conversation"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Initialiser mongo_client à None avant le bloc try
        mongo_client = None
        try:
            # Connexion à MongoDB
            mongo_client = MongoClient(MONGO_URI)
            db = mongo_client[DB_NAME]

            # Récupérer l'historique de la conversation
            conversation_history = []
            for event in tracker.events:
                if event.get("event") == "user":
                    # Message de l'utilisateur
                    user_message = {
                        "timestamp": str(datetime.now()),
                        "type": "user",
                        "message": event.get("text", ""),
                    }
                    parse_data = event.get("parse_data", {})
                    if parse_data:
                        intent_data = parse_data.get("intent", {})
                        entities = parse_data.get("entities", [])
                        user_message.update({
                            "intent": intent_data.get("name", ""),
                            "confidence": intent_data.get("confidence", 0),
                            "entities": entities
                        })
                    conversation_history.append(user_message)
                elif event.get("event") == "bot":
                    # Réponse du bot
                    conversation_history.append({
                        "timestamp": str(datetime.now()),
                        "type": "bot",
                        "message": event.get("text", "")
                    })

            # Créer la structure de données de la conversation
            conversation_data = {
                "conversation_id": tracker.sender_id,
                "timestamp": str(datetime.now()),
                "slots": {
                    "zone": tracker.get_slot('zone'),
                    "saison": tracker.get_slot('saison'),
                    "type_sol": tracker.get_slot('type_sol'),
                    "objectif_agricole": tracker.get_slot('objectif_agricole'),
                    "symptome": tracker.get_slot('symptome'),
                    "type_culture": tracker.get_slot('type_culture')
                },
                "history": conversation_history
            }

            # Sauvegarder dans MongoDB
            db.conversations.insert_one(conversation_data)
            logger.info(f"Conversation {tracker.sender_id} enregistrée dans MongoDB")

        except Exception as e:
            logger.error(f"Erreur dans ActionLogConversation : {str(e)}")

        finally:
            # Fermer la connexion MongoDB si elle existe
            if mongo_client is not None:
                mongo_client.close()

        return []


class ActionResetSlots(Action):
    def name(self) -> Text:
        return "action_reset_slots"

    @staticmethod
    def get_default_values() -> Dict[Text, Any]:
        """Définit les valeurs par défaut pour les slots."""
        return {
            "zone": None,
            "saison": None,
            "type_sol": None,
            "objectif_agricole": None,
            "symptome": None,
            "type_culture": None
        }

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        """Réinitialise tous les slots avec leurs valeurs par défaut."""
        try:
            # Obtenir les valeurs par défaut
            default_values = self.get_default_values()

            # Créer la liste des événements de réinitialisation
            reset_events = [SlotSet(slot_name, value)
                            for slot_name, value in default_values.items()]

            logger.debug("Réinitialisation des slots effectuée")
            return reset_events

        except Exception as e:
            logger.error(f"Erreur lors de la réinitialisation des slots: {str(e)}")
            return [AllSlotsReset()]  # Fallback sur la réinitialisation globale
