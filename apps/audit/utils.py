from .models import AuditLog


def log_event(*, user, action, module, obj=None, old_value=None, new_value=None,
              ip_address=None, result=AuditLog.Results.SUCCESS):
    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        module=module,
        object_id=str(obj.pk) if obj is not None else '',
        object_repr=str(obj)[:255] if obj is not None else '',
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        result=result,
    )