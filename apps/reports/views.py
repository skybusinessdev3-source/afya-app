from datetime import date as date_cls

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.utils import log_event

from .services import (daily_report, whatsapp_daily, monthly_report, whatsapp_monthly,
                       annual_report, whatsapp_annual)
from .exports import build_pdf, build_excel


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