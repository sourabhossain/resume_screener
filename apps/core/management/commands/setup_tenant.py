"""
Management command to bootstrap a tenant organization with an admin user.

Usage:
    python manage.py setup_tenant \\
        --name "Demo Company" \\
        --slug "demo" \\
        --admin-email "admin@demo.com" \\
        --admin-password "admin123"
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Create an Organization with an admin user and migrate existing data."

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Organization display name')
        parser.add_argument('--slug', required=True, help='Subdomain slug (e.g. demo)')
        parser.add_argument('--admin-email', required=True, dest='admin_email', help='Admin user email')
        parser.add_argument('--admin-password', required=True, dest='admin_password', help='Admin user password')

    def handle(self, *args, **options):
        from apps.core.models import Organization, OrganizationMember, Job, Resume

        slug = options['slug']
        name = options['name']
        email = options['admin_email']
        password = options['admin_password']

        # Create or update org
        org, org_created = Organization.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'is_active': True},
        )
        if org_created:
            self.stdout.write(self.style.SUCCESS(f"Created organization: {org.name} ({slug})"))
        else:
            self.stdout.write(f"Organization already exists: {org.name} ({slug})")

        # Create or get admin user
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exclude(email=email).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user, user_created = User.objects.get_or_create(
            email=email,
            defaults={'username': username},
        )
        if user_created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created admin user: {email}"))
        else:
            self.stdout.write(f"User already exists: {email}")

        # Create membership
        membership, mem_created = OrganizationMember.objects.get_or_create(
            organization=org,
            user=user,
            defaults={'role': 'admin'},
        )
        if mem_created:
            self.stdout.write(self.style.SUCCESS(f"Created admin membership for {email}"))
        else:
            if membership.role != 'admin':
                membership.role = 'admin'
                membership.save()
                self.stdout.write(f"Updated {email} to admin role")

        # Migrate existing Jobs and Resumes that have no org
        jobs_updated = Job.all_objects.filter(organization__isnull=True).update(organization=org)
        resumes_updated = Resume.all_objects.filter(organization__isnull=True).update(organization=org)

        if jobs_updated:
            self.stdout.write(self.style.SUCCESS(f"Assigned {jobs_updated} existing job(s) to {org.name}"))
        if resumes_updated:
            self.stdout.write(self.style.SUCCESS(f"Assigned {resumes_updated} existing resume(s) to {org.name}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nTenant setup complete!\n"
            f"  Org:      {org.name} ({slug})\n"
            f"  Admin:    {email}\n"
            f"  URL:      {org.subdomain_url}\n"
        ))
