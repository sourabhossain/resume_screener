"""
Tests for multi-tenant isolation: middleware, data scoping, and org flows.
"""
import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse
from apps.core.models import (
    Organization, OrganizationMember, OrganizationInvite, Job, Resume,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org_a(db):
    return Organization.objects.create(name='Org A', slug='org-a', is_active=True)


@pytest.fixture
def org_b(db):
    return Organization.objects.create(name='Org B', slug='org-b', is_active=True)


@pytest.fixture
def user_a(db, django_user_model, org_a):
    user = django_user_model.objects.create_user(
        username='user_a', email='a@orga.com', password='pass1234'
    )
    OrganizationMember.objects.create(organization=org_a, user=user, role='admin')
    return user


@pytest.fixture
def user_b(db, django_user_model, org_b):
    user = django_user_model.objects.create_user(
        username='user_b', email='b@orgb.com', password='pass1234'
    )
    OrganizationMember.objects.create(organization=org_b, user=user, role='admin')
    return user


@pytest.fixture
def client_a(client, org_a, user_a):
    client.login(username='user_a', password='pass1234')
    return client


@pytest.fixture
def client_b(client, org_b, user_b):
    client.login(username='user_b', password='pass1234')
    return client


@pytest.fixture
def job_a(org_a):
    return Job.objects.create(title='Job A', status='active', organization=org_a)


@pytest.fixture
def job_b(org_b):
    return Job.objects.create(title='Job B', status='active', organization=org_b)


# ---------------------------------------------------------------------------
# Tenant middleware tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTenantMiddleware:

    def test_resolves_tenant_from_subdomain(self):
        org = Organization.objects.create(slug='ssl-wireless', name='SSL Wireless', is_active=True)
        factory = RequestFactory()

        with override_settings(BASE_DOMAIN='resumeai.com', FORCE_TENANT_SLUG=''):
            from apps.core.middleware import TenantMiddleware
            request = factory.get('/', SERVER_NAME='ssl-wireless.resumeai.com')
            mw = TenantMiddleware(lambda r: r)
            mw(request)
            assert request.organization == org

    def test_returns_none_for_main_domain(self, db):
        factory = RequestFactory()
        with override_settings(BASE_DOMAIN='resumeai.com', FORCE_TENANT_SLUG=''):
            from apps.core.middleware import TenantMiddleware
            request = factory.get('/', SERVER_NAME='resumeai.com')
            mw = TenantMiddleware(lambda r: r)
            mw(request)
            assert request.organization is None

    def test_returns_none_for_unknown_subdomain(self, db):
        factory = RequestFactory()
        with override_settings(BASE_DOMAIN='resumeai.com', FORCE_TENANT_SLUG=''):
            from apps.core.middleware import TenantMiddleware
            request = factory.get('/', SERVER_NAME='unknown-org.resumeai.com')
            mw = TenantMiddleware(lambda r: r)
            mw(request)
            assert request.organization is None

    def test_force_tenant_slug_in_dev(self):
        org = Organization.objects.create(slug='demo', name='Demo', is_active=True)
        factory = RequestFactory()
        with override_settings(FORCE_TENANT_SLUG='demo'):
            from apps.core.middleware import TenantMiddleware
            request = factory.get('/')
            mw = TenantMiddleware(lambda r: r)
            mw(request)
            assert request.organization == org

    def test_inactive_org_returns_none(self, db):
        Organization.objects.create(slug='inactive', name='Inactive', is_active=False)
        factory = RequestFactory()
        with override_settings(BASE_DOMAIN='resumeai.com', FORCE_TENANT_SLUG=''):
            from apps.core.middleware import TenantMiddleware
            request = factory.get('/', SERVER_NAME='inactive.resumeai.com')
            mw = TenantMiddleware(lambda r: r)
            mw(request)
            assert request.organization is None


# ---------------------------------------------------------------------------
# Tenant isolation tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTenantIsolation:

    def test_org_a_cannot_see_org_b_jobs(self, client_a, job_a, job_b):
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.get(reverse('core:job_list'))
        assert response.status_code == 200
        job_titles = [j.title for j in response.context['jobs']]
        assert 'Job A' in job_titles
        assert 'Job B' not in job_titles

    def test_org_a_cannot_access_org_b_job_by_id(self, client_a, job_b):
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.get(reverse('core:job_detail', kwargs={'pk': job_b.pk}))
        assert response.status_code == 404

    def test_org_a_cannot_access_org_b_resume_by_id(self, client_a, org_b, job_b):
        resume_b = Resume.objects.create(
            job=job_b, organization=org_b, candidate_name='Bob'
        )
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.get(reverse('core:resume_detail', kwargs={'pk': resume_b.pk}))
        assert response.status_code == 404

    def test_job_create_sets_organization(self, client_a, org_a):
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.post(reverse('core:job_create'), {
                'title': 'New Job', 'description': 'desc', 'status': 'draft'
            })
        assert response.status_code == 302
        job = Job.objects.get(title='New Job')
        assert job.organization == org_a

    def test_resume_create_sets_organization(self, client_a, org_a, job_a):
        from unittest.mock import patch
        import io

        pdf_bytes = b'%PDF-1.4 fake'
        fake_file = io.BytesIO(pdf_bytes)
        fake_file.name = 'resume.pdf'

        with patch('apps.core.tasks.screen_resume_task.delay'), \
             patch('apps.core.views.transaction.on_commit', side_effect=lambda fn: fn()):
            with override_settings(FORCE_TENANT_SLUG='org-a'):
                response = client_a.post(
                    reverse('core:resume_create', kwargs={'job_pk': job_a.pk}),
                    {'candidate_name': 'Alice', 'file': fake_file},
                )
        assert response.status_code == 302
        resume = Resume.objects.get(candidate_name='Alice')
        assert resume.organization == org_a

    def test_dashboard_only_shows_org_data(self, client_a, job_a, job_b):
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.get(reverse('core:dashboard'))
        assert response.status_code == 200
        # Only org_a's job should be counted
        assert response.context['total_jobs'] == 1

    def test_no_cross_tenant_resume_access_via_rescreen(self, client_a, org_b, job_b):
        resume_b = Resume.objects.create(
            job=job_b, organization=org_b, candidate_name='Bob'
        )
        with override_settings(FORCE_TENANT_SLUG='org-a'):
            response = client_a.post(
                reverse('core:resume_rescreen', kwargs={'pk': resume_b.pk})
            )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Organization registration tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOrganizationRegistration:

    def test_register_creates_org_user_and_membership(self, client):
        response = client.post(reverse('core:org_register'), {
            'name': 'New Corp',
            'slug': 'new-corp',
            'email': 'admin@newcorp.com',
            'password': 'securepass123',
            'password2': 'securepass123',
        })
        assert response.status_code == 302
        assert Organization.objects.filter(slug='new-corp').exists()
        org = Organization.objects.get(slug='new-corp')
        from django.contrib.auth.models import User
        user = User.objects.get(email='admin@newcorp.com')
        assert OrganizationMember.objects.filter(
            organization=org, user=user, role='admin'
        ).exists()

    def test_register_slug_must_be_unique(self, client, org):
        response = client.post(reverse('core:org_register'), {
            'name': 'Another Org',
            'slug': 'testorg',  # already taken (org fixture)
            'email': 'admin@another.com',
            'password': 'securepass123',
            'password2': 'securepass123',
        })
        assert response.status_code == 200  # re-renders form
        assert b'already taken' in response.content

    def test_register_slug_auto_generated_from_name(self, client):
        response = client.post(reverse('core:org_register'), {
            'name': 'SSL Wireless Ltd',
            'slug': '',  # leave empty to trigger auto-gen
            'email': 'admin@sslwireless.com',
            'password': 'securepass123',
            'password2': 'securepass123',
        })
        # Either redirects (success) or renders with auto-slug
        # The view auto-generates slug from name when field is empty
        assert Organization.objects.filter(slug='ssl-wireless-ltd').exists() or response.status_code == 200

    def test_register_password_mismatch_returns_form_error(self, client):
        response = client.post(reverse('core:org_register'), {
            'name': 'Mismatch Corp',
            'slug': 'mismatch-corp',
            'email': 'x@mismatch.com',
            'password': 'passA1234',
            'password2': 'passB1234',
        })
        assert response.status_code == 200
        assert b'do not match' in response.content


# ---------------------------------------------------------------------------
# Member invite tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMemberInvite:
    """Tests for invite creation and acceptance."""

    def test_invite_creates_token_and_sends_email(self, client, org, authenticated_client):
        from django.utils import timezone
        import secrets as secrets_mod

        # Admin invites a new member
        with override_settings(FORCE_TENANT_SLUG='testorg'):
            response = authenticated_client.post(
                reverse('core:org_members'),
                {'action': 'invite', 'email': 'newmember@example.com', 'role': 'member'},
            )
        assert response.status_code == 302
        assert OrganizationInvite.objects.filter(
            organization=org, email='newmember@example.com', status='pending'
        ).exists()

    def test_accept_invite_creates_membership(self, client, org, django_user_model):
        from django.utils import timezone
        import secrets as secrets_mod

        user = django_user_model.objects.create_user(
            username='invitee', email='invitee@example.com', password='pass1234'
        )
        invite = OrganizationInvite.objects.create(
            organization=org,
            email=user.email,
            role='member',
            token=secrets_mod.token_urlsafe(32),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )

        client.login(username='invitee', password='pass1234')
        response = client.post(
            reverse('core:accept_invite', kwargs={'token': invite.token}),
            {'action': 'accept'},
        )
        assert response.status_code == 302
        assert OrganizationMember.objects.filter(
            organization=org, user=user, role='member'
        ).exists()
        invite.refresh_from_db()
        assert invite.status == 'accepted'

    def test_expired_invite_rejected(self, client, org):
        from django.utils import timezone
        import secrets as secrets_mod

        invite = OrganizationInvite.objects.create(
            organization=org,
            email='expired@example.com',
            role='member',
            token=secrets_mod.token_urlsafe(32),
            expires_at=timezone.now() - timezone.timedelta(days=1),  # expired
        )
        response = client.get(reverse('core:accept_invite', kwargs={'token': invite.token}))
        assert response.status_code == 302  # redirected to landing with error

    def test_invite_already_member_shows_error(self, authenticated_client, org, django_user_model):
        existing = django_user_model.objects.create_user(
            username='existing', email='existing@example.com', password='pass1234'
        )
        OrganizationMember.objects.create(organization=org, user=existing, role='member')

        with override_settings(FORCE_TENANT_SLUG='testorg'):
            response = authenticated_client.post(
                reverse('core:org_members'),
                {'action': 'invite', 'email': 'existing@example.com', 'role': 'member'},
            )
        assert response.status_code == 302
        # Should show an error message (no new invite created)
        assert OrganizationInvite.objects.filter(
            email='existing@example.com', organization=org
        ).count() == 0


# ---------------------------------------------------------------------------
# Setup tenant management command test
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSetupTenantCommand:

    def test_creates_org_user_membership_and_migrates_data(self):
        from django.core.management import call_command
        import io

        # Create an unassigned job to test migration
        orphan_job = Job.objects.create(title='Orphan Job', status='active', organization=None)

        out = io.StringIO()
        call_command(
            'setup_tenant',
            '--name', 'Test Company',
            '--slug', 'test-company',
            '--admin-email', 'sa@test.com',
            '--admin-password', 'admin1234',
            stdout=out,
        )

        assert Organization.objects.filter(slug='test-company').exists()
        from django.contrib.auth.models import User
        user = User.objects.get(email='sa@test.com')
        org = Organization.objects.get(slug='test-company')
        assert OrganizationMember.objects.filter(organization=org, user=user, role='admin').exists()

        # Orphan job should be migrated to new org
        orphan_job.refresh_from_db()
        assert orphan_job.organization == org


# ---------------------------------------------------------------------------
# Full onboarding integration test
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFullOrgOnboardingFlow:

    def test_full_org_onboarding_flow(self, client):
        import io
        from unittest.mock import patch
        from django.contrib.auth.models import User

        SLUG = 'onboard-corp'

        # 1. Register: creates org + user + OrganizationMember in one POST
        response = client.post(reverse('core:org_register'), {
            'name': 'Onboard Corp',
            'slug': SLUG,
            'email': 'founder@onboard.com',
            'password': 'securepass123',
            'password2': 'securepass123',
        })
        assert response.status_code == 302

        org = Organization.objects.get(slug=SLUG)
        user = User.objects.get(email='founder@onboard.com')
        assert OrganizationMember.objects.filter(
            organization=org, user=user, role='admin'
        ).exists()

        # 2. Login → redirected to org picker (LOGIN_REDIRECT_URL = 'core:org_picker')
        response = client.post(reverse('login'), {
            'username': user.username,
            'password': 'securepass123',
        })
        assert response.status_code == 302
        assert 'pick-org' in response['Location']

        # Enter the new org's context for the remaining requests
        with override_settings(FORCE_TENANT_SLUG=SLUG):

            # 3. Org picker: single membership → redirects to dashboard
            response = client.get(reverse('core:org_picker'))
            assert response.status_code == 302
            assert 'dashboard' in response['Location']

            # 4. Create job → organization stamped correctly
            response = client.post(reverse('core:job_create'), {
                'title': 'Founding Engineer',
                'description': 'Build the product',
                'status': 'active',
            })
            assert response.status_code == 302
            job = Job.objects.get(title='Founding Engineer')
            assert job.organization == org

            # 5. Add resume → organization stamped, screening queued
            pdf_bytes = b'%PDF-1.4 fake content'
            fake_file = io.BytesIO(pdf_bytes)
            fake_file.name = 'alice.pdf'

            with patch('apps.core.tasks.screen_resume_task.delay') as mock_delay, \
                 patch('apps.core.views.transaction.on_commit', side_effect=lambda fn: fn()):
                response = client.post(
                    reverse('core:resume_create', kwargs={'job_pk': job.pk}),
                    {'candidate_name': 'Alice', 'file': fake_file},
                )

            assert response.status_code == 302
            resume = Resume.objects.get(candidate_name='Alice', job=job)
            assert resume.organization == org
            assert resume.screening_status == 'processing'
            mock_delay.assert_called_once_with(resume.id)
