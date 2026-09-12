from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    context = {
        'page_title': 'Tableau de bord',
    }
    return render(request, 'core/dashboard.html', context)