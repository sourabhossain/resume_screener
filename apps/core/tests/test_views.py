"""
Unit tests for views.
"""
import pytest
from django.urls import reverse
from apps.core.models import Job, Resume


@pytest.mark.django_db
class TestDashboardView:
    """Tests for dashboard view."""
    
    def test_dashboard_requires_login(self, client):
        """Test dashboard redirects unauthenticated users."""
        response = client.get(reverse('core:dashboard'))
        assert response.status_code == 302
        assert 'login' in response.url
    
    def test_dashboard_authenticated(self, authenticated_client):
        """Test dashboard accessible when authenticated."""
        response = authenticated_client.get(reverse('core:dashboard'))
        assert response.status_code == 200
    
    def test_dashboard_context(self, authenticated_client, sample_job):
        """Test dashboard contains expected context."""
        response = authenticated_client.get(reverse('core:dashboard'))
        assert 'total_jobs' in response.context
        assert 'active_jobs' in response.context
        assert 'total_resumes' in response.context


@pytest.mark.django_db
class TestJobViews:
    """Tests for job CRUD views."""
    
    def test_job_list_requires_login(self, client):
        """Test job list redirects unauthenticated users."""
        response = client.get(reverse('core:job_list'))
        assert response.status_code == 302
    
    def test_job_list_authenticated(self, authenticated_client):
        """Test job list accessible when authenticated."""
        response = authenticated_client.get(reverse('core:job_list'))
        assert response.status_code == 200
    
    def test_job_list_search(self, authenticated_client, sample_job):
        """Test job list search functionality."""
        response = authenticated_client.get(
            reverse('core:job_list'), 
            {'q': 'Python'}
        )
        assert response.status_code == 200
        assert sample_job in response.context['jobs']
    
    def test_job_list_filter_status(self, authenticated_client, sample_job):
        """Test job list status filter."""
        response = authenticated_client.get(
            reverse('core:job_list'), 
            {'status': 'active'}
        )
        assert response.status_code == 200
        assert sample_job in response.context['jobs']
    
    def test_job_create_get(self, authenticated_client):
        """Test job create form displays."""
        response = authenticated_client.get(reverse('core:job_create'))
        assert response.status_code == 200
        assert 'form' in response.context
    
    def test_job_create_post(self, authenticated_client):
        """Test creating a new job."""
        data = {
            'title': 'New Job',
            'description': 'Job description',
            'status': 'draft'
        }
        response = authenticated_client.post(reverse('core:job_create'), data)
        assert response.status_code == 302  # Redirect after success
        assert Job.objects.filter(title='New Job').exists()
    
    def test_job_detail(self, authenticated_client, sample_job):
        """Test job detail view."""
        response = authenticated_client.get(
            reverse('core:job_detail', kwargs={'pk': sample_job.pk})
        )
        assert response.status_code == 200
        assert response.context['job'] == sample_job
    
    def test_job_edit(self, authenticated_client, sample_job):
        """Test editing a job."""
        data = {
            'title': 'Updated Title',
            'description': sample_job.description,
            'status': sample_job.status
        }
        response = authenticated_client.post(
            reverse('core:job_edit', kwargs={'pk': sample_job.pk}),
            data
        )
        sample_job.refresh_from_db()
        assert sample_job.title == 'Updated Title'
    
    def test_job_delete(self, authenticated_client, sample_job):
        """Test soft deleting a job."""
        response = authenticated_client.post(
            reverse('core:job_delete', kwargs={'pk': sample_job.pk})
        )
        assert response.status_code == 302
        assert Job.objects.filter(pk=sample_job.pk).count() == 0


@pytest.mark.django_db
class TestResumeViews:
    """Tests for resume CRUD views."""
    
    def test_resume_create_requires_active_job(self, authenticated_client, sample_job):
        """Test resume creation requires active job."""
        sample_job.status = 'draft'
        sample_job.save()
        
        response = authenticated_client.get(
            reverse('core:resume_create', kwargs={'job_pk': sample_job.pk})
        )
        # Should redirect with error message
        assert response.status_code == 302
    
    def test_resume_detail(self, authenticated_client, sample_resume):
        """Test resume detail view."""
        response = authenticated_client.get(
            reverse('core:resume_detail', kwargs={'pk': sample_resume.pk})
        )
        assert response.status_code == 200
        assert response.context['resume'] == sample_resume
    
    def test_resume_delete(self, authenticated_client, sample_resume):
        """Test soft deleting a resume."""
        response = authenticated_client.post(
            reverse('core:resume_delete', kwargs={'pk': sample_resume.pk})
        )
        assert response.status_code == 302
        assert Resume.objects.filter(pk=sample_resume.pk).count() == 0
