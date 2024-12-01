import json
import logging
import traceback
from multiprocessing import process
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset
from thefuzz import fuzz, process

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_agricultural_data() -> Dict:
    """Charge les données agricoles depuis le fichier JSON."""
    try:
        with open('C:/Users/asus/Documents/Agribot/agribot/actions/agricultural_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Données chargées avec succès: {len(data.get('cultures_info', {}))} zones")
            return data
    except Exception as e:
        logger.error(f"Erreur lors du chargement des données: {str(e)}")
        return {}


# Charger les données au démarrage
AGRICULTURAL_DATA = load_agricultural_data()


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
        zones_valides = list(AGRICULTURAL_DATA.get('cultures_info', {}).keys())
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

        # Définition des valeurs valides
        zones_valides = list(AGRICULTURAL_DATA.get('cultures_info', {}).keys())
        saisons_valides = ["saison des pluies", "saison sèche"]
        sols_valides = ["argileux", "sableux"]

        # Normalisation de l'objectif
        objectif_norm = None
        if objectif:
            objectif = objectif.lower().strip()
            if "rente" in objectif:
                objectif_norm = "cultures de rente"
            elif "vivrière" in objectif or "vivriere" in objectif:
                objectif_norm = "cultures vivrières"
            else:
                # Utiliser fuzzy matching avec token_set_ratio pour meilleure correspondance
                choices = ["cultures de rente", "cultures vivrières"]
                match = process.extractOne(objectif, choices, scorer=fuzz.token_set_ratio)
                if match and match[1] >= 60:
                    objectif_norm = match[0]
                    logger.debug(f"Fuzzy match pour objectif: '{objectif}' -> '{objectif_norm}' (score: {match[1]})")

        # Normalisation avec fuzzy matching pour les autres paramètres
        zone_norm = self.fuzzy_match(zone, zones_valides) if zone else None
        saison_norm = self.fuzzy_match(saison, saisons_valides) if saison else None
        type_sol_norm = self.fuzzy_match(type_sol, sols_valides) if type_sol else None

        logger.debug(
            f"Normalisation des paramètres:\n"
            f"Zone: {zone} -> {zone_norm}\n"
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
            return AGRICULTURAL_DATA['cultures_info'][params['zone']][params['saison']][params['type_sol']][
                params['objectif']]
        except KeyError:
            logger.debug(f"Aucune donnée trouvée pour les paramètres: {params}")
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
        if zone in AGRICULTURAL_DATA['cultures_info']:
            if saison in AGRICULTURAL_DATA['cultures_info'][zone]:
                sols_disponibles = list(AGRICULTURAL_DATA['cultures_info'][zone][saison].keys())
                if sols_disponibles:
                    suggestions.append(
                        f"Pour {zone} en {saison}, les sols disponibles sont : {', '.join(sols_disponibles)}")

        # Cherche d'autres zones avec le même type de sol
        zones_compatibles = []
        for autre_zone in AGRICULTURAL_DATA['cultures_info']:
            if saison in AGRICULTURAL_DATA['cultures_info'][autre_zone]:
                if type_sol in AGRICULTURAL_DATA['cultures_info'][autre_zone][saison]:
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
                           f"{', '.join(missing_params)}. Pouvez-vous les préciser ?")
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


class ActionTraiterUrgence(Action):
    def name(self) -> Text:
        return "action_traiter_urgence"

    @staticmethod
    def extract_culture_from_entities(tracker: Tracker) -> Optional[str]:
        """Extrait la culture à partir des entités Rasa."""
        entities = tracker.latest_message.get('entities', [])
        for entity in entities:
            if entity['entity'] == 'type_culture':
                return entity['value']
        return None

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        try:
            # Extraction de la culture
            culture = self.extract_culture_from_entities(tracker)

            if culture:
                # Tenter de récupérer les infos pour cette culture
                try:
                    info = AGRICULTURAL_DATA['problemes_courants']['maladies'][culture]

                    response = f"Pour vos {culture}, voici les recommandations :\n\n"

                    if 'symptomes' in info:
                        response += "🔍 Symptômes courants :\n"
                        for symptome in info['symptomes']:
                            response += f"• {symptome}\n"
                        response += "\n"

                    if 'solutions' in info:
                        response += "💡 Solutions recommandées :\n"
                        for solution in info['solutions']:
                            response += f"• {solution}\n"
                        response += "\n"

                    if 'prevention' in info:
                        response += "🛡️ Prévention :\n"
                        for prev in info['prevention']:
                            response += f"• {prev}\n"

                    dispatcher.utter_message(text=response)
                    return []

                except KeyError:
                    dispatcher.utter_message(
                        text=f"Je n'ai pas d'informations pour cette culture : {culture}")
                    return []

            else:
                dispatcher.utter_message(
                    text="Pour quelle culture observez-vous ce problème ? (tomates, oignons)")
                return []

        except Exception as e:
            logger.error(f"Erreur: {str(e)}")
            dispatcher.utter_message(text="Désolé, j'ai rencontré une erreur. Pouvez-vous réessayer ?")
            return []


class ActionResetSlots(Action):
    def name(self) -> Text:
        return "action_reset_slots"

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        return [AllSlotsReset()]
