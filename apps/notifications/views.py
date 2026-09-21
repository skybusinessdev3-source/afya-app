import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from django.conf import settings

from .models import Notification, PushSubscription
from .utils import process_due_reminders


def vapid_public_key(request):
    """Context processor : expose la clé publique VAPID à tous les templates."""
    return {'vapid_public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')}


@login_required
@require_POST
def mark_all_read(request):
    n = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True, 'marked': n})


@login_required
@require_POST
def push_subscribe(request):
    """Enregistre l'abonnement Web Push du navigateur de l'utilisateur."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        endpoint = (data.get('endpoint') or '').strip()
        keys = data.get('keys') or {}
        p256dh = (keys.get('p256dh') or '').strip()
        auth = (keys.get('auth') or '').strip()
        if not endpoint or not p256dh or not auth:
            return JsonResponse({'ok': False, 'error': 'Abonnement incomplet.'}, status=400)
        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth})
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def push_unsubscribe(request):
    """Retire l'abonnement Web Push de ce navigateur."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        PushSubscription.objects.filter(
            user=request.user, endpoint=(data.get('endpoint') or '').strip()).delete()
    except Exception:
        pass
    return JsonResponse({'ok': True})


@login_required
def api_unread(request):
    """Polling (toutes les 20 s côté navigateur) : rappels dus + non-lues.
    Appelle process_due_reminders() à chaque passage → les rappels partent
    même sans cron, tant que l'application est ouverte quelque part."""
    process_due_reminders()
    qs = Notification.objects.filter(user=request.user, is_read=False)
    return JsonResponse({
        'count': qs.count(),
        'latest': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link or '',
            'created': n.created_at.strftime('%d/%m %H:%M'),
        } for n in qs[:5]],
    })