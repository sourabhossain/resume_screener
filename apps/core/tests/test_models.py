"""
Unit tests for Job and Resume models.
"""
import pytest
from django.utils import timezone
from apps.core.models import Job, Resume


@pytest.mark.django_db
class TestJobModel:
    """Tests for Job model."""
    
    def test_job_creation(self):
        """Test creating a job with basic fields."""
        job = Job.objects.create(
            title='Software Engineer',
            description='Full stack developer position',
            status='active'
        )
        assert job.pk is not None
        assert job.title == 'Software Engineer'
        assert job.status == 'active'
        assert job.is_deleted is False
    
    def test_job_str_method(self):
        """Test the __str__ method returns title."""
        job = Job.objects.create(title='Data Scientist')
        assert str(job) == 'Data Scientist'
    
    def test_job_soft_delete(self):
        """Test soft delete functionality."""
        job = Job.objects.create(title='Test Job')
        job.soft_delete()
        
        # Should not appear in normal queries
        assert Job.objects.filter(pk=job.pk).count() == 0
        # Should appear in all_with_deleted
        assert Job.objects.all_with_deleted().filter(pk=job.pk).count() == 1
    
    def test_job_restore(self):
        """Test restoring a soft-deleted job."""
        job = Job.objects.create(title='Test Job')
        job.soft_delete()
        job.restore()
        
        assert Job.objects.filter(pk=job.pk).count() == 1
        assert job.is_deleted is False
    
    def test_active_resumes_property(self, sample_job, sample_resume):
        """Test active_resumes property excludes deleted resumes."""
        assert sample_job.active_resumes.count() == 1
        
        sample_resume.soft_delete()
        assert sample_job.active_resumes.count() == 0


@pytest.mark.django_db
class TestResumeModel:
    """Tests for Resume model."""
    
    def test_resume_creation(self, sample_job):
        """Test creating a resume."""
        resume = Resume.objects.create(
            job=sample_job,
            candidate_name='Jane Doe',
            final_score=75
        )
        assert resume.pk is not None
        assert resume.candidate_name == 'Jane Doe'
    
    def test_resume_str_method(self, sample_job):
        """Test the __str__ method."""
        resume = Resume.objects.create(
            job=sample_job,
            candidate_name='John Smith'
        )
        assert 'John Smith' in str(resume)
        assert sample_job.title in str(resume)
    
    def test_auto_tier_top(self, sample_job):
        """Test auto tier assignment for high score."""
        resume = Resume.objects.create(
            job=sample_job,
            candidate_name='Top Candidate',
            final_score=85
        )
        assert resume.tier == 'top'
        assert resume.recommendation == 'interview'
    
    def test_auto_tier_mid(self, sample_job):
        """Test auto tier assignment for medium score."""
        resume = Resume.objects.create(
            job=sample_job,
            candidate_name='Mid Candidate',
            final_score=70
        )
        assert resume.tier == 'mid'
        assert resume.recommendation == 'talent_pool'
    
    def test_auto_tier_low(self, sample_job):
        """Test auto tier assignment for low score."""
        resume = Resume.objects.create(
            job=sample_job,
            candidate_name='Low Candidate',
            final_score=40
        )
        assert resume.tier == 'low'
        assert resume.recommendation == 'reject'
    
    def test_resume_ordering(self, sample_job):
        """Test resumes are ordered by final_score desc."""
        Resume.objects.create(job=sample_job, candidate_name='Low', final_score=50)
        Resume.objects.create(job=sample_job, candidate_name='High', final_score=90)
        Resume.objects.create(job=sample_job, candidate_name='Mid', final_score=70)
        
        resumes = list(Resume.objects.all())
        assert resumes[0].candidate_name == 'High'
        assert resumes[1].candidate_name == 'Mid'
        assert resumes[2].candidate_name == 'Low'
