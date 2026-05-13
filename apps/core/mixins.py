from django.contrib import messages
from django.shortcuts import redirect


class TenantMixin:
    """
    Mixin for all tenant-scoped views.
    Ensures request.organization is set and user belongs to it.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.organization:
            messages.error(request, "Organization not found.")
            return redirect('core:landing')
        if not self._user_in_org(request):
            messages.error(request, "You don't have access to this organization.")
            return redirect('core:landing')
        return super().dispatch(request, *args, **kwargs)

    def _user_in_org(self, request):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        from apps.core.models import OrganizationMember
        return OrganizationMember.objects.filter(
            organization=request.organization,
            user=request.user
        ).exists()

    def get_org_queryset(self, model):
        return model.objects.filter(organization=self.request.organization)


class AdminRequiredMixin(TenantMixin):
    """Only org admins can access this view."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(response, 'status_code') and response.status_code != 200:
            return response
        if not self._user_is_admin(request):
            messages.error(request, "Admin access required.")
            return redirect('core:dashboard')
        return response

    def _user_is_admin(self, request):
        if request.user.is_superuser:
            return True
        from apps.core.models import OrganizationMember
        return OrganizationMember.objects.filter(
            organization=request.organization,
            user=request.user,
            role='admin'
        ).exists()
