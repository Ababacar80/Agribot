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
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors du chargement des données: {str(e)}")
        return {}


# Charger les données au démarrage
AGRICULTURAL_DATA = load_agricultural_data()


class ValidateConseilCultureForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_conseil_culture_form"

    @staticmethod
    async def validate_zone(
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        # Normaliser la valeur
        normalized_value = slot_value.lower().replace('-', '').replace(' ', '')
        zones_valides = AGRICULTURAL_DATA.get('cultures_par_zone', {}).keys()

        if normalized_value in zones_valides:
            return {"zone": normalized_value}

        zones_list = ', '.join(zones_valides)
        dispatcher.utter_message(text=f"Zone non reconnue. Zones valides : {zones_list}")
        return {"zone": None}

    @staticmethod
    async def validate_saison(
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        saisons_valides = ["saison des pluies", "saison sèche"]
        if slot_value.lower() in saisons_valides:
            return {"saison": slot_value.lower()}

        dispatcher.utter_message(text="Choisissez entre 'saison des pluies' et 'saison sèche'")
        return {"saison": None}

    @staticmethod
    async def validate_type_sol(
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        sols_valides = ["argileux", "sableux", "limoneux"]
        if slot_value.lower() in sols_valides:
            return {"type_sol": slot_value.lower()}

        dispatcher.utter_message(text="Choisissez entre : argileux, sableux ou limoneux")
        return {"type_sol": None}

    @staticmethod
    async def validate_objectif_agricole(
            slot_value: Any,
            dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        objectifs_valides = ["cultures vivrières", "cultures de rente"]
        if slot_value.lower() in objectifs_valides:
            return {"objectif_agricole": slot_value.lower()}

        dispatcher.utter_message(text="Choisissez entre 'cultures vivrières' et 'cultures de rente'")
        return {"objectif_agricole": None}


class ActionSuggererCultures(Action):
    def name(self) -> Text:
        return "action_suggerer_cultures"

    @staticmethod
    def fuzzy_match(input_value: str, choices: list, threshold: int = 70) -> Optional[str]:
        """
        Utilise fuzzy matching pour trouver la meilleure correspondance.
        """
        if not input_value:
            return None
        try:
            match = process.extractOne(input_value.lower(), choices, scorer=fuzz.ratio)
            if match:
                value, score = match
                logger.debug(f"Fuzzy match pour '{input_value}': Meilleur match='{value}' avec score={score}")
                return value if score >= threshold else None
            return None
        except Exception as e:
            logger.error(f"Erreur fuzzy matching: {str(e)}")
            return None

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        try:
            # Récupération des slots
            zone = tracker.get_slot("zone")
            saison = tracker.get_slot("saison")
            type_sol = tracker.get_slot("type_sol")
            objectif = tracker.get_slot("objectif_agricole")

            logger.debug(f"Valeurs brutes des slots: Zone={zone}, Saison={saison}, "
                         f"Sol={type_sol}, Objectif={objectif}")

            # Définition des valeurs valides
            zones_valides = list(AGRICULTURAL_DATA.get('cultures_info', {}).keys())
            saisons_valides = ["saison des pluies", "saison sèche"]
            sols_valides = ["argileux", "sableux"]

            # Afficher tous les scores pour chaque entrée
            logger.debug("Scores de matching pour la zone:")
            for choice in zones_valides:
                score = fuzz.ratio(zone.lower(), choice.lower())
                logger.debug(f"  '{zone}' vs '{choice}': {score}")

            logger.debug("Scores de matching pour la saison:")
            for choice in saisons_valides:
                score = fuzz.ratio(saison.lower(), choice.lower())
                logger.debug(f"  '{saison}' vs '{choice}': {score}")

            logger.debug("Scores de matching pour le type de sol:")
            for choice in sols_valides:
                score = fuzz.ratio(type_sol.lower(), choice.lower())
                logger.debug(f"  '{type_sol}' vs '{choice}': {score}")

            # Normalisation avec fuzzy matching
            zone_norm = self.fuzzy_match(zone, zones_valides)
            saison_norm = self.fuzzy_match(saison, saisons_valides)
            type_sol_norm = self.fuzzy_match(type_sol, sols_valides)

            # Gestion de l'objectif
            objectif_norm = None
            if objectif:
                logger.debug("Traitement de l'objectif:")
                # Séparer les entrées multiples et prendre la dernière non vide
                objectifs = [obj.strip() for obj in objectif.split('\n') if obj.strip()]
                if objectifs:
                    dernier_objectif = objectifs[-1].lower()
                    logger.debug(f"  Dernière entrée valide: '{dernier_objectif}'")

                    # Liste des objectifs valides pour le fuzzy matching
                    objectifs_valides = ["rente", "vivriere"]

                    # Nettoyage et normalisation
                    clean_objectif = dernier_objectif.replace('cultures', '').replace('culture', '').replace('de',
                                                                                                             '').strip()
                    logger.debug(f"  Après nettoyage initial: '{clean_objectif}'")

                    # Fuzzy matching
                    match = process.extractOne(clean_objectif, objectifs_valides)
                    if match:
                        mot, score = match
                        logger.debug(f"  Fuzzy match: '{clean_objectif}' vs '{mot}' (score: {score})")
                        if score >= 60:  # Seuil plus bas car les mots sont plus courts
                            objectif_norm = "cultures de rente" if mot == "rente" else "cultures vivrières"
                            logger.debug(f"  Match trouvé -> {objectif_norm}")

                logger.debug(f"Objectif final: {objectif_norm}")

            logger.debug(f"Paramètres après normalisation: Zone={zone_norm}, Saison={saison_norm}, "
                         f"Sol={type_sol_norm}, Objectif={objectif_norm}")

            if not all([zone_norm, saison_norm, type_sol_norm, objectif_norm]):
                logger.debug("Paramètres manquants après normalisation")
                return self.handle_no_recommendations(dispatcher, zone, saison, type_sol)

            # Accès aux données
            cultures_info = AGRICULTURAL_DATA.get('cultures_info', {})
            zone_data = cultures_info.get(zone_norm, {})
            saison_data = zone_data.get(saison_norm, {})
            sol_data = saison_data.get(type_sol_norm, {})
            cultures_data = sol_data.get(objectif_norm, [])

            if not cultures_data:
                logger.debug("Aucune culture trouvée pour cette combinaison")
                return self.handle_no_recommendations(dispatcher, zone_norm, saison_norm, type_sol_norm)

            message = (f"Pour votre zone {zone_norm} en {saison_norm} avec un sol {type_sol_norm}, "
                       f"voici les cultures recommandées pour {objectif_norm}:\n\n")

            # Ajouter les détails pour chaque culture
            for culture in cultures_data:
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

            dispatcher.utter_message(text=message)
            return [SlotSet("cultures_suggerees", [c['nom'] for c in cultures_data])]

        except Exception as e:
            logger.error(f"Erreur: {str(e)}")
            logger.error(f"Traceback complet: {traceback.format_exc()}")
            return self.handle_no_recommendations(dispatcher)

    @staticmethod
    def handle_no_recommendations(
            dispatcher: CollectingDispatcher,
            zone: Optional[str] = None,
            saison: Optional[str] = None,
            type_sol: Optional[str] = None
    ) -> List[Dict[Text, Any]]:
        # Utiliser les données normalisées pour l'affichage
        if any([zone, saison, type_sol]):
            sols_disponibles = list(AGRICULTURAL_DATA.get('cultures_info', {})
                                    .get(zone, {})
                                    .get(saison, {}).keys())
            if sols_disponibles:
                message = (f"Pour votre zone {zone} en {saison}, les types de sols disponibles sont : "
                           f"{', '.join(sols_disponibles)}.\n"
                           f"Veuillez choisir parmi ces options.")
            else:
                message = ("Je n'ai pas de recommandations spécifiques pour cette combinaison. "
                           "Consultez un agent agricole local pour des conseils personnalisés.")
        else:
            message = ("Je n'ai pas suffisamment d'informations. "
                       "Veuillez me donner tous les détails nécessaires.")

        dispatcher.utter_message(text=message)
        return [AllSlotsReset()]


class ActionTraiterUrgence(Action):
    def name(self) -> Text:
        return "action_traiter_urgence"

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        message = tracker.latest_message.get('text', '').lower()

        # Détection de la culture
        culture_detectee = None
        if "tomate" in message:
            culture_detectee = "tomates"
        elif "oignon" in message:
            culture_detectee = "oignons"

        # Détection du type de problème
        type_probleme = None
        if any(mot in message for mot in ["pourri", "pourrisse", "pourriture"]):
            type_probleme = "maladies"  # Pourriture est dans la catégorie maladies
        elif any(mot in message for mot in ["insecte", "parasite", "mangé", "trou"]):
            type_probleme = "parasites"
        elif any(mot in message for mot in ["malade", "maladie", "tache"]):
            type_probleme = "maladies"

        try:
            if culture_detectee and type_probleme:
                # Récupérer les informations depuis le JSON
                info = AGRICULTURAL_DATA['problemes_courants'][type_probleme].get(culture_detectee)

                if info:
                    response = (f"Pour vos {culture_detectee} qui présentent un problème de {type_probleme}, "
                                f"voici mes recommandations :\n\n")

                    response += "🔍 Symptômes courants :\n"
                    for symptome in info["symptomes"]:
                        response += f"• {symptome}\n"

                    response += "\n💡 Solutions recommandées :\n"
                    for solution in info["solutions"]:
                        response += f"• {solution}\n"

                    response += "\n🛡️ Prévention :\n"
                    for prevention in info["prevention"]:
                        response += f"• {prevention}\n"

                    dispatcher.utter_message(text=response)
                    return [
                        SlotSet("last_problem_type", type_probleme),
                        SlotSet("last_culture", culture_detectee)
                    ]

            # Si on n'a pas identifié la culture
            if not culture_detectee:
                dispatcher.utter_message(
                    text="Pour quelle culture observez-vous ce problème ? "
                         "(Par exemple : tomates ou oignons)"
                )
                return []

            # Si on n'a pas identifié le type de problème
            if not type_probleme:
                dispatcher.utter_message(
                    text="Pouvez-vous décrire plus précisément les symptômes ? "
                         "Est-ce lié à des insectes/parasites ou à une maladie ?"
                )
                return []

            # Si la combinaison n'existe pas dans nos données
            dispatcher.utter_message(
                text=("Je n'ai pas de recommandation spécifique pour ce problème.\n"
                      "Voici quelques conseils généraux :\n"
                      "1. 🔍 Examinez et photographiez les symptômes\n"
                      "2. ⚡ Isolez les plants touchés\n"
                      "3. 👨‍🌾 Contactez un agent agricole\n"
                      "4. ⚠️ Évitez tout traitement non recommandé")
            )
            return []

        except Exception as e:
            logger.error(f"Erreur lors du traitement de l'urgence: {str(e)}")
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
