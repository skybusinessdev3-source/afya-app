import json
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.core.utils import can_backdate, parse_operation_date
from .models import Expense, Invoice, Payment, get_current_rate


def _facture_credit_entreprise(inv):
    """True si le patient appartient à une entreprise « facturée à
    l'entreprise » (ex : LTJ) → créance entreprise, jamais dette patient."""
    return bool(inv.patient and inv.patient.company
                and inv.patient.company.facturation_entreprise)


def _creance_info(inv):
    """Si cette facture a un solde restant et qu'aucune décision n'a été
    prise → infos pour le modal « Stocker cette créance ? » (sinon None)."""
    if inv is None or inv.patient is None or inv.balance_usd <= 0 \
            or inv.debt_tracked is not None:
        return None
    if _facture_credit_entreprise(inv):
        return None  # créance entreprise : pas de question, rapport à part
    return {
        'invoice_id': inv.id,
        'reference': inv.reference,
        'patient': inv.patient.full_name,
        'balance': str(inv.balance_usd),
    }


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
@require_POST
def expense_create(request):
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', '0')))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Le montant doit être positif."}, status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        expense = Expense.objects.create(
            label=data.get('label', '').strip(),
            person_id=data.get('person_id') or None,
            person_other=data.get('person_other', '').strip(),
            amount_original=amount,
            currency_original=data.get('currency', 'USD'),
            date=op_date,
            observation=data.get('observation', '').strip(),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=expense, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Dépense « {expense.label} » enregistrée.",
            'id': expense.id,
        })
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'message': "Libellé obligatoire."}, status=400)


@login_required
def debts_page(request):
    """Créances = factures non annulées avec solde dû, confirmées au stockage.
    - Les impayés des patients d'entreprises « facturées à l'entreprise »
      (ex : LTJ) sont exclus → rapport entreprises (créances entreprises).
    - Les soldes « en attente de décision » sont listés à part (à confirmer)."""
    base = [i for i in Invoice.objects
            .exclude(status=Invoice.Status.CANCELLED)
            .select_related('patient', 'patient__company')
            .prefetch_related('payments')
            if i.balance_usd > 0 and not _facture_credit_entreprise(i)]
    invoices = [i for i in base if i.debt_tracked is True]
    en_attente = [i for i in base if i.debt_tracked is None]
    context = {
        'page_title': 'Dettes (créances)',
        'invoices': invoices,
        'en_attente': en_attente,
        'total_debt': sum(i.balance_usd for i in invoices),
        'total_attente': sum(i.balance_usd for i in en_attente),
        'today': timezone.localdate(),
        'can_backdate': can_backdate(request.user),
    }
    return render(request, 'finance/debts.html', context)


@login_required
@require_POST
def creance_decide(request):
    """Décision du modal « Stocker cette créance ? » (oui / non)."""
    try:
        data = json.loads(request.body)
        inv = Invoice.objects.get(pk=data.get('invoice_id'))
        decision = data.get('decision')
        if decision not in ('oui', 'non'):
            return JsonResponse({'success': False, 'message': "Décision invalide."}, status=400)
        inv.debt_tracked = (decision == 'oui')
        inv.save(update_fields=['debt_tracked'])
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='finance', obj=inv,
                  new_value={'creance_stockee': inv.debt_tracked},
                  ip_address=get_client_ip(request))
        msg = (f"Créance de {inv.balance_usd} $ stockée ({inv.reference})."
               if inv.debt_tracked else f"Créance ignorée ({inv.reference}).")
        return JsonResponse({'success': True, 'message': msg})
    except Invoice.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Facture introuvable."}, status=404)


@login_required
@require_POST
@transaction.atomic
def debt_pay(request):
    """Enregistre un paiement contre une facture impayée (régularisation de dette)."""
    try:
        data = json.loads(request.body)
        inv = Invoice.objects.get(pk=data.get('invoice_id'))
        if inv.status == Invoice.Status.CANCELLED:
            return JsonResponse({'success': False, 'message': "Facture annulée — paiement impossible."},
                                status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        # 1 ou 2 paiements (paiement mixte $ + FC)
        cur1 = data.get('currency', 'USD')
        paiements = [
            (Decimal(str(data.get('amount', '0') or '0')), cur1),
            (Decimal(str(data.get('amount2', '0') or '0')),
             data.get('currency2') or ('FC' if cur1 == 'USD' else 'USD')),
        ]
        paiements = [(a, c) for a, c in paiements if a > 0]
        if not paiements:
            return JsonResponse({'success': False, 'message': "Le montant doit être positif."}, status=400)

        # Anti trop-perçu : on compare le TOTAL en USD (taux figé à l'enregistrement)
        rate = get_current_rate()
        total_usd = sum(((a / rate).quantize(Decimal('0.01')) if c == 'FC' else a)
                        for a, c in paiements)
        if total_usd > inv.balance_usd:
            return JsonResponse({'success': False,
                                 'message': f"Montant supérieur au reste dû ({inv.balance_usd} $)."},
                                status=400)

        for amount, currency in paiements:
            payment = Payment.objects.create(
                invoice=inv,
                amount_original=amount,
                currency_original=currency,
                date=op_date,
                received_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        reste = inv.balance_usd
        msg = (f"Facture {inv.reference} soldée ✔" if reste <= 0
               else f"Paiement enregistré — reste dû : {reste} $.")
        return JsonResponse({'success': True, 'message': msg, 'balance': str(reste)})

    except Invoice.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Facture introuvable."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)

# ================= OPÉRATIONS (annuler / modifier — SUPERUSER uniquement) =================

def _superuser_required(request):
    if not request.user.is_superuser:
        return JsonResponse({'success': False,
                             'message': "Action réservée à l'administrateur."}, status=403)
    return None


@login_required
def operations_page(request):
    """Journal des opérations récentes avec annulation/modification.
    Réservé au super-utilisateur (Rossy) — même pas le directeur."""
    if not request.user.is_superuser:
        return render(request, '403.html', status=403)

    from apps.appointments.models import Appointment
    from apps.centre.models import Session
    from apps.home_care.models import HomeCareService
    from apps.laboratory.models import LaboratoryRecord
    from apps.medicine.models import MedicineRecord
    from apps.pharmacy.models import PharmacySale

    ops = []

    for p in Payment.objects.select_related('invoice__patient', 'received_by').order_by('-id'):
        inv = p.invoice
        ops.append({
            'type': 'payment', 'id': p.id, 'date': p.date, 'created': p.created_at,
            'desc': f"Paiement {inv.reference if inv else ''} — "
                    f"{inv.patient.full_name if inv and inv.patient else 'Générique'}",
            'amount': f"{p.amount_original} {p.currency_original}",
            'by': str(p.received_by or '—'),
            'status': p.get_status_display(),
            'inactive': p.status == Payment.Status.CANCELLED,
            'cancelable': p.status == Payment.Status.VALID,
            'editable': p.status == Payment.Status.VALID,
        })

    for inv in Invoice.objects.select_related('patient', 'created_by').order_by('-id'):
        n_pay = inv.payments.filter(status=Payment.Status.VALID).count()
        ops.append({
            'type': 'invoice', 'id': inv.id, 'date': inv.date, 'created': inv.created_at,
            'desc': f"Facture {inv.reference} — {inv.label} — "
                    f"{inv.patient.full_name if inv.patient else 'Générique'}",
            'amount': f"{inv.amount_original} {inv.currency_original}",
            'by': str(inv.created_by or '—'),
            'status': inv.get_status_display(),
            'inactive': inv.status == Invoice.Status.CANCELLED,
            'cancelable': inv.status != Invoice.Status.CANCELLED and n_pay == 0,
            'editable': False,
        })

    for e in Expense.objects.select_related('created_by').order_by('-id'):
        ops.append({
            'type': 'expense', 'id': e.id, 'date': e.date, 'created': e.created_at,
            'desc': f"Dépense — {e.label}",
            'amount': f"{e.amount_original} {e.currency_original}",
            'by': str(e.created_by or '—'), 'status': '—',
            'inactive': False, 'cancelable': True, 'editable': True,
        })

    for se in Session.objects.select_related('patient').order_by('-id'):
        ops.append({
            'type': 'session', 'id': se.id, 'date': se.date, 'created': se.created_at,
            'desc': f"Séance — {se.patient.full_name} ({se.get_motif_display()})",
            'amount': '', 'by': str(se.professional or '—'),
            'status': se.get_status_display(),
            'inactive': False, 'cancelable': True, 'editable': False,
        })

    for v in PharmacySale.objects.select_related('patient', 'product', 'sold_by').order_by('-id'):
        ops.append({
            'type': 'sale', 'id': v.id, 'date': v.date, 'created': v.created_at,
            'desc': f"Vente — {v.product.name} x{v.quantity} — "
                    f"{v.patient.full_name if v.patient else 'Client comptant'}",
            'amount': f"{v.total_usd} $",
            'by': str(v.sold_by or '—'), 'status': '—',
            'inactive': False, 'cancelable': True, 'editable': False,
        })

    for r in LaboratoryRecord.objects.select_related('patient', 'exam').order_by('-id'):
        ops.append({
            'type': 'lab', 'id': r.id, 'date': r.date, 'created': r.created_at,
            'desc': f"Examen — {r.patient.full_name} — {r.exam.name}",
            'amount': f"{r.amount_original} {r.currency_original}",
            'by': str(r.created_by or '—'), 'status': r.get_status_display(),
            'inactive': False, 'cancelable': True, 'editable': True,
        })

    for r in MedicineRecord.objects.select_related('patient').order_by('-id'):
        ops.append({
            'type': 'med', 'id': r.id, 'date': r.date, 'created': r.created_at,
            'desc': f"Médecine — {r.patient.full_name} — {r.get_category_display()}",
            'amount': f"{r.amount_original} {r.currency_original}",
            'by': str(r.created_by or '—'), 'status': r.get_status_display(),
            'inactive': False, 'cancelable': True, 'editable': True,
        })

    for r in HomeCareService.objects.select_related('patient').order_by('-id'):
        is_consult = getattr(r, 'service_type', 'SOINS') == 'CONSULTATION'
        ops.append({
            'type': 'home', 'id': r.id, 'date': r.date, 'created': r.created_at,
            'desc': (f"Consultation à domicile — {r.patient.full_name}"
                     if is_consult else
                     f"Domicile — {r.patient.full_name} "
                     f"({r.sessions_done}/{r.sessions_prescribed} séances)"),
            'amount': '', 'by': str(r.created_by or '—'), 'status': '—',
            'inactive': False, 'cancelable': True, 'editable': False,
        })

    for a in Appointment.objects.select_related('patient').order_by('-id'):
        ops.append({
            'type': 'rdv', 'id': a.id, 'date': a.datetime.date(), 'created': a.created_at,
            'desc': f"RDV — {a.patient.full_name} — {a.motif} "
                    f"({a.datetime:%d/%m/%Y %H:%M})",
            'amount': '', 'by': str(a.created_by or '—'),
            'status': a.get_status_display(),
            'inactive': a.status == Appointment.Status.CANCELLED,
            'cancelable': a.status != Appointment.Status.CANCELLED,
            'editable': False,
        })

    # ----- Filtres (type, recherche, période) -----
    ftype = request.GET.get('type', '')
    q = request.GET.get('q', '').strip()
    try:
        fd1 = date_cls.fromisoformat(request.GET.get('d1', ''))
    except ValueError:
        fd1 = None
    try:
        fd2 = date_cls.fromisoformat(request.GET.get('d2', ''))
    except ValueError:
        fd2 = None
    if ftype:
        ops = [o for o in ops if o['type'] == ftype]
    if q:
        needle = q.casefold()
        ops = [o for o in ops
               if needle in f"{o['desc']} {o['amount']} {o['by']}".casefold()]
    if fd1:
        ops = [o for o in ops if o['date'] >= fd1]
    if fd2:
        ops = [o for o in ops if o['date'] <= fd2]

    ops.sort(key=lambda o: o['created'], reverse=True)

    # ----- Pagination (25 par page, navigation façon Google) -----
    paginator = Paginator(ops, 25)
    page = paginator.get_page(request.GET.get('page'))
    num, total_pages = page.number, paginator.num_pages
    pages_num = [p for p in range(1, total_pages + 1)
                 if p <= 3 or p == total_pages or abs(p - num) <= 1]
    pages_shown = []
    prev = None
    for p in pages_num:
        if prev is not None and p - prev > 1:
            pages_shown.append('…')
        pages_shown.append(p)
        prev = p

    from urllib.parse import urlencode
    qs = urlencode({k: v for k, v in {
        'type': ftype, 'q': q,
        'd1': fd1.isoformat() if fd1 else '',
        'd2': fd2.isoformat() if fd2 else '',
    }.items() if v})

    return render(request, 'finance/operations.html', {
        'page_title': 'Opérations',
        'ops': page,
        'page': page,
        'pages_shown': pages_shown,
        'total_ops': paginator.count,
        'qs': qs,
        'ftype': ftype, 'q': q,
        'd1': fd1.isoformat() if fd1 else '',
        'd2': fd2.isoformat() if fd2 else '',
        'op_types': [
            ('payment', 'Paiements'), ('invoice', 'Factures'),
            ('expense', 'Dépenses'), ('session', 'Séances (centre)'),
            ('sale', 'Ventes (pharmacie)'), ('lab', 'Examens (labo)'),
            ('med', 'Actes médecine'), ('home', 'Soins à domicile'),
            ('rdv', 'Rendez-vous'),
        ],
    })


@login_required
@require_POST
@transaction.atomic
def operation_cancel(request):
    """Annule une opération (superuser uniquement). Tout est tracé au journal."""
    deny = _superuser_required(request)
    if deny:
        return deny
    try:
        data = json.loads(request.body)
        otype, oid = data.get('type'), int(data.get('id'))
        reason = data.get('reason', '').strip()
        if not reason:
            return JsonResponse({'success': False, 'message': "Motif obligatoire."}, status=400)

        from apps.appointments.models import Appointment
        from apps.centre.models import Session
        from apps.home_care.models import HomeCareService
        from apps.laboratory.models import LaboratoryRecord
        from apps.medicine.models import MedicineRecord
        from apps.pharmacy.models import PharmacySale, StockMovement

        if otype == 'payment':
            obj = Payment.objects.get(pk=oid)
            obj.cancel(request.user, reason)
            msg = f"Paiement de {obj.amount_original} {obj.currency_original} annulé."

        elif otype == 'invoice':
            obj = Invoice.objects.get(pk=oid)
            if obj.payments.filter(status=Payment.Status.VALID).exists():
                return JsonResponse({'success': False,
                                     'message': "Cette facture a des paiements valides — "
                                                "annulez d'abord les paiements."}, status=400)
            obj.cancel(request.user, reason)
            msg = f"Facture {obj.reference} annulée."

        elif otype == 'expense':
            obj = Expense.objects.get(pk=oid)
            msg = f"Dépense « {obj.label} » ({obj.amount_original} {obj.currency_original}) supprimée."
            obj.delete()
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='finance', obj=None,
                      old_value={'type': 'expense', 'id': oid, 'motif': reason},
                      ip_address=get_client_ip(request))
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'session':
            obj = Session.objects.get(pk=oid)
            msg = f"Séance de {obj.patient.full_name} ({obj.date:%d/%m/%Y}) supprimée."
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='centre', obj=None,
                      old_value={'type': 'session', 'id': oid,
                                 'patient': obj.patient.full_name, 'motif': reason},
                      ip_address=get_client_ip(request))
            obj.delete()
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'sale':
            obj = PharmacySale.objects.select_related('product', 'patient').get(pk=oid)
            StockMovement.objects.filter(sale=obj).delete()   # stock restauré
            msg = (f"Vente « {obj.product.name} x{obj.quantity} » supprimée "
                   f"(stock restauré).")
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='pharmacy', obj=None,
                      old_value={'type': 'sale', 'id': oid, 'motif': reason},
                      ip_address=get_client_ip(request))
            obj.delete()
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'lab':
            obj = LaboratoryRecord.objects.select_related('patient', 'exam').get(pk=oid)
            msg = f"Examen « {obj.exam.name} » de {obj.patient.full_name} supprimé."
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='laboratory', obj=None,
                      old_value={'type': 'lab', 'id': oid, 'motif': reason},
                      ip_address=get_client_ip(request))
            obj.delete()
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'med':
            obj = MedicineRecord.objects.select_related('patient').get(pk=oid)
            msg = f"Acte médecine de {obj.patient.full_name} supprimé."
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='medicine', obj=None,
                      old_value={'type': 'med', 'id': oid, 'motif': reason},
                      ip_address=get_client_ip(request))
            obj.delete()
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'home':
            obj = HomeCareService.objects.select_related('patient').get(pk=oid)
            msg = f"Prestation à domicile de {obj.patient.full_name} supprimée."
            log_event(user=request.user, action=AuditLog.Actions.DELETE,
                      module='home_care', obj=None,
                      old_value={'type': 'home', 'id': oid, 'motif': reason},
                      ip_address=get_client_ip(request))
            obj.delete()
            return JsonResponse({'success': True, 'message': msg})

        elif otype == 'rdv':
            obj = Appointment.objects.select_related('patient').get(pk=oid)
            obj.status = Appointment.Status.CANCELLED
            obj.save(update_fields=['status'])
            msg = f"Rendez-vous de {obj.patient.full_name} annulé."

        else:
            return JsonResponse({'success': False, 'message': "Type inconnu."}, status=400)

        log_event(user=request.user, action=AuditLog.Actions.CANCEL,
                  module='finance' if otype in ('payment', 'invoice') else otype,
                  obj=obj if otype in ('payment', 'invoice', 'rdv') else None,
                  old_value={'type': otype, 'id': oid, 'motif': reason},
                  ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f"Introuvable : {e}"}, status=404)


@login_required
@require_POST
@transaction.atomic
def operation_update(request):
    """Modifie une opération (superuser uniquement) :
    - paiement : montant, devise, date, méthode
    - dépense  : libellé, montant, devise, date
    - examen labo / acte médecine : prescripteur
    """
    deny = _superuser_required(request)
    if deny:
        return deny
    try:
        data = json.loads(request.body)
        otype, oid = data.get('type'), int(data.get('id'))
        f = data.get('fields', {})

        if otype == 'payment':
            obj = Payment.objects.get(pk=oid)
            if obj.status == Payment.Status.CANCELLED:
                return JsonResponse({'success': False, 'message': "Paiement déjà annulé."}, status=400)
            if f.get('amount'):
                obj.amount_original = Decimal(str(f['amount']))
                if obj.amount_original <= 0:
                    return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
            if f.get('currency') in ('USD', 'FC'):
                obj.currency_original = f['currency']
            if f.get('date'):
                obj.date = date_cls.fromisoformat(f['date'])
            if f.get('method') in ('CASH', 'MOBILE_MONEY', 'BANK'):
                obj.method = f['method']
            obj.save()   # recalcule amount_usd + statut facture automatiquement
            msg = f"Paiement modifié ({obj.amount_original} {obj.currency_original})."

        elif otype == 'expense':
            obj = Expense.objects.get(pk=oid)
            if f.get('label'):
                obj.label = f['label'].strip()
            if f.get('amount'):
                obj.amount_original = Decimal(str(f['amount']))
                if obj.amount_original <= 0:
                    return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
            if f.get('currency') in ('USD', 'FC'):
                obj.currency_original = f['currency']
            if f.get('date'):
                obj.date = date_cls.fromisoformat(f['date'])
            obj.save()
            msg = f"Dépense « {obj.label} » modifiée."

        elif otype == 'lab':
            from apps.laboratory.models import LaboratoryRecord
            obj = LaboratoryRecord.objects.get(pk=oid)
            obj.prescriber_name = f.get('prescriber_name', obj.prescriber_name).strip()
            obj.save(update_fields=['prescriber_name'])
            msg = f"Prescripteur modifié : {obj.prescriber_name or '—'}."

        elif otype == 'med':
            from apps.medicine.models import MedicineRecord
            obj = MedicineRecord.objects.get(pk=oid)
            obj.prescriber_name = f.get('prescriber_name', obj.prescriber_name).strip()
            obj.save(update_fields=['prescriber_name'])
            msg = f"Prescripteur modifié : {obj.prescriber_name or '—'}."

        else:
            return JsonResponse({'success': False,
                                 'message': "Ce type ne se modifie pas (annulez puis re-saisissez)."},
                                status=400)

        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='finance' if otype in ('payment', 'expense') else otype, obj=obj,
                  new_value={'type': otype, 'id': oid, 'champs': f},
                  ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': msg})

    except (InvalidOperation, ValueError) as e:
        return JsonResponse({'success': False, 'message': f"Données invalides : {e}"}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f"Introuvable : {e}"}, status=404)
