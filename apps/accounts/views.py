from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from django.shortcuts import redirect


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


@login_required
def profile_page(request):
    return render(request, 'accounts/profile.html', {'page_title': 'Mon profil'})


@login_required
@require_POST
def profile_update(request):
    """Nom, prénom, téléphone — les champs vides ne sont JAMAIS écrasés."""
    import json
    data = json.loads(request.body)
    u = request.user
    changed = []
    if data.get('first_name', '').strip():
        u.first_name = data['first_name'].strip()
        changed.append('first_name')
    if data.get('last_name', '').strip():
        u.last_name = data['last_name'].strip()
        changed.append('last_name')
    if data.get('phone', '').strip():
        u.phone = data['phone'].strip()
        changed.append('phone')
    if changed:
        u.save(update_fields=changed)
        log_event(user=u, action=AuditLog.Actions.UPDATE,
                  module='accounts', obj=u, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': 'Profil mis à jour.'})
    return JsonResponse({'success': False, 'message': 'Rien à modifier : remplissez au moins un champ.'})


@login_required
@require_POST
def profile_avatar(request):
    """Photo de profil (multipart)."""
@login_required
@require_POST
def profile_avatar(request):
    """Photo de profil (multipart) — redirige vers la page profil avec message."""
    if request.FILES.get('avatar'):
        request.user.avatar = request.FILES['avatar']
        request.user.save(update_fields=['avatar'])
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='accounts', obj=request.user, ip_address=get_client_ip(request))
        messages.success(request, 'Photo de profil mise à jour.')
    else:
        messages.error(request, 'Aucun fichier sélectionné.')
    return redirect('accounts:profile')


@login_required
@require_POST
def profile_password(request):
    """Changement de mot de passe avec vérification de l'ancien."""
    import json
    data = json.loads(request.body)
    if not request.user.check_password(data.get('old_password', '')):
        return JsonResponse({'success': False, 'message': 'Ancien mot de passe incorrect.'}, status=400)
    new = data.get('new_password', '')
    if len(new) < 8:
        return JsonResponse({'success': False, 'message': 'Le nouveau mot de passe doit faire 8 caractères minimum.'}, status=400)
    request.user.set_password(new)
    request.user.must_change_password = False
    request.user.save(update_fields=['password', 'must_change_password'])
    log_event(user=request.user, action=AuditLog.Actions.UPDATE,
              module='accounts', obj=request.user, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': 'Mot de passe modifié. Veuillez vous reconnecter.'})