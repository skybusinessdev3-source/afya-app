"""Vues de l'assistant IA — page de discussion + API (chat, fichier, confirmation).

Sécurité :
- tout est derrière @login_required ;
- l'IA ne modifie JAMAIS rien directement : elle propose une action, un jeton
  signé (15 min) est renvoyé, et SEUL le superuser peut confirmer ;
- 3 demandes hors du rôle → silence de 5 minutes (AssistantLockout) ;
- plafond quotidien de messages par utilisateur (ASSISTANT_DAILY_LIMIT).
"""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event

from . import actions, ai_engine, documents, images, tools
from .models import AssistantLockout, AssistantMessage

TAILLE_MAX_FICHIER = 10 * 1024 * 1024  # 10 Mo


def _ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


def _verrou(user):
    """Récupère (ou crée) le compteur anti-abus de l'utilisateur."""
    verrou, _ = AssistantLockout.objects.get_or_create(user=user)
    return verrou


def _msg_json(m):
    """Un message tel que le template le dessine."""
    data = {
        'id': m.id,
        'role': m.role,
        'content': m.content,
        'heure': timezone.localtime(m.created_at).strftime('%H:%M'),
        'attachment_url': None,
        'attachment_name': m.attachment_name or '',
        'is_image': False,
    }
    if m.attachment:
        try:
            data['attachment_url'] = reverse('assistant:download', args=[m.id])
            data['is_image'] = m.is_image
        except Exception:
            pass
    return data


# ---------------------------------------------------------------- page
@login_required
def assistant_page(request):
    historique = list(
        AssistantMessage.objects.filter(user=request.user)
        .order_by('-created_at')[:50])
    historique.reverse()
    verrou = _verrou(request.user)
    return render(request, 'assistant/index.html', {
        'page_title': 'Assistant IA',
        'messages_json': json.dumps([_msg_json(m) for m in historique]),
        'images_actives': images.is_configured(),
        'est_superuser': request.user.is_superuser,
        'verrou_secondes': verrou.remaining_seconds(),
    })


# ---------------------------------------------------------------- chat
@login_required
@require_POST
def api_chat(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Requête illisible.'}, status=400)

    texte = (payload.get('message') or '').strip()
    if not texte:
        return JsonResponse({'error': 'Message vide.'}, status=400)
    if len(texte) > 4000:
        texte = texte[:4000]

    # --- verrou anti-abus
    verrou = _verrou(request.user)
    if verrou.is_locked():
        reste = verrou.remaining_seconds()
        return JsonResponse({
            'error': (f"L'assistant est en pause pour toi : 3 demandes hors de ton "
                      f"domaine. Réessaie dans {reste // 60} min {reste % 60:02d} s."),
            'locked_until': reste,
        }, status=429)

    # --- plafond quotidien
    limite = getattr(settings, 'ASSISTANT_DAILY_LIMIT', 150)
    debut = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    nb_jour = AssistantMessage.objects.filter(
        user=request.user, role=AssistantMessage.Roles.USER,
        created_at__gte=debut).count()
    if nb_jour >= limite:
        return JsonResponse({
            'error': (f"Tu as atteint la limite de {limite} messages aujourd'hui. "
                      "L'assistant sera de nouveau disponible demain."),
        }, status=429)

    # --- historique AVANT d'enregistrer le nouveau message
    historique = [(m.role, m.content, m.context_text) for m in
                  AssistantMessage.objects.filter(user=request.user)
                  .order_by('-created_at')[:ai_engine.MAX_HISTORIQUE]]
    historique.reverse()

    msg_user = AssistantMessage.objects.create(
        user=request.user, role=AssistantMessage.Roles.USER, content=texte)

    resultat = ai_engine.chat(request.user, texte, historique)

    # --- règle des 3 tentatives hors portée
    if resultat['out_of_scope']:
        verrou.add_strike()
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='Assistant IA', obj=msg_user,
                  new_value={'hors_portee': texte[:200],
                             'tentatives': verrou.strikes,
                             'bloque': verrou.is_locked()},
                  ip_address=_ip(request), result=AuditLog.Results.FAILURE)
    else:
        if verrou.strikes:
            verrou.reset()

    msg_ia = AssistantMessage.objects.create(
        user=request.user, role=AssistantMessage.Roles.ASSISTANT,
        content=resultat['reply'])

    # --- artefacts : fichier généré (docx/xlsx/pdf/image) ou action à confirmer
    action_a_confirmer = None
    for art in resultat.get('artifacts') or []:
        if art.get('kind') == 'file' and not msg_ia.attachment:
            msg_ia.attachment = art['path']
            msg_ia.attachment_name = art.get('name', '')
            msg_ia.is_image = bool(art.get('is_image'))
            msg_ia.save(update_fields=['attachment', 'attachment_name', 'is_image'])
        elif art.get('kind') == 'action' and action_a_confirmer is None:
            action_a_confirmer = {
                'token': art['token'],
                'description': art['description'],
            }

    reponse = {'message': _msg_json(msg_ia)}
    if action_a_confirmer:
        reponse['action'] = action_a_confirmer
    if verrou.is_locked():
        reponse['locked_until'] = verrou.remaining_seconds()
    return JsonResponse(reponse)


# ---------------------------------------------------------------- fichier reçu
@login_required
@require_POST
def api_upload(request):
    fichier = request.FILES.get('fichier')
    if not fichier:
        return JsonResponse({'error': 'Aucun fichier reçu.'}, status=400)
    if fichier.size > TAILLE_MAX_FICHIER:
        return JsonResponse({'error': "Fichier trop lourd (maximum 10 Mo)."}, status=400)

    nom = fichier.name[:150]
    msg = AssistantMessage(user=request.user, role=AssistantMessage.Roles.USER,
                           content=f"📎 Fichier déposé : {nom}",
                           attachment_name=nom)
    msg.attachment.save(nom, fichier, save=False)

    try:
        texte = documents.extract_text(msg.attachment.path, nom)
    except ValueError as e:                       # image ou format non géré
        msg.attachment.delete(save=False)
        return JsonResponse({'error': str(e)}, status=400)
    except Exception:
        msg.attachment.delete(save=False)
        return JsonResponse({'error': "Impossible de lire ce fichier."}, status=400)

    msg.context_text = texte
    msg.save()
    accuse = ("📄 J'ai bien lu le fichier « " + nom + " » "
              f"({len(texte)} caractères). Pose-moi ta question à son sujet.")
    msg_ia = AssistantMessage.objects.create(
        user=request.user, role=AssistantMessage.Roles.ASSISTANT, content=accuse)
    return JsonResponse({'messages': [_msg_json(msg), _msg_json(msg_ia)]})


# ---------------------------------------------------------------- confirmation d'une action
@login_required
@require_POST
def api_confirm(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Requête illisible.'}, status=400)

    token = payload.get('token') or ''
    valider = bool(payload.get('confirmer', True))

    # Seul le superuser confirme — un autre utilisateur = tentative hors portée
    if not request.user.is_superuser:
        verrou = _verrou(request.user)
        verrou.add_strike()
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='Assistant IA',
                  new_value={'confirmation_refusee': True,
                             'tentatives': verrou.strikes},
                  ip_address=_ip(request), result=AuditLog.Results.FAILURE)
        return JsonResponse({'error': "Seul le superuser peut confirmer une modification."},
                            status=403)

    try:
        action, parametres = actions.read_token(token)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    description = actions.describe(action, parametres)
    if not valider:
        AssistantMessage.objects.create(
            user=request.user, role=AssistantMessage.Roles.ASSISTANT,
            content=f"❌ Action annulée : {description}")
        return JsonResponse({'ok': True, 'message': 'Action annulée.'})

    resultat = actions.execute(request.user, action, parametres)
    AssistantMessage.objects.create(
        user=request.user, role=AssistantMessage.Roles.ASSISTANT,
        content=f"✅ {resultat}")
    return JsonResponse({'ok': True, 'message': resultat})


# ---------------------------------------------------------------- téléchargement
@login_required
def download(request, message_id):
    msg = get_object_or_404(AssistantMessage, pk=message_id)
    # Propriétaire du fil, ou responsable et plus (MANAGER/ADMIN/DIRECTOR/superuser)
    if msg.user_id != request.user.id and not tools.autorise(request.user, tools.RESP):
        return JsonResponse({'error': 'Accès refusé.'}, status=403)
    if not msg.attachment:
        return JsonResponse({'error': 'Aucun fichier.'}, status=404)
    nom = msg.attachment_name or 'fichier'
    return FileResponse(msg.attachment.open('rb'), as_attachment=not msg.is_image,
                        filename=nom)
