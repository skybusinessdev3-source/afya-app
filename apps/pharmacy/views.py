import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import Invoice, Payment
from apps.patients.models import Patient
from .models import PharmacyProduct, PharmacySale, StockMovement


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
def pharmacy_sale(request):
    today = timezone.localdate()
    sales_today = PharmacySale.objects.filter(date=today).select_related('product', 'patient')
    context = {
        'page_title': 'Pharmacie',
        'today': today,
        'sales_today': sales_today,
        'sales_total_usd': sum(s.total_usd for s in sales_today),
        'sales_total_fc': sum(s.total_fc for s in sales_today),
        'count_today': sales_today.count(),
    }
    return render(request, 'pharmacy/sale.html', context)


@login_required
def product_search(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    products = PharmacyProduct.objects.filter(Q(name__icontains=q), is_active=True)[:8]
    results = [{
        'id': p.id,
        'name': p.name,
        'price_usd': float(p.price_usd),
        'price_fc': float(p.price_fc),
        'stock': p.stock_available,
    } for p in products]
    return JsonResponse({'results': results})


@login_required
@require_POST
@transaction.atomic
def sale_create(request):
    """
    Vente panier : plusieurs produits d'un coup.
    - 1 facture unique (total recalculé CÔTÉ SERVEUR)
    - 1 vente + 1 mouvement de stock par produit
    - paiement éventuel (devise libre)
    """
    try:
        data = json.loads(request.body)

        patient_id = data.get('patient_id')
        patient = Patient.objects.filter(pk=patient_id, is_active=True).first() if patient_id else None

        items = data.get('items', [])
        if not items:
            return JsonResponse({'success': False, 'message': "Ajoutez au moins un produit."}, status=400)

        # Vérification stock + récupération produits (serveur = autorité, §11)
        lines = []
        for it in items:
            product = PharmacyProduct.objects.select_for_update().get(
                pk=it['product_id'], is_active=True)
            qty = int(it.get('quantity', 1))
            if qty <= 0:
                return JsonResponse({'success': False, 'message': f"Quantité invalide : {product.name}"}, status=400)
            if qty > product.stock_available:
                return JsonResponse({
                    'success': False,
                    'message': f"Stock insuffisant pour « {product.name} » "
                               f"(dispo: {product.stock_available}, demandé: {qty}).",
                }, status=400)
            lines.append((product, qty))

        # Total recalculé serveur
        currency = data.get('currency', 'USD')
        total_usd = sum(p.price_usd * q for p, q in lines)
        total_fc = sum(p.price_fc * q for p, q in lines)
        due = total_fc if currency == 'FC' else total_usd

        # Ventes + mouvements (créés par le modèle)
        for product, qty in lines:
            sale = PharmacySale.objects.create(
                patient=patient, product=product, quantity=qty, sold_by=request.user)
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='pharmacy', obj=sale, ip_address=get_client_ip(request))

        invoice = Invoice.objects.create(
            patient=patient,
            label=f"Pharmacie — {len(lines)} article(s)",
            amount_original=due,
            currency_original=currency,
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=invoice, ip_address=get_client_ip(request))

        amount_paid = Decimal(str(data.get('amount_paid', '0') or '0'))
        if amount_paid > 0:
            payment = Payment.objects.create(
                invoice=invoice,
                amount_original=amount_paid,
                currency_original=data.get('paid_currency', currency),
                received_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Vente enregistrée : {len(lines)} article(s)"
                       + (f" pour {patient.full_name}" if patient else " (client comptant)"),
            'total_usd': float(total_usd),
            'total_fc': float(total_fc),
        })

    except PharmacyProduct.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Produit introuvable."}, status=404)
    except (InvalidOperation, ValueError, KeyError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)


@login_required
@require_POST
@transaction.atomic
def product_create(request):
    """Crée un produit + mouvement d'entrée de stock initial (tracé)."""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        price_usd = Decimal(str(data.get('price_usd', '0')))
        price_fc = Decimal(str(data.get('price_fc', '0')))
        initial_qty = int(data.get('initial_qty', 0) or 0)

        if not name or price_usd <= 0 or price_fc <= 0:
            return JsonResponse({'success': False, 'message': "Nom et prix ($ et FC) obligatoires."}, status=400)
        if PharmacyProduct.objects.filter(name__iexact=name).exists():
            return JsonResponse({'success': False, 'message': "Un produit porte déjà ce nom."}, status=400)

        product = PharmacyProduct.objects.create(
            name=name, price_usd=price_usd, price_fc=price_fc,
            expiry_date=data.get('expiry_date') or None,
            observation=data.get('observation', ''),
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='pharmacy', obj=product, ip_address=get_client_ip(request))

        if initial_qty > 0:
            movement = StockMovement.objects.create(
                product=product, movement_type=StockMovement.Type.IN,
                quantity=initial_qty, reason="Stock initial", created_by=request.user)
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='pharmacy', obj=movement, ip_address=get_client_ip(request))

        return JsonResponse({'success': True,
                             'message': f"Produit « {product.name} » créé (stock : {product.stock_available})."})
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)