"""Moteur de conversation de l'assistant IA — Groq (API compatible OpenAI).

Le modèle ne devine jamais les chiffres : il appelle les outils de tools.py
(lecture seule, mêmes calculs que les rapports de l'app). Les modifications
passent par proposer_action → carte de confirmation (superuser uniquement).

Marqueur de sécurité : quand une demande dépasse le rôle de l'utilisateur,
le modèle commence sa réponse par [[HORS_PORTEE]] — la vue compte alors
l'essai (3 essais → silence de 5 minutes).
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from . import tools as t

logger = logging.getLogger('apps.assistant')

MAX_ROUNDS = 5          # allers-retours outils maximum par question
MAX_HISTORIQUE = 12     # messages de contexte renvoyés au modèle
MARQUEUR = '[[HORS_PORTEE]]'

_ACCES = {
    'STAFF': ("rapport du jour, recherche de patients, génération de documents "
              "(Word/PDF/Excel) et d'images"),
    'RESP': ("tous les rapports (jour/mois/année), prescripteurs, entreprises, "
             "dettes, recherche de patients, génération de documents et d'images"),
    'DIR': ("tous les rapports, prescripteurs, entreprises, dettes, journal "
            "d'activité, génération de documents et d'images"),
    'ROOT': ("tout ce qui précède, plus la possibilité de PROPOSER des "
             "modifications via l'outil proposer_action"),
}


def _system_prompt(user):
    niveau = t.niveau_user(user)
    nom = user.get_full_name() or user.username
    return f"""Tu es l'assistant IA de CRF-MK, un centre médical (kinésithérapie, médecine, laboratoire, pharmacie, soins à domicile) géré avec l'application AFYA APP. Tu réponds TOUJOURS en français, de façon claire et concise.

Utilisateur actuel : {nom} — rôle : {user.get_role_display()}.
Date du jour : {timezone.localdate():%d/%m/%Y}.

RÈGLES ABSOLUES :
1. Chiffres de l'application : JAMAIS d'invention — utilise les outils fournis (rapport_jour, rapport_mois, prescripteurs…). Si une donnée n'est pas accessible par un outil, dis-le honnêtement.
2. Portée : cet utilisateur a accès à : {_ACCES[niveau]}.
   - Si la demande porte sur des données ou actions HORS de cette portée (autres rapports, modifications sans en avoir le droit…), commence IMPÉRATIVEMENT ta réponse par {MARQUEUR} puis refuse poliment en une phrase. N'utilise ce marqueur QUE pour un dépassement de rôle, jamais pour une simple question générale.
3. Modifications : tu ne modifies JAMAIS rien toi-même. {"Quand le superuser demande une modification, utilise l'outil proposer_action : une carte de confirmation s'affichera." if niveau == 'ROOT' else "Si on te demande de modifier, supprimer ou enregistrer quelque chose → " + MARQUEUR + " et explique que seul le superuser peut le faire."}
4. Argent : montants en $ (USD) et/ou FC (francs congolais) — ne mélange jamais les deux devises dans un total.
5. Style : réponses courtes, **gras** pour les chiffres clés, listes avec « - ». Pour les questions générales (rédaction, conseils, culture…), réponds librement et utilement, sans outil.
6. Documents : quand on te demande une lettre, un rapport ou un tableau, utilise generer_document ou generer_tableau avec un contenu COMPLET et bien rédigé.
7. Fichiers déposés : si le message contient « --- Contenu du fichier joint --- », base ta réponse sur ce contenu."""


def _appel_groq(messages, schemas, model):
    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_completion_tokens': 1600,
    }
    if schemas:
        payload['tools'] = schemas
        payload['tool_choice'] = 'auto'
    req = urllib.request.Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f"Bearer {settings.GROQ_API_KEY.strip()}",
                 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # On récupère le message exact de Groq — indispensable pour diagnostiquer
        try:
            detail = json.loads(e.read().decode('utf-8') or '{}')
            err = detail.get('error') or {}
            e.groq_message = str(err.get('message') or '')
            e.groq_code = str(err.get('code') or '')
        except Exception:
            e.groq_message = ''
            e.groq_code = ''
        logger.warning('Groq HTTP %s (%s) : %s', e.code, e.groq_code, e.groq_message)
        raise


def _message_erreur_http(e):
    """Traduit une erreur HTTP de Groq en consigne claire pour l'utilisateur."""
    code, msg, groq_code = e.code, getattr(e, 'groq_message', ''), getattr(e, 'groq_code', '')
    if code == 401:
        return ("La clé Groq est refusée (invalide ou révoquée). Vérifie GROQ_API_KEY "
                "dans le fichier .env — copie-la à nouveau depuis console.groq.com, "
                "sans espace ni guillemets, puis redémarre le serveur.")
    if code == 403:
        if 'country' in groq_code or 'country' in msg.lower() or 'territor' in msg.lower():
            return ("Groq refuse les requêtes envoyées depuis ce pays "
                    f"(« {msg or groq_code} »). En local sur ton PC ça restera bloqué, "
                    "mais sur le serveur en ligne (hébergé en Europe) ça fonctionnera. "
                    "Tu peux tester l'assistant directement après le déploiement.")
        if 'model' in groq_code or 'model' in msg.lower():
            return ("La clé Groq n'a pas le droit d'utiliser ce modèle. Dans "
                    "console.groq.com → API Keys, vérifie que la clé n'a pas de "
                    "restriction de modèles (laisse l'accès à tous les modèles), "
                    "ou crée une nouvelle clé sans restriction.")
        return f"Groq refuse la requête (403) : {msg or 'permission refusée'}. Vérifie la clé dans console.groq.com."
    if code == 404:
        return ("Le modèle configuré est introuvable chez Groq. Vérifie GROQ_MODEL "
                "dans le .env (valeur attendue : openai/gpt-oss-120b).")
    if code == 413:
        return "Le message est trop long pour le service IA — raccourcis-le et réessaie."
    return ("Le service IA est momentanément indisponible "
            f"(erreur {code}{' — ' + msg if msg else ''}). Réessaie dans un instant.")


def chat(user, texte, historique):
    """Une question → une réponse.
    historique : liste de tuples (role, content, context_text).
    Retourne {'reply', 'out_of_scope', 'artifacts': [...]}."""
    if not getattr(settings, 'GROQ_API_KEY', ''):
        return {'reply': ("L'assistant n'est pas encore configuré : la clé Groq "
                          "(GROQ_API_KEY) manque dans le fichier .env du serveur."),
                'out_of_scope': False, 'artifacts': []}

    messages = [{'role': 'system', 'content': _system_prompt(user)}]
    for role, content, ctx in historique[-MAX_HISTORIQUE:]:
        c = content or ''
        if ctx:
            c += f"\n\n--- Contenu du fichier joint ---\n{ctx[:8000]}"
        messages.append({'role': role, 'content': c[:6000]})
    messages.append({'role': 'user', 'content': texte})

    schemas = t.schemas_pour(user)
    artifacts = []
    models = [settings.GROQ_MODEL, getattr(settings, 'GROQ_MODEL_FALLBACK', 'openai/gpt-oss-20b')]
    model_index = 0

    for _ in range(MAX_ROUNDS):
        try:
            data = _appel_groq(messages, schemas, models[model_index])
        except urllib.error.HTTPError as e:
            if e.code == 429 and model_index == 0:
                model_index = 1     # quota du modèle principal épuisé → modèle de secours
                continue
            return {'reply': _message_erreur_http(e),
                    'out_of_scope': False, 'artifacts': []}
        except Exception:
            return {'reply': ("Impossible de joindre le service IA — vérifie la "
                              "connexion internet du serveur et réessaie."),
                    'out_of_scope': False, 'artifacts': []}

        msg = data.get('choices', [{}])[0].get('message') or {}
        appels = msg.get('tool_calls') or []

        if not appels:
            reply = (msg.get('content') or '').strip()
            out_of_scope = reply.startswith(MARQUEUR)
            if out_of_scope:
                reply = reply[len(MARQUEUR):].strip() or \
                    "Cette demande dépasse ce que ton rôle permet de consulter."
            if not reply:
                reply = "Je n'ai pas réussi à formuler une réponse — reformule ta question."
            return {'reply': reply, 'out_of_scope': out_of_scope, 'artifacts': artifacts}

        messages.append(msg)
        for call in appels:
            fn = (call.get('function') or {})
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except json.JSONDecodeError:
                args = {}
            resultat, artifact = t.execute_tool(user, fn.get('name', ''), args)
            if artifact:
                artifacts.append(artifact)
            messages.append({'role': 'tool',
                             'tool_call_id': call.get('id', ''),
                             'content': str(resultat)[:3500]})

    return {'reply': ("Ta demande nécessite trop d'étapes d'un coup — "
                      "essaie de la découper en questions plus simples."),
            'out_of_scope': False, 'artifacts': artifacts}
