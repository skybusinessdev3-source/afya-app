import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import Invoice, Payment
from apps.patients.models import Patient
from .models import PharmacyProduct, PharmacySale


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
    """Recherche instantanée de produits (AJAX)."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    products = PharmacyProduct.objects.filter(
        Q(name__icontains=q), is_active=True,
    )[:8]

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
    Enregistre une vente : déduit le stock (mouvement tracé automatique)
    + facture du MONTANT DÛ + paiement éventuel.
    """
    try:
        data = json.loads(request.body)
        product = PharmacyProduct.objects.get(pk=data['product_id'], is_active=True)
        quantity = int(data.get('quantity', 1))

        if quantity <= 0:
            return JsonResponse({'success': False, 'message': "Quantité invalide."}, status=400)

        # Anti stock négatif : vérifié CÔTÉ SERVEUR (§11)
        if quantity > product.stock_available:
            return JsonResponse({
                'success': False,
                'message': f"Stock insuffisant pour « {product.name} » "
                           f"(disponible : {product.stock_available}, demandé : {quantity}).",
            }, status=400)

        patient_id = data.get('patient_id') or None
        patient = Patient.objects.filter(pk=patient_id, is_active=True).first() if patient_id else None

        # --- Vente (le mouvement de stock est créé automatiquement par le modèle) ---
        sale = PharmacySale.objects.create(
            patient=patient,
            product=product,
            quantity=quantity,
            sold_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='pharmacy', obj=sale, ip_address=get_client_ip(request))

        # --- Facture du montant dû + paiement éventuel ---
        currency = data.get('currency', 'USD')
        due = sale.total_fc if currency == 'FC' else sale.total_usd
        invoice = Invoice.objects.create(
            patient=patient,
            label=f"Pharmacie — {product.name} ×{quantity}",
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
                currency_original=currency,
                received_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Vente enregistrée : {product.name} ×{quantity}",
            'stock_remaining': product.stock_available,
            'total_usd': float(sale.total_usd),
            'total_fc': float(sale.total_fc),
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
            name=name,
            price_usd=price_usd,
            price_fc=price_fc,
            expiry_date=data.get('expiry_date') or None,
            observation=data.get('observation', ''),
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='pharmacy', obj=product, ip_address=get_client_ip(request))

        if initial_qty > 0:
            movement = StockMovement.objects.create(
                product=product,
                movement_type=StockMovement.Type.IN,
                quantity=initial_qty,
                reason="Stock initial",
                created_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='pharmacy', obj=movement, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Produit « {product.name} » créé (stock : {product.stock_available}).",
        })

    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)