import pytest
import os
from dotenv import load_dotenv
from django.test import Client

# Load environment variables
load_dotenv()


@pytest.fixture(autouse=True)
def _stub_verify_resume_links_delay(monkeypatch):
    """Avoid real Celery/network during ResumeService.apply_screening_result in tests."""
    from apps.core.tasks import verify_resume_links_task

    monkeypatch.setattr(verify_resume_links_task, 'delay', lambda *a, **kw: None)


@pytest.fixture
def client():
    """Django test client fixture."""
    return Client()


@pytest.fixture
def org(db):
    """Create the test organization matching FORCE_TENANT_SLUG='testorg'."""
    from apps.core.models import Organization
    return Organization.objects.create(
        name='Test Org',
        slug='testorg',
        is_active=True,
    )


@pytest.fixture
def authenticated_client(client, django_user_model, org):
    """Authenticated Django test client whose user is a member of the test org."""
    from apps.core.models import OrganizationMember
    user = django_user_model.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
    OrganizationMember.objects.create(organization=org, user=user, role='admin')
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def sample_job(db, org):
    """Create a sample job for testing (scoped to test org)."""
    from apps.core.models import Job
    return Job.objects.create(
        title='Senior Python Developer',
        description='Looking for experienced Python developer',
        status='active',
        organization=org,
    )


@pytest.fixture
def sample_resume(db, sample_job, org):
    """Create a sample resume for testing (scoped to test org)."""
    from apps.core.models import Resume
    return Resume.objects.create(
        job=sample_job,
        organization=org,
        candidate_name='John Doe',
        experience_score=85,
        education_score=75,
        skills_score=90,
        final_score=85
    )
