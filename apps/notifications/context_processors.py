from .models import Notification


def notifications_badge(request):
    if not request.user.is_authenticated:
        return {}
    qs = Notification.objects.filter(user=request.user)
    return {
        'unread_notifications_count': qs.filter(is_read=False).count(),
        'latest_notifications': qs[:6],
    }