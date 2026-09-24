import json
from datetime import date as date_cls, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.centre.models import Session
from apps.finance.models import Expense, Payment, get_current_rate


def landing(request):
    """Page d'accueil animée (non connectés). Les connectés vont au dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html')


def service_worker(request):
    """Sert sw.js avec autorisation de contrôler tout le site (scope /)."""
    response = FileResponse(open(settings.BASE_DIR / 'static' / 'sw.js', 'rb'),
                            content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


@login_required
def dashboard(request):
    today = timezone.localdate()

    sessions_today = Session.objects.filter(date=today)
    patients_today = sessions_today.values('patient').distinct().count()

    # Recettes SÉPARÉES par devise (jamais additionnées — règle métier)
    payments = Payment.objects.filter(date=today, status=Payment.Status.VALID)
    rev_usd = payments.filter(currency_original='USD').aggregate(
        t=Sum('amount_original'))['t'] or 0
    rev_fc = payments.filter(currency_original='FC').aggregate(
        t=Sum('amount_original'))['t'] or 0

    # Dépenses séparées par devise
    expenses = Expense.objects.filter(date=today)
    exp_usd = expenses.filter(currency_original='USD').aggregate(
        t=Sum('amount_original'))['t'] or 0
    exp_fc = expenses.filter(currency_original='FC').aggregate(
        t=Sum('amount_original'))['t'] or 0

    # --- Données du graphique : 7 derniers jours ---
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    chart_labels, chart_usd, chart_fc = [], [], []
    chart_exp_usd, chart_exp_fc = [], []
    for d in days:
        p = Payment.objects.filter(date=d, status=Payment.Status.VALID)
        e = Expense.objects.filter(date=d)
        chart_labels.append(d.strftime('%d/%m'))
        chart_usd.append(float(p.filter(currency_original='USD').aggregate(
            t=Sum('amount_original'))['t'] or 0))
        chart_fc.append(float(p.filter(currency_original='FC').aggregate(
            t=Sum('amount_original'))['t'] or 0))
        chart_exp_usd.append(float(e.filter(currency_original='USD').aggregate(
            t=Sum('amount_original'))['t'] or 0))
        chart_exp_fc.append(float(e.filter(currency_original='FC').aggregate(
            t=Sum('amount_original'))['t'] or 0))

    # --- Journal d'activité : 30 derniers jours (transparence — qui a fait quoi, quand) ---
    recent_activity = (AuditLog.objects
                       .filter(created_at__date__gte=today - timedelta(days=30))
                       .select_related('user')[:50])

    context = {
        'page_title': 'Tableau de bord',
        'today': today,
        'recent_activity': recent_activity,
        'patients_today': patients_today,
        'sessions_today_count': sessions_today.count(),
        'rev_usd': rev_usd,
        'rev_fc': rev_fc,
        'exp_usd': exp_usd,
        'exp_fc': exp_fc,
        'net_usd': rev_usd - exp_usd,
        'net_fc': rev_fc - exp_fc,
        'chart_labels': json.dumps(chart_labels),
        'chart_usd': json.dumps(chart_usd),
        'chart_fc': json.dumps(chart_fc),
        'chart_exp_usd': json.dumps(chart_exp_usd),
        'chart_exp_fc': json.dumps(chart_exp_fc),
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def about_page(request):
    # SVG inline : "currentColor" hérite de la couleur du thème (clair/sombre auto)
    def bars():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<line x1="4" y1="24" x2="38" y2="24"/>'
                '<rect x="7" y="12" width="5" height="12" fill="currentColor" stroke="none"/>'
                '<rect x="16" y="6" width="5" height="18" fill="currentColor" stroke="none"/>'
                '<rect x="25" y="15" width="5" height="9" fill="currentColor" stroke="none"/></svg>')

    def pulse():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">'
                '<path d="M2 14 H12 L16 6 L22 22 L26 12 L29 14 H38"/></svg>')

    def users_svg():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<circle cx="14" cy="9" r="4.5"/><path d="M5 24 C5 17 23 17 23 24"/>'
                '<circle cx="29" cy="10" r="3.5"/><path d="M24 24 C24 19 36 19 36 24"/></svg>')

    def capsule():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<rect x="8" y="8" width="24" height="12" rx="6" transform="rotate(-30 20 14)"/>'
                '<line x1="14" y1="20" x2="26" y2="8"/></svg>')

    def drop():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<path d="M20 3 C20 3 10 14 10 19 a10 8 0 0 0 20 0 C30 14 20 3 20 3 Z"/></svg>')

    def house():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<path d="M6 14 L20 4 L34 14"/><path d="M10 13 V24 H30 V13"/>'
                '<path d="M20 24 V17" stroke-width="3"/></svg>')

    def calendar_svg():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<rect x="6" y="6" width="28" height="19" rx="3"/><line x1="6" y1="12" x2="34" y2="12"/>'
                '<line x1="13" y1="3" x2="13" y2="8"/><line x1="27" y1="3" x2="27" y2="8"/>'
                '<rect x="12" y="16" width="4" height="4" fill="currentColor" stroke="none"/></svg>')

    def chat():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5">'
                '<path d="M6 5 H26 a4 4 0 0 1 4 4 V15 a4 4 0 0 1 -4 4 H14 L8 24 V19 H6 a4 4 0 0 1 -4 -4 V9 a4 4 0 0 1 4 -4 Z"/>'
                '<circle cx="13" cy="12" r="1.4" fill="currentColor" stroke="none"/>'
                '<circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none"/>'
                '<circle cx="25" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>')

    def sliders():
        return ('<svg viewBox="0 0 40 28" class="w-8 h-8" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">'
                '<line x1="6" y1="8" x2="34" y2="8"/><circle cx="24" cy="8" r="3" fill="currentColor"/>'
                '<line x1="6" y1="20" x2="34" y2="20"/><circle cx="14" cy="20" r="3" fill="currentColor"/></svg>')

    features = [
        {"titre": "Tableau de bord", "desc": "Recettes, dépenses et graphiques 7 jours, par devise", "icon": "layout-dashboard", "svg": bars()},
        {"titre": "Centre (jour)", "desc": "Séances, paiements multi-devises, dépenses, nouveau patient", "icon": "stethoscope", "svg": pulse()},
        {"titre": "Patients", "desc": "Liste, recherche instantanée, fiche complète avec historique", "icon": "users", "svg": users_svg()},
        {"titre": "Pharmacie", "desc": "Ventes en panier, stock tracé, réapprovisionnement", "icon": "pill", "svg": capsule()},
        {"titre": "Laboratoire", "desc": "Examens tarifés, répartition 20/60/40 figée, suivi des parts versées", "icon": "flask-conical", "svg": drop()},
        {"titre": "Médecine générale", "desc": "Consultation 20/80 · Autre prestation 40/60 (configurable)", "icon": "clipboard-plus", "svg": pulse()},
        {"titre": "Médecine manuelle", "desc": "Répartition 20/80 et autres prestations configurables", "icon": "hand", "svg": pulse()},
        {"titre": "Soins à domicile", "desc": "Suivi des séances, répartition calculée sur le payé", "icon": "house-plus", "svg": house()},
        {"titre": "Rendez-vous", "desc": "Calendrier mois/semaine, rappels automatiques, alarmes", "icon": "calendar-days", "svg": calendar_svg()},
        {"titre": "Rapports", "desc": "Journalier / mensuel / annuel, par activité, par prescripteur — WhatsApp, PDF, Excel", "icon": "file-text", "svg": bars()},
        {"titre": "Détails du mois", "desc": "Chaque jour du mois détaillé, recherche instantanée avec surlignage", "icon": "calendar-search", "svg": calendar_svg()},
        {"titre": "Dettes", "desc": "Suivi des créances, paiement visible au rapport du jour J", "icon": "hand-coins", "svg": bars()},
        {"titre": "Entreprises", "desc": "Rapports privés par entreprise (LTJ, GGA…), export Excel", "icon": "building-2", "svg": users_svg()},
        {"titre": "Messagerie", "desc": "Privées, groupes, fichiers, vocaux, éphémère, recherche", "icon": "messages-square", "svg": chat()},
        {"titre": "Configuration", "desc": "8 onglets : taux, répartitions, examens, services, personnel", "icon": "settings", "svg": sliders()},
        {"titre": "Notifications", "desc": "Rappels de rendez-vous automatiques, cloche temps réel", "icon": "bell", "svg": calendar_svg()},
    ]
    return render(request, 'core/about.html', {
        'page_title': 'À propos',
        'features': features,
    })