import logging

from django.conf import settings

from .models import Organization

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Reads subdomain from request host and sets request.organization.

    Example: ssl-wireless.resumeai.com → slug='ssl-wireless'

    For local development:
      - HOST header: ssl-wireless.localhost:8000
      - Or use FORCE_TENANT_SLUG setting to bypass subdomain detection
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = self._resolve_tenant(request)
        return self.get_response(request)

    def _resolve_tenant(self, request):
        host = request.get_host().split(":")[0]
        base_domain = getattr(settings, "BASE_DOMAIN", "resumeai.com")

        # Support both the configured BASE_DOMAIN and bare 'localhost' for dev.
        candidate_bases = [base_domain]
        if base_domain != "localhost":
            candidate_bases.append("localhost")

        # Subdomain detection takes priority over FORCE_TENANT_SLUG.
        for base in candidate_bases:
            if host.endswith(f".{base}"):
                subdomain = host[: -(len(base) + 1)]
                if not subdomain or subdomain == "www":
                    break  # bare domain — fall through to forced slug
                try:
                    return Organization.objects.get(slug=subdomain, is_active=True)
                except Organization.DoesNotExist:
                    logger.warning(f"Unknown tenant subdomain: {subdomain}")
                    return None

        # No subdomain found — use FORCE_TENANT_SLUG if configured (dev only).
        forced_slug = getattr(settings, "FORCE_TENANT_SLUG", None)
        if forced_slug:
            try:
                return Organization.objects.get(slug=forced_slug, is_active=True)
            except Organization.DoesNotExist:
                return None

        return None
