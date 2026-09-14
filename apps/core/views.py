import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone

from apps.centre.models import Session
from apps.finance.models import Expense, Payment


# ============================================================
# PAGE D'ACCUEIL
# ============================================================

def landing(request):
    """
    Page d'accueil publique.
    Si l'utilisateur est déjà connecté, il est redirigé
    vers le tableau de bord.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(
        request,
        "core/landing.html",
        {
            "logo_url": static("img/logo.png"),
        },
    )


# ============================================================
# TABLEAU DE BORD
# ============================================================

@login_required
def dashboard(request):
    today = timezone.localdate()

    # --------------------------------------------------------
    # SÉANCES / PATIENTS DU JOUR
    # --------------------------------------------------------

    sessions_today = Session.objects.filter(date=today)

    patients_today = (
        sessions_today
        .values("patient")
        .distinct()
        .count()
    )

    sessions_today_count = sessions_today.count()

    # --------------------------------------------------------
    # RECETTES DU JOUR
    #
    # IMPORTANT :
    # USD et FC restent toujours séparés.
    # On ne les additionne jamais directement.
    # --------------------------------------------------------

    payments_today = Payment.objects.filter(
        date=today,
        status=Payment.Status.VALID,
    )

    revenues = payments_today.aggregate(
        usd=Sum(
            "amount_original",
            filter=Q(currency_original="USD"),
        ),
        fc=Sum(
            "amount_original",
            filter=Q(currency_original="FC"),
        ),
    )

    rev_usd = revenues["usd"] or 0
    rev_fc = revenues["fc"] or 0

    # --------------------------------------------------------
    # DÉPENSES DU JOUR
    # --------------------------------------------------------

    expenses_today = Expense.objects.filter(date=today)

    expenses = expenses_today.aggregate(
        usd=Sum(
            "amount_original",
            filter=Q(currency_original="USD"),
        ),
        fc=Sum(
            "amount_original",
            filter=Q(currency_original="FC"),
        ),
    )

    exp_usd = expenses["usd"] or 0
    exp_fc = expenses["fc"] or 0

    # --------------------------------------------------------
    # NET DU JOUR
    # --------------------------------------------------------

    net_usd = rev_usd - exp_usd
    net_fc = rev_fc - exp_fc

    # --------------------------------------------------------
    # GRAPHIQUE DES 7 DERNIERS JOURS
    # --------------------------------------------------------

    days = [
        today - timedelta(days=i)
        for i in range(6, -1, -1)
    ]

    chart_labels = []
    chart_usd = []
    chart_fc = []
    chart_exp_usd = []
    chart_exp_fc = []

    for day in days:

        chart_labels.append(day.strftime("%d/%m"))

        # Recettes
        payment_data = Payment.objects.filter(
            date=day,
            status=Payment.Status.VALID,
        ).aggregate(
            usd=Sum(
                "amount_original",
                filter=Q(currency_original="USD"),
            ),
            fc=Sum(
                "amount_original",
                filter=Q(currency_original="FC"),
            ),
        )

        # Dépenses
        expense_data = Expense.objects.filter(
            date=day,
        ).aggregate(
            usd=Sum(
                "amount_original",
                filter=Q(currency_original="USD"),
            ),
            fc=Sum(
                "amount_original",
                filter=Q(currency_original="FC"),
            ),
        )

        chart_usd.append(float(payment_data["usd"] or 0))
        chart_fc.append(float(payment_data["fc"] or 0))

        chart_exp_usd.append(float(expense_data["usd"] or 0))
        chart_exp_fc.append(float(expense_data["fc"] or 0))

    # --------------------------------------------------------
    # CONTEXTE
    # --------------------------------------------------------

    context = {
        "page_title": "Tableau de bord",

        # Date
        "today": today,

        # Activité
        "patients_today": patients_today,
        "sessions_today_count": sessions_today_count,

        # Finance
        "rev_usd": rev_usd,
        "rev_fc": rev_fc,
        "exp_usd": exp_usd,
        "exp_fc": exp_fc,

        "net_usd": net_usd,
        "net_fc": net_fc,

        # Graphique
        "chart_labels": json.dumps(chart_labels),
        "chart_usd": json.dumps(chart_usd),
        "chart_fc": json.dumps(chart_fc),
        "chart_exp_usd": json.dumps(chart_exp_usd),
        "chart_exp_fc": json.dumps(chart_exp_fc),
    }

    return render(
        request,
        "core/dashboard.html",
        context,
    )


# ============================================================
# PAGE "À PROPOS"
# ============================================================

@login_required
def about_page(request):
    """
    Présentation des fonctionnalités disponibles
    dans AFYA APP.
    """

    features = [
        {
            "titre": "Tableau de bord",
            "desc": (
                "Recettes, dépenses et graphiques sur 7 jours, "
                "avec séparation des devises"
            ),
            "icon": "layout-dashboard",
        },
        {
            "titre": "Centre (jour)",
            "desc": (
                "Séances, paiements multi-devises, dépenses "
                "et gestion des patients"
            ),
            "icon": "stethoscope",
        },
        {
            "titre": "Patients",
            "desc": (
                "Liste, recherche et fiche complète avec historique"
            ),
            "icon": "users",
        },
        {
            "titre": "Pharmacie",
            "desc": (
                "Ventes, panier, stock, mouvements "
                "et réapprovisionnement"
            ),
            "icon": "pill",
        },
        {
            "titre": "Laboratoire",
            "desc": (
                "Gestion des examens et répartition des revenus"
            ),
            "icon": "flask-conical",
        },
        {
            "titre": "Médecine générale",
            "desc": (
                "Consultations et autres prestations "
                "avec répartitions configurables"
            ),
            "icon": "clipboard-plus",
        },
        {
            "titre": "Médecine manuelle",
            "desc": (
                "Gestion des prestations et répartitions configurables"
            ),
            "icon": "hand",
        },
        {
            "titre": "Soins à domicile",
            "desc": (
                "Suivi des séances, paiements "
                "et répartitions calculées"
            ),
            "icon": "house-plus",
        },
        {
            "titre": "Rendez-vous",
            "desc": (
                "Calendrier, rappels automatiques "
                "et alarmes"
            ),
            "icon": "calendar-days",
        },
        {
            "titre": "Rapports",
            "desc": (
                "Rapports journaliers, mensuels et annuels "
                "avec exports"
            ),
            "icon": "file-text",
        },
        {
            "titre": "Messagerie",
            "desc": (
                "Conversations privées et groupes, "
                "fichiers, vocaux et recherche"
            ),
            "icon": "messages-square",
        },
        {
            "titre": "Configuration",
            "desc": (
                "Taux de change, répartitions, examens, "
                "services et personnel"
            ),
            "icon": "settings",
        },
        {
            "titre": "Notifications",
            "desc": (
                "Rappels de rendez-vous et notifications "
                "en temps réel"
            ),
            "icon": "bell",
        },
    ]

    return render(
        request,
        "core/about.html",
        {
            "page_title": "À propos",
            "features": features,
        },
    )