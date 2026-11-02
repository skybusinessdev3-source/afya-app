"""Génération d'images via l'API Google Gemini (« Nano Banana »).

Inactive tant que GEMINI_API_KEY n'est pas renseignée dans le .env —
l'assistant répond alors poliment que l'option n'est pas configurée.
Le modèle se règle via GEMINI_IMAGE_MODEL (défaut : gemini-3.1-flash-image).
"""
import base64
import json
import urllib.error
import urllib.request

from django.conf import settings


def is_configured():
    return bool(getattr(settings, 'GEMINI_API_KEY', ''))


def generate_image(description):
    """Génère une image. Retourne (bytes PNG, None) ou (None, message d'erreur)."""
    if not is_configured():
        return None, ("La génération d'images n'est pas encore activée : il manque la clé "
                      "Google AI Studio (GEMINI_API_KEY) dans la configuration du serveur. "
                      "Demande à l'administrateur de l'ajouter.")

    model = getattr(settings, 'GEMINI_IMAGE_MODEL', 'gemini-3.1-flash-image')
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={settings.GEMINI_API_KEY.strip()}")
    payload = {
        'contents': [{'parts': [{'text': description}]}],
        'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']},
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'},
                                     method='POST')
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:300]
        return None, f"Le service d'images a renvoyé une erreur ({e.code}). {detail}"
    except Exception as e:
        return None, f"Impossible de joindre le service d'images ({e})."

    for cand in data.get('candidates', []):
        for part in (cand.get('content') or {}).get('parts', []):
            inline = part.get('inlineData') or part.get('inline_data') or {}
            if inline.get('data'):
                return base64.b64decode(inline['data']), None
    return None, "Aucune image n'a été produite — reformule la description."
