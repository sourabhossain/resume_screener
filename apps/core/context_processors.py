from .models import OrganizationMember


def tenant_context(request):
    """Inject current org role into every template."""
    org = getattr(request, 'organization', None)
    role = None

    if org and hasattr(request, 'user') and request.user.is_authenticated:
        if request.user.is_superuser:
            role = 'admin'
        else:
            membership = OrganizationMember.objects.filter(
                organization=org, user=request.user
            ).values_list('role', flat=True).first()
            role = membership

    return {'current_org_role': role}
