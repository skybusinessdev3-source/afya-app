import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from apps.centre.models import Session
from apps.finance.models import Expense, Payment


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

    context = {
        'page_title': 'Tableau de bord',
        'today': today,
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

from django.shortcuts import redirect


def landing(request):
    """Page d'accueil animée (non connectés). Les connectés vont au dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html')

from django.conf import settings
from django.templatetags.static import static as static_url


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html', {'logo_url': static_url('img/logo.png')})