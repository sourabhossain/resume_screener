"""
Management command for local multi-tenant development setup.

Usage:
    python manage.py tenant_dev_setup
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print /etc/hosts entries and nginx config needed for local subdomain routing."

    def handle(self, *args, **options):
        from apps.core.models import Organization

        orgs = list(Organization.objects.filter(is_active=True).order_by('slug'))

        self.stdout.write("")
        self.stdout.write("=" * 48)
        self.stdout.write("ResumeAI — Local Development Setup")
        self.stdout.write("=" * 48)
        self.stdout.write("")
        self.stdout.write("Add these lines to /etc/hosts:")
        self.stdout.write("  Mac/Linux : sudo nano /etc/hosts")
        self.stdout.write("  Windows   : C:\\Windows\\System32\\drivers\\etc\\hosts")
        self.stdout.write("")
        self.stdout.write("127.0.0.1  localhost")
        for org in orgs:
            self.stdout.write(f"127.0.0.1  {org.slug}.localhost")
        self.stdout.write("")
        self.stdout.write("After editing /etc/hosts, visit:")
        for org in orgs:
            self.stdout.write(f"  http://{org.slug}.localhost/  →  {org.name} dashboard")
        self.stdout.write("  http://localhost/               →  Landing page")
        self.stdout.write("")

        self.stdout.write("-" * 48)
        self.stdout.write("Nginx — wildcard subdomain config (nginx.conf)")
        self.stdout.write("-" * 48)
        self.stdout.write("")
        self.stdout.write("Update your server block's server_name to:")
        self.stdout.write("")
        self.stdout.write("  server_name localhost *.localhost;")
        self.stdout.write("")
        self.stdout.write("Or with named-capture regex (more explicit):")
        self.stdout.write("")
        self.stdout.write("  server_name ~^(?<subdomain>.+)\\.localhost$ localhost;")
        self.stdout.write("")
        self.stdout.write("Then restart nginx:  docker-compose restart nginx")
        self.stdout.write("")

        self.stdout.write("-" * 48)
        self.stdout.write("Current organizations")
        self.stdout.write("-" * 48)
        self.stdout.write("")
        if orgs:
            for org in orgs:
                self.stdout.write(f"  {org.slug:<20}  {org.name}")
        else:
            self.stdout.write("  (no organizations — run: python manage.py setup_tenant)")
        self.stdout.write("")
        self.stdout.write("=" * 48)
        self.stdout.write("")
