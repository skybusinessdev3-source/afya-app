from .models import CenterConfig


def center_config(request):
    """Rend le logo/config du centre disponible dans tous les templates."""
    return {'center_config': CenterConfig.objects.first()}