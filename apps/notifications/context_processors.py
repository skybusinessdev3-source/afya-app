from django.conf import settings

from .models import Notification


def notifications_badge(request):
    ctx = {'vapid_public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')}
    if not request.user.is_authenticated:
        return ctx
    qs = Notification.objects.filter(user=request.user)
    ctx.update({
        'unread_notifications_count': qs.filter(is_read=False).count(),
        'latest_notifications': qs[:6],
    })
    return ctx