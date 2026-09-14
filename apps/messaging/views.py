import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.audit.utils import log_event

from .models import Conversation, ConversationMember, Message, MessageAttachment


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


def _conversation_data(conv, user):
    if conv.type == Conversation.Types.PRIVATE:
        other = conv.members.filter(is_active=True).exclude(user=user).first()
        name = (other.user.get_full_name() or other.user.username) if other else 'Inconnu'
    else:
        name = conv.name
    last = conv.messages.filter(is_deleted=False, sender__isnull=False).first()
    return {
        'id': conv.id,
        'name': name,
        'is_group': conv.type == Conversation.Types.GROUP,
        'last_message': (last.content or '[pièce jointe]')[:40] if last else '',
        'last_time': last.created_at.strftime('%H:%M') if last else '',
    }


@login_required
def messaging_page(request):
    users = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
    return render(request, 'messaging/index.html', {
        'page_title': 'Messagerie',
        'users_json': json.dumps([{
            'id': u.id,
            'name': u.get_full_name() or u.username,
            'initial': (u.first_name or u.username)[:1].upper(),
        } for u in users]),
    })


@login_required
def api_conversations(request):
    memberships = ConversationMember.objects.filter(
        user=request.user, is_active=True).select_related('conversation')
    return JsonResponse({'conversations': [
        _conversation_data(m.conversation, request.user) for m in memberships]})


@login_required
def api_messages(request, conv_id):
    conv = Conversation.objects.get(pk=conv_id)
    try:
        conv.assert_member(request.user)
    except PermissionError:
        return JsonResponse({'error': 'Accès refusé.'}, status=403)

    messages = []
    for m in conv.messages.filter(is_deleted=False).select_related('sender')[:100]:
        if not m.is_visible:
            continue
        attachments = [{
            'type': a.file_type,
            'url': a.file.url,
            'name': a.original_name or a.file.name.split('/')[-1],
            'is_image': a.file_type == MessageAttachment.Types.IMAGE,
        } for a in m.attachments.all()]
        messages.append({
            'id': m.id,
            'sender': m.sender.get_full_name() or m.sender.username if m.sender else '—',
            'mine': m.sender_id == request.user.id,
            'content': m.content,
            'time': m.created_at.strftime('%H:%M'),
            'date': m.created_at.strftime('%d/%m/%Y'),
            'attachments': attachments,
            'ephemeral_hours': m.ephemeral_hours,
        })
    messages.reverse()
    return JsonResponse({'messages': messages, 'conversation': _conversation_data(conv, request.user)})


@login_required
@require_POST
def api_send(request, conv_id):
    conv = Conversation.objects.get(pk=conv_id)
    try:
        conv.assert_member(request.user)
    except PermissionError:
        return JsonResponse({'success': False, 'message': 'Accès refusé.'}, status=403)

    data = json.loads(request.body)
    content = data.get('content', '').strip()
    if not content:
        return JsonResponse({'success': False, 'message': 'Message vide.'}, status=400)

    msg = Message.objects.create(
        conversation=conv, sender=request.user, content=content,
        ephemeral_hours=data.get('ephemeral_hours') or None,
    )
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='messaging', obj=msg, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'id': msg.id})


@login_required
@require_POST
def api_upload(request, conv_id):
    conv = Conversation.objects.get(pk=conv_id)
    try:
        conv.assert_member(request.user)
    except PermissionError:
        return JsonResponse({'success': False, 'message': 'Accès refusé.'}, status=403)

    f = request.FILES.get('file')
    content = request.POST.get('content', '').strip()
    if not f and not content:
        return JsonResponse({'success': False, 'message': 'Rien à envoyer.'}, status=400)

    msg = Message.objects.create(conversation=conv, sender=request.user, content=content)
    if f:
        mime = f.content_type or ''
        if f.size > MessageAttachment.MAX_SIZE:
            msg.delete()
            return JsonResponse({'success': False, 'message': 'Fichier trop volumineux (max 25 Mo).'}, status=400)
        if mime not in [m for lst in MessageAttachment.ALLOWED_MIME.values() for m in lst]:
            msg.delete()
            return JsonResponse({'success': False, 'message': f'Type de fichier non autorisé ({mime}).'}, status=400)
        ftype = next((t for t, lst in MessageAttachment.ALLOWED_MIME.items() if mime in lst), 'DOCUMENT')
        MessageAttachment.objects.create(
            message=msg, file=f, file_type=ftype, original_name=f.name, size=f.size)
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='messaging', obj=msg, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'id': msg.id})


@login_required
@require_POST
def api_start_conversation(request):
    data = json.loads(request.body)
    other = User.objects.get(pk=data['user_id'], is_active=True)
    existing = Conversation.objects.filter(
        type=Conversation.Types.PRIVATE,
        members__user=request.user, members__is_active=True,
    ).filter(members__user=other, members__is_active=True).first()
    if existing:
        return JsonResponse({'success': True, 'conversation_id': existing.id})
    conv = Conversation.objects.create(type=Conversation.Types.PRIVATE, created_by=request.user)
    ConversationMember.objects.create(conversation=conv, user=request.user,
                                      role=ConversationMember.Roles.ADMIN)
    ConversationMember.objects.create(conversation=conv, user=other)
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='messaging', obj=conv, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'conversation_id': conv.id})


@login_required
@require_POST
def api_create_group(request):
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    member_ids = data.get('member_ids', [])
    if not name:
        return JsonResponse({'success': False, 'message': 'Le groupe doit avoir un nom.'}, status=400)
    if not member_ids:
        return JsonResponse({'success': False, 'message': 'Sélectionnez au moins un membre.'}, status=400)

    conv = Conversation.objects.create(type=Conversation.Types.GROUP, name=name,
                                       created_by=request.user)
    ConversationMember.objects.create(conversation=conv, user=request.user,
                                      role=ConversationMember.Roles.ADMIN)
    for uid in member_ids:
        ConversationMember.objects.create(conversation=conv, user_id=uid)
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='messaging', obj=conv, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'conversation_id': conv.id})

@login_required
@require_POST
def api_delete_message(request, msg_id):
    """Suppression 'pour tous' — réservée à l'auteur du message."""
    msg = Message.objects.get(pk=msg_id)
    if msg.sender_id != request.user.id:
        return JsonResponse({'success': False, 'message': 'Seul l\'auteur peut supprimer.'}, status=403)
    msg.delete_for_all()  # flag is_deleted — l'historique reste en base (§16.1)
    log_event(user=request.user, action=AuditLog.Actions.DELETE,
              module='messaging', obj=msg, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': 'Message supprimé.'})