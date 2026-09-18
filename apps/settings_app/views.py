import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import get_current_rate
from apps.accounts.models import RegistrationCode, User

from .models import (CenterConfig, Company, Staff, ExchangeRate, LabExam,
                     LabSplitConfig, HomeCareSplitConfig, MedicineSplitConfig)


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


@login_required
def settings_page(request):
    from apps.centre.models import Service
    context = {
        'page_title': 'Configuration',
        'tab_list': [
            ('centre', 'Centre'),
            ('personnel', 'Personnel'),
            ('taux', 'Taux'),
            ('entreprises', 'Entreprises'),
            ('repartitions', 'Répartitions'),
            ('medecine', 'Médecine'),
            ('codes', 'Codes'),
            ('examens', 'Examens'),
            ('services', 'Services'),
        ],
        'center': CenterConfig.objects.first(),
        'staff_list': Staff.objects.all(),
        'rates': ExchangeRate.objects.all()[:10],
        'companies': Company.objects.all(),
        'lab_split': LabSplitConfig.objects.filter(is_active=True).first(),
        'home_split': HomeCareSplitConfig.objects.filter(is_active=True).first(),
        'medicine_splits': MedicineSplitConfig.objects.filter(is_active=True),
        'medicine_categories': MedicineSplitConfig.Categories,
        'exams': LabExam.objects.all(),
        'services': Service.objects.all(),
        'taux': get_current_rate(),
        'invitation_codes': RegistrationCode.objects.select_related('created_by', 'used_by')[:50],
        'user_roles': User.Roles,  # ← import : from apps.accounts.models import User
    }
    return render(request, 'settings_app/index.html', context)


# ================= CENTRE =================
@login_required
@require_POST
@transaction.atomic
def center_update(request):
    data = json.loads(request.body)
    c = CenterConfig.objects.first()
    if c is None:
        c = CenterConfig(pk=1)
    c.name = data.get('name', c.name or '').strip()
    c.address = data.get('address', c.address or '').strip()
    c.phone = data.get('phone', c.phone or '').strip()
    c.email = data.get('email', c.email or '').strip()
    c.default_doctor_id = data.get('default_doctor_id') or None
    c.save()
    log_event(user=request.user, action=AuditLog.Actions.UPDATE,
              module='settings_app', obj=c, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': 'Configuration du centre enregistrée.'})


@login_required
@require_POST
@transaction.atomic
def center_logo(request):
    c = CenterConfig.objects.first()
    if c is None:
        c = CenterConfig(pk=1, name='CRF-MK')
    if request.FILES.get('logo'):
        c.logo = request.FILES['logo']
        c.save()
        return JsonResponse({'success': True, 'message': 'Logo mis à jour.'})
    return JsonResponse({'success': False, 'message': 'Aucun fichier.'}, status=400)


# ================= PERSONNEL =================
@login_required
@require_POST
@transaction.atomic
def staff_create(request):
    data = json.loads(request.body)
    if not data.get('last_name') or not data.get('title'):
        return JsonResponse({'success': False, 'message': 'Nom et titre obligatoires.'}, status=400)
    s = Staff.objects.create(
        last_name=data['last_name'].strip(),
        first_name=data.get('first_name', '').strip(),
        sex=data.get('sex', ''),
        title=data['title'],
        phone=data.get('phone', '').strip(),
    )
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='settings_app', obj=s, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': f'{s} ajouté.'})


@login_required
@require_POST
@transaction.atomic
def staff_toggle(request, pk):
    s = Staff.objects.get(pk=pk)
    s.is_active = not s.is_active
    s.save(update_fields=['is_active'])
    log_event(user=request.user, action=AuditLog.Actions.UPDATE,
              module='settings_app', obj=s, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': f"{s} : {'activé' if s.is_active else 'désactivé'}."})


# ================= TAUX =================
@login_required
@require_POST
@transaction.atomic
def rate_create(request):
    try:
        data = json.loads(request.body)
        rate = ExchangeRate(
            currency_from=data.get('currency_from', 'USD'),
            currency_to=data.get('currency_to', 'FC'),
            rate=Decimal(str(data['rate'])),
            effective_from=data.get('effective_from') or timezone.now(),
            created_by=request.user,
        )
        rate.full_clean()
        rate.save()
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=rate, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Taux enregistré : {rate}.'})
    except (InvalidOperation, KeyError, ValueError) as e:
        return JsonResponse({'success': False, 'message': f'Données invalides : {e}'}, status=400)


# ================= ENTREPRISES =================
@login_required
@require_POST
@transaction.atomic
def company_create(request):
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Nom obligatoire.'}, status=400)
    c, created = Company.objects.get_or_create(
        name__iexact=name,
        defaults={'name': name,  # sans ça, l'entreprise était créée SANS nom (bug)
                  'email': data.get('email', ''), 'phone': data.get('phone', '')})
    if created:
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=c, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': f'Entreprise « {c.name} » enregistrée.'})


@login_required
@require_POST
@transaction.atomic
def company_toggle(request, pk):
    c = Company.objects.get(pk=pk)
    c.is_active = not c.is_active
    c.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'message': f"« {c.name} » : {'activée' if c.is_active else 'désactivée'}."})


# ================= RÉPARTITIONS =================
@login_required
@require_POST
@transaction.atomic
def lab_split_create(request):
    try:
        data = json.loads(request.body)
        cfg = LabSplitConfig(
            prescriber_pct=Decimal(str(data['prescriber_pct'])),
            lab_team_pct=Decimal(str(data['lab_team_pct'])),
            center_pct=Decimal(str(data['center_pct'])),
            effective_from=data.get('effective_from') or timezone.now(),
            created_by=request.user,
        )
        cfg.full_clean()
        cfg.save()
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=cfg, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Nouvelle répartition labo : {cfg}.'})
    except (InvalidOperation, KeyError, ValueError) as e:
        return JsonResponse({'success': False, 'message': f'Données invalides : {e}'}, status=400)


@login_required
@require_POST
@transaction.atomic
def home_split_create(request):
    try:
        data = json.loads(request.body)
        cfg = HomeCareSplitConfig(
            doctor_pct=Decimal(str(data['doctor_pct'])),
            center_pct=Decimal(str(data['center_pct'])),
            effective_from=data.get('effective_from') or timezone.now(),
            created_by=request.user,
        )
        cfg.full_clean()
        cfg.save()
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=cfg, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Nouvelle répartition domicile : {cfg}.'})
    except (InvalidOperation, KeyError, ValueError) as e:
        return JsonResponse({'success': False, 'message': f'Données invalides : {e}'}, status=400)


@login_required
@require_POST
@transaction.atomic
def medicine_split_create(request):
    """Nouvelle répartition médecine — versionnée comme les autres (§12.1)."""
    try:
        data = json.loads(request.body)
        cfg = MedicineSplitConfig(
            category=data['category'],
            prescriber_pct=Decimal(str(data['prescriber_pct'])),
            center_pct=Decimal(str(data['center_pct'])),
            effective_from=data.get('effective_from') or timezone.now(),
            created_by=request.user,
        )
        cfg.full_clean()
        cfg.save()
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=cfg, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Nouvelle répartition : {cfg}.'})
    except (InvalidOperation, KeyError, ValueError) as e:
        return JsonResponse({'success': False, 'message': f'Données invalides : {e}'}, status=400)


# ================= EXAMENS =================
@login_required
@require_POST
@transaction.atomic
def exam_toggle(request, pk):
    e = LabExam.objects.get(pk=pk)
    e.is_active = not e.is_active
    e.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'message': f"« {e.name} » : {'activé' if e.is_active else 'désactivé'}."})


@login_required
@require_POST
@transaction.atomic
def exam_update(request, pk):
    try:
        e = LabExam.objects.get(pk=pk)
        data = json.loads(request.body)
        e.price_usd = Decimal(str(data['price_usd']))
        e.price_fc = Decimal(str(data['price_fc']))
        e.observation = data.get('observation', e.observation)
        e.save()
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='settings_app', obj=e, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f"« {e.name} » mis à jour."})
    except (InvalidOperation, KeyError, ValueError):
        return JsonResponse({'success': False, 'message': 'Prix invalides.'}, status=400)


# ================= SERVICES DU CENTRE =================
@login_required
@require_POST
@transaction.atomic
def service_create(request):
    from apps.centre.models import Service
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'message': 'Nom obligatoire.'}, status=400)
        s, created = Service.objects.get_or_create(
            name__iexact=name,
            defaults={'price_usd': Decimal(str(data['price_usd'])),
                      'price_fc': Decimal(str(data['price_fc']))})
        if created:
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='settings_app', obj=s, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Service « {s.name} » enregistré.'})
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': 'Prix invalides.'}, status=400)


@login_required
@require_POST
@transaction.atomic
def service_toggle(request, pk):
    from apps.centre.models import Service
    s = Service.objects.get(pk=pk)
    s.is_active = not s.is_active
    s.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'message': f"« {s.name} » : {'activé' if s.is_active else 'désactivé'}."})

# ================= CODES D'INVITATION (§17.2) =================
@login_required
@require_POST
@transaction.atomic
def code_create(request):
    """Génère un code d'invitation (rôle + durée). Affiché une fois, copiable."""
    data = json.loads(request.body)
    role = data.get('role', 'STAFF')
    valid_days = int(data.get('valid_days', 7))
    max_uses = int(data.get('max_uses', 1))

    from datetime import timedelta
    code = RegistrationCode.objects.create(
        role=role,
        created_by=request.user,
        expires_at=timezone.now() + timedelta(days=valid_days),
        max_uses=max_uses,
    )
    log_event(user=request.user, action=AuditLog.Actions.CREATE,
              module='accounts', obj=code, ip_address=get_client_ip(request))
    return JsonResponse({
        'success': True,
        'message': 'Code généré — copie-le maintenant, il ne sera plus affiché en clair.',
        'code': code.code,
        'role': code.get_role_display(),
        'expires': f"{code.expires_at:%d/%m/%Y %H:%M}",
    })


# ========================= Modification du service, tarf etc... ====================
@login_required
@require_POST
@transaction.atomic
def code_toggle(request, pk):
    """Révoque / réactive un code d'invitation."""
    c = RegistrationCode.objects.get(pk=pk)
    c.is_active = not c.is_active
    c.save(update_fields=['is_active'])
    log_event(user=request.user, action=AuditLog.Actions.UPDATE,
              module='accounts', obj=c, ip_address=get_client_ip(request))
    return JsonResponse({'success': True,
                         'message': f"Code {c.code[:8]}… : {'réactivé' if c.is_active else 'révoqué'}."})
    
@login_required
@require_POST
@transaction.atomic
def service_update(request, pk):
    """Modification d'un service du centre (nom + tarifs $/FC)."""
    from apps.centre.models import Service
    try:
        s = Service.objects.get(pk=pk)
        data = json.loads(request.body)
        if data.get('name', '').strip():
            s.name = data['name'].strip()
        s.price_usd = Decimal(str(data['price_usd']))
        s.price_fc = Decimal(str(data['price_fc']))
        if s.price_usd <= 0 or s.price_fc <= 0:
            return JsonResponse({'success': False, 'message': 'Prix invalides.'}, status=400)
        s.save()
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='settings_app', obj=s, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'Service « {s.name} » mis à jour.'})
    except (Service.DoesNotExist, InvalidOperation, KeyError, ValueError):
        return JsonResponse({'success': False, 'message': 'Données invalides.'}, status=400)