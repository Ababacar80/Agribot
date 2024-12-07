import os
import traceback
from collections import Counter, defaultdict
from datetime import datetime

from pymongo import MongoClient

from actions.actions import MONGO_URI, DB_NAME


def perform_conversation_analysis():
    """
    Analyse détaillée des conversations depuis MongoDB.
    """
    try:
        # Compteurs et collecteurs
        all_intents = []
        all_questions = []
        nlu_fallbacks = []
        low_confidence_intents = []
        slot_values = defaultdict(list)
        conversation_flows = []
        conversation_lengths = []
        failed_conversations = []
        entity_extractions = []

        # Initialiser la connexion MongoDB
        mongo_client = None
        try:
            mongo_client = MongoClient(MONGO_URI)
            db = mongo_client[DB_NAME]

            # Compter le nombre total de conversations
            total_conversations = db.conversations.count_documents({})
            print(f"\nNombre de conversations trouvées: {total_conversations}")

            # Récupérer toutes les conversations
            for conversation in db.conversations.find({}):
                conv_id = None  # Initialisation de conv_id avant le bloc try
                try:
                    conv_id = conversation.get('conversation_id', 'unknown')
                    print(f"\nAnalyse de la conversation: {conv_id}")

                    # Extraire les slots
                    slots = conversation.get("slots", {})
                    for slot_name, value in slots.items():
                        if value:
                            print(f"Slot trouvé: {slot_name} = {value}")
                            slot_values[slot_name].append(value)

                    # Extraire l'historique des messages
                    history = conversation.get("history", [])
                    print(f"Nombre de messages trouvés: {len(history)}")
                    messages_count = 0
                    has_fallback = False
                    has_low_confidence = False
                    conversation_flow = []

                    for message in history:
                        message_type = message.get("type")

                        if message_type == "user":
                            messages_count += 1
                            user_message = {
                                "message": message.get("message", ""),
                                "intent": message.get("intent", ""),
                                "confidence": message.get("confidence", 0),
                                "entities": message.get("entities", [])
                            }

                            print(f"Message utilisateur: {user_message['message']}")
                            print(f"Intent détecté: {user_message['intent']}")

                            if user_message["intent"] == "nlu_fallback":
                                has_fallback = True
                                nlu_fallbacks.append({
                                    "message": user_message["message"],
                                    "confidence": user_message["confidence"],
                                    "timestamp": message.get("timestamp")
                                })

                            if user_message["confidence"] < 0.7:
                                has_low_confidence = True
                                low_confidence_intents.append(user_message)

                            # Collecter les entités
                            entity_extractions.extend(user_message["entities"])

                            conversation_flow.append(user_message)
                            all_questions.append(user_message["message"])
                            if user_message["intent"]:
                                all_intents.append(user_message["intent"])

                        elif message_type == "bot":
                            messages_count += 1
                            bot_message = message.get("message", "")
                            print(f"Message bot: {bot_message}")
                            conversation_flow.append({
                                "type": "bot",
                                "message": bot_message
                            })

                    # Gestion des conversations problématiques
                    if has_fallback or has_low_confidence:
                        print(f"Conversation problématique détectée: {conv_id}")
                        print(f"- Fallback: {has_fallback}")
                        print(f"- Low confidence: {has_low_confidence}")

                        failed_conversations.append({
                            "id": conv_id,
                            "timestamp": conversation.get("timestamp", "unknown"),
                            "has_fallback": has_fallback,
                            "has_low_confidence": has_low_confidence,
                            "flow": conversation_flow
                        })

                    print(f"Nombre total de messages dans la conversation: {messages_count}")
                    conversation_flows.append(conversation_flow)
                    conversation_lengths.append(messages_count)

                except Exception as e:
                    print(f"Erreur lors de l'analyse de la conversation {conv_id or 'inconnue'}: {str(e)}")
                    continue

        finally:
            if mongo_client is not None:
                mongo_client.close()

        # Vérification des données analysées
        if not conversation_lengths:
            print("ATTENTION: Aucune conversation n'a été analysée!")
            return None

        # Calcul des statistiques
        total_messages = sum(conversation_lengths)
        avg_length = total_messages / len(conversation_lengths) if conversation_lengths else 0

        # Création du résultat final
        analysis_result = {
            "general_stats": {
                "total_conversations": len(conversation_lengths),
                "average_length": avg_length,
                "total_messages": total_messages,
                "unique_users": len(set(conv["id"] for conv in failed_conversations)) if failed_conversations else 0
            },
            "intent_stats": {
                "top_intents": Counter(all_intents).most_common(10),
                "total_intents": len(all_intents),
                "unique_intents": len(set(all_intents))
            },
            "nlu_performance": {
                "fallbacks": {
                    "total": len(nlu_fallbacks),
                    "details": nlu_fallbacks
                },
                "low_confidence": {
                    "total": len(low_confidence_intents),
                    "details": low_confidence_intents
                }
            },
            "slot_statistics": {
                slot: {
                    "total_utilisations": len(values),
                    "valeurs_uniques": len(set(values)),
                    "top_valeurs": Counter(values).most_common(5)
                }
                for slot, values in slot_values.items()
            },
            "entity_statistics": dict(Counter(e.get("entity") for e in entity_extractions)),
            "failed_conversations": {
                "total": len(failed_conversations),
                "details": failed_conversations
            },
            "frequent_questions": Counter(all_questions).most_common(10)
        }

        print("\nAnalyse terminée avec succès!")
        return analysis_result

    except Exception as e:
        print(f"Erreur lors de l'analyse des conversations: {str(e)}")
        print(f"Détails de l'erreur: {traceback.format_exc()}")
        return None


def create_html_report(analysis_data):
    """
    Génère un rapport HTML détaillé des analyses.
    """
    try:
        if not analysis_data:
            print("Aucune donnée à analyser.")
            return

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Rapport d'analyse détaillé des conversations</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 20px;
                    line-height: 1.6;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .card {
                    background-color: white;
                    padding: 20px;
                    margin-bottom: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                table { 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin-bottom: 20px;
                    background-color: white;
                }
                th, td { 
                    padding: 12px 8px; 
                    text-align: left; 
                    border-bottom: 1px solid #ddd;
                }
                th { 
                    background-color: #2e7d32;
                    color: white;
                }
                tr:nth-child(even) { 
                    background-color: #f9f9f9;
                }
                tr:hover {
                    background-color: #f5f5f5;
                }
                h1, h2, h3 { 
                    color: #2e7d32;
                    border-bottom: 2px solid #2e7d32;
                    padding-bottom: 5px;
                }
                .stats {
                    background-color: #f8f8f8;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #2e7d32;
                }
                .alert {
                    background-color: #fff3e0;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    border-left: 4px solid #ff9800;
                }
                .failed {
                    background-color: #ffebee;
                    border-left: 4px solid #f44336;
                }
                .metric {
                    display: inline-block;
                    margin: 10px;
                    padding: 15px;
                    background-color: white;
                    border-radius: 5px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    min-width: 200px;
                }
                .metric-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #2e7d32;
                }
                .metric-label {
                    color: #666;
                    font-size: 14px;
                }
            </style>
        </head>
        <body>
        <div class="container">
        """

        # En-tête et statistiques générales
        html += "<h1>Rapport d'analyse détaillé des conversations</h1>"

        # Vérifier si les données existent avant de les utiliser
        if "general_stats" in analysis_data:
            gen_stats = analysis_data["general_stats"]
            html += f"""
            <div class="card">
                <h2>Statistiques générales</h2>
                <div class="stats">
                    <div class="metric">
                        <div class="metric-value">{gen_stats.get('total_conversations', 0)}</div>
                        <div class="metric-label">Conversations totales</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{gen_stats.get('average_length', 0):.1f}</div>
                        <div class="metric-label">Messages moyens par conversation</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value">{gen_stats.get('total_messages', 0)}</div>
                        <div class="metric-label">Messages totaux</div>
                    </div>
                </div>
            </div>
            """

        # Ajouter section Intent stats
        if "intent_stats" in analysis_data:
            intent_stats = analysis_data["intent_stats"]
            html += """
            <div class="card">
                <h2>Statistiques des Intents</h2>
                <table>
                    <tr>
                        <th>Intent</th>
                        <th>Nombre d'occurrences</th>
                    </tr>
            """
            for intent, count in intent_stats.get('top_intents', []):
                html += f"""
                <tr>
                    <td>{intent}</td>
                    <td>{count}</td>
                </tr>
                """
            html += "</table></div>"

        # Section NLU Performance
        if "nlu_performance" in analysis_data:
            nlu_stats = analysis_data["nlu_performance"]
            if nlu_stats.get('fallbacks', {}).get('details'):
                html += """
                <div class="card">
                    <h2>Performance NLU</h2>
                    <div class="alert">
                        <h3>Échecs NLU</h3>
                        <table>
                            <tr><th>Message</th><th>Confiance</th><th>Timestamp</th></tr>
                """
                for fallback in nlu_stats['fallbacks']['details']:
                    html += f"""
                    <tr>
                        <td>{fallback.get('message', 'N/A')}</td>
                        <td>{fallback.get('confidence', 0):.2f}</td>
                        <td>{fallback.get('timestamp', 'N/A')}</td>
                    </tr>
                    """
                html += "</table></div></div>"

        # Statistiques des slots
        if "slot_statistics" in analysis_data:
            html += """
            <div class="card">
                <h2>Utilisation des slots</h2>
                <table>
                    <tr><th>Slot</th><th>Total utilisations</th><th>Valeurs uniques</th><th>Top 5 valeurs</th></tr>
            """
            for slot, stats in analysis_data["slot_statistics"].items():
                top_values = "<br>".join(f"{val}: {count}" for val, count in stats.get('top_valeurs', []))
                html += f"""
                <tr>
                    <td>{slot}</td>
                    <td>{stats.get('total_utilisations', 0)}</td>
                    <td>{stats.get('valeurs_uniques', 0)}</td>
                    <td>{top_values}</td>
                </tr>
                """
            html += "</table></div>"

        html += """
            </div>
            </body>
            </html>
        """

        # Générer le rapport
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f'conversation_report_{timestamp}.html'

        # Créer le dossier reports s'il n'existe pas
        reports_dir = "reports"
        os.makedirs(reports_dir, exist_ok=True)

        report_path = os.path.join(reports_dir, report_filename)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"Rapport HTML généré avec succès dans : {report_path}")
        print(f"Taille du fichier : {os.path.getsize(report_path)} octets")
        return report_path

    except Exception as e:
        print(f"Erreur lors de la génération du rapport HTML: {str(e)}")
        return None


def main():
    """
    Fonction principale qui orchestre l'analyse et la génération du rapport.
    """
    print("Démarrage de l'analyse des conversations...")

    # Exécuter l'analyse
    conversation_data = perform_conversation_analysis()

    if conversation_data:
        # Générer le rapport HTML
        report_path = create_html_report(conversation_data)

        if report_path:
            print("\nAnalyse terminée avec succès!")
            print(f"Vous pouvez consulter le rapport détaillé ici : {report_path}")

            # Afficher quelques statistiques rapides
            print("\nRésumé rapide :")
            print(f"- Total des conversations : {conversation_data['general_stats']['total_conversations']}")
            print(f"- Nombre de fallbacks NLU : {conversation_data['nlu_performance']['fallbacks']['total']}")
            print(f"- Conversations problématiques : {conversation_data['failed_conversations']['total']}")
        else:
            print("Erreur lors de la génération du rapport.")
    else:
        print("Impossible de générer le rapport en raison d'erreurs lors de l'analyse.")


if __name__ == "__main__":
    main()
