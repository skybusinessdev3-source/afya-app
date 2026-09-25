import re
from datetime import date as date_cls

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.utils import log_event

from apps.settings_app.models import Company
from .services import (daily_report, whatsapp_daily, monthly_report, whatsapp_monthly,
                       annual_report, whatsapp_annual, company_report,
                       prescribers_summary, prescriber_report, activity_report, ACTIVITES,
                       month_days_report)
from .exports import (build_pdf, build_excel, build_company_excel,
                      build_prescriber_excel, build_prescriber_pdf,
                      build_activity_excel, build_activity_pdf)


def _get_report(request):
    """Retourne (vue, periode, report, text) selon les paramètres GET."""
    vue = request.GET.get('vue', 'jour')
    today = timezone.localdate()

    if vue == 'mois':
        try:
            year, month = map(int, request.GET.get('periode', f"{today.year}-{today.month}").split('-'))
        except ValueError:
            year, month = today.year, today.month
        report = monthly_report(year, month)
        return vue, f"{year}-{month:02d}", report, whatsapp_monthly(report)

    if vue == 'annee':
        try:
            year = int(request.GET.get('periode', today.year))
        except ValueError:
            year = today.year
        report = annual_report(year)
        return vue, str(year), report, whatsapp_annual(report)

    try:
        selected = date_cls.fromisoformat(request.GET.get('periode', str(today)))
    except ValueError:
        selected = today
    report = daily_report(selected)
    return 'jour', selected.isoformat(), report, whatsapp_daily(report)


@login_required
def report_page(request):
    vue, periode, report, text = _get_report(request)
    log_event(user=request.user, action=AuditLog.Actions.EXPORT,
              module='reports', obj=None, ip_address=request.META.get('REMOTE_ADDR'))
    return render(request, 'reports/index.html', {
        'page_title': 'Rapports',
        'vue': vue, 'periode': periode,
        'report': report, 'whatsapp_text': text,
    })


@login_required
def mois_details_page(request):
    """Toutes les activités du mois, jour par jour (même modèle que le
    rapport journalier), avec recherche par patient."""
    today = timezone.localdate()
    try:
        year, month = map(int, request.GET.get('periode', f"{today.year}-{today.month}").split('-'))
        date_cls(year, month, 1)  # valide
    except ValueError:
        year, month = today.year, today.month
    return render(request, 'reports/mois_details.html', {
        'page_title': 'Détails du mois',
        'periode': f"{year}-{month:02d}",
        'report': month_days_report(year, month),
    })


@login_required
def export_pdf(request):
    vue, periode, report, _ = _get_report(request)
    log_event(user=request.user, action=AuditLog.Actions.EXPORT,
              module='reports', obj=None, ip_address=request.META.get('REMOTE_ADDR'))
    data = build_pdf(vue, report)
    resp = HttpResponse(data, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="rapport_{vue}_{periode}.pdf"'
    return resp


@login_required
def export_excel(request):
    vue, periode, report, _ = _get_report(request)
    log_event(user=request.user, action=AuditLog.Actions.EXPORT,
              module='reports', obj=None, ip_address=request.META.get('REMOTE_ADDR'))
    data = build_excel(vue, report)
    resp = HttpResponse(data, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="rapport_{vue}_{periode}.xlsx"'
    return resp

def _company_period(request):
    """Entreprise choisie + période (mois) depuis GET."""
    today = timezone.localdate()
    company = Company.objects.filter(
        pk=request.GET.get('entreprise'), is_active=True).first()
    try:
        year, month = map(int, request.GET.get(
            'periode', f"{today.year}-{today.month:02d}").split('-'))
    except ValueError:
        year, month = today.year, today.month
    return company, year, month


@login_required
def entreprises_page(request):
    """Rapport mensuel d'une entreprise (créances — ex : LTJ)."""
    companies = Company.objects.filter(is_active=True)
    company, year, month = _company_period(request)
    report = company_report(company, year, month) if company else None
    return render(request, 'reports/entreprise.html', {
        'page_title': 'Rapports entreprises',
        'companies': companies,
        'company': company,
        'periode': f"{year}-{month:02d}",
        'report': report,
    })


@login_required
def entreprise_excel(request):
    company, year, month = _company_period(request)
    if company is None:
        return HttpResponse("Choisissez une entreprise.", status=400)
    report = company_report(company, year, month)
    log_event(user=request.user, action=AuditLog.Actions.EXPORT,
              module='reports', obj=None, ip_address=request.META.get('REMOTE_ADDR'))
    data = build_company_excel(report)
    resp = HttpResponse(data, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    nom = company.name.replace(' ', '_')
    resp['Content-Disposition'] = f'attachment; filename="ANNEXE_{nom}_{report["mois_nom"]}_{year}.xlsx"'
    return resp


# ================= PRESCRIPTEURS & ACTIVITÉS =================

def _periode(request):
    """Période GET d1/d2 (YYYY-MM-DD) ; défaut = 1er du mois → aujourd'hui."""
    today = timezone.localdate()
    debut_mois = today.replace(day=1)
    try:
        d1 = date_cls.fromisoformat(request.GET.get('d1', ''))
    except ValueError:
        d1 = debut_mois
    try:
        d2 = date_cls.fromisoformat(request.GET.get('d2', ''))
    except ValueError:
        d2 = today
    if d2 < d1:
        d1, d2 = d2, d1
    return d1, d2


def _log_export(request):
    log_event(user=request.user, action=AuditLog.Actions.EXPORT,
              module='reports', obj=None, ip_address=request.META.get('REMOTE_ADDR'))


def _nom_fichier(txt):
    """Nom de fichier sûr : lettres/chiffres/-/_ uniquement."""
    return re.sub(r'[^\w\-]+', '_', txt, flags=re.UNICODE).strip('_') or 'rapport'


def _excel_response(data, filename):
    resp = HttpResponse(data, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


def _pdf_response(data, filename):
    resp = HttpResponse(data, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@login_required
def prescripteurs_page(request):
    """Synthèse par prescripteur (labo + médecine) sur une période."""
    d1, d2 = _periode(request)
    prescripteurs = prescribers_summary(d1, d2)
    # Graphique : qui a le plus d'actes (labo + médecine + domicile) ?
    chart, top_key = None, None
    if prescripteurs:
        ordered = sorted(prescripteurs,
                         key=lambda e: e['labo_count'] + e['med_count'] + e['dom_count'],
                         reverse=True)
        top_key = ordered[0]['key']
        chart = {'titre': "Actes par prescripteur (labo + médecine + domicile)",
                 'unite': 'actes',
                 'labels': [e['name'] for e in ordered[:10]],
                 'values': [e['labo_count'] + e['med_count'] + e['dom_count']
                            for e in ordered[:10]]}
    return render(request, 'reports/prescripteurs.html', {
        'page_title': 'Rapport par prescripteur',
        'd1': d1.isoformat(), 'd2': d2.isoformat(),
        'prescripteurs': prescripteurs,
        'chart': chart, 'top_key': top_key,
    })


@login_required
def prescripteur_detail(request, key):
    """Rapport individuel d'un prescripteur."""
    d1, d2 = _periode(request)
    report = prescriber_report(key, d1, d2)
    return render(request, 'reports/prescripteur_detail.html', {
        'page_title': f"Prescripteur — {report['name']}",
        'key': key,
        'd1': d1.isoformat(), 'd2': d2.isoformat(),
        'report': report,
    })


@login_required
def prescripteur_excel(request, key):
    d1, d2 = _periode(request)
    report = prescriber_report(key, d1, d2)
    _log_export(request)
    data = build_prescriber_excel(report)
    nom = _nom_fichier(report['name'])
    return _excel_response(data, f"prescripteur_{nom}_{d1}_{d2}.xlsx")


@login_required
def prescripteur_pdf(request, key):
    d1, d2 = _periode(request)
    report = prescriber_report(key, d1, d2)
    _log_export(request)
    data = build_prescriber_pdf(report)
    nom = _nom_fichier(report['name'])
    return _pdf_response(data, f"prescripteur_{nom}_{d1}_{d2}.pdf")


@login_required
def activite_page(request, slug):
    """Rapport détaillé d'une activité sur une période."""
    d1, d2 = _periode(request)
    report = activity_report(slug, d1, d2)
    if report is None:
        return HttpResponse("Activité inconnue.", status=404)
    return render(request, 'reports/activite.html', {
        'page_title': 'Rapport par activité',
        'slug': slug,
        'activites': ACTIVITES,
        'd1': d1.isoformat(), 'd2': d2.isoformat(),
        'report': report,
    })


@login_required
def activite_excel(request, slug):
    d1, d2 = _periode(request)
    report = activity_report(slug, d1, d2)
    if report is None:
        return HttpResponse("Activité inconnue.", status=404)
    _log_export(request)
    data = build_activity_excel(report)
    return _excel_response(data, f"activite_{slug}_{d1}_{d2}.xlsx")


@login_required
def activite_pdf(request, slug):
    d1, d2 = _periode(request)
    report = activity_report(slug, d1, d2)
    if report is None:
        return HttpResponse("Activité inconnue.", status=404)
    _log_export(request)
    data = build_activity_pdf(report)
    return _pdf_response(data, f"activite_{slug}_{d1}_{d2}.pdf")
