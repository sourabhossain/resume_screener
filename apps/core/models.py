from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted objects by default."""
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        return super().get_queryset()
    
    def deleted_only(self):
        return super().get_queryset().filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """Abstract base model with soft delete functionality."""
    
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    objects = SoftDeleteManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()
    
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save()


class Job(SoftDeleteModel):
    """Job Description model - stores job postings for resume screening."""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='jobs/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    posted_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_type = models.CharField(max_length=50, blank=True)
    

    required_skills = models.JSONField(default=list, blank=True, help_text="Required skills for matching")
    required_experience = models.FloatField(null=True, blank=True, help_text="Required years of experience")
    required_education = models.JSONField(default=list, blank=True, help_text="Required education levels")
    
    class Meta:
        db_table = 'job_description'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'is_deleted'], name='job_status_deleted_idx'),
            models.Index(fields=['-created_at'], name='job_created_idx'),
            models.Index(fields=['title'], name='job_title_idx'),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def active_resumes(self):
        return self.resumes.filter(is_deleted=False)


class Resume(SoftDeleteModel):
    """Resume model - stores candidate resumes and their screening results."""
    
    TIER_CHOICES = [
        ('low', 'Low'),
        ('mid', 'Mid'),
        ('top', 'Top'),
    ]
    
    RECOMMENDATION_CHOICES = [
        ('interview', 'Interview'),
        ('talent_pool', 'Talent Pool'),
        ('reject', 'Reject'),
    ]
    
    job = models.ForeignKey(
        Job, 
        on_delete=models.CASCADE, 
        related_name='resumes',
        db_column='job_id'
    )
    file_name = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='resumes/', blank=True, null=True)
    candidate_name = models.CharField(max_length=255)
    raw_text = models.TextField(blank=True)
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, blank=True)
    recommendation = models.CharField(max_length=20, choices=RECOMMENDATION_CHOICES, blank=True)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    experience_score = models.FloatField(null=True, blank=True)
    education_score = models.FloatField(null=True, blank=True)
    skills_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_type = models.CharField(max_length=50, blank=True)
    

    skills = models.JSONField(default=list, blank=True, help_text="Extracted skills from resume")
    education = models.JSONField(default=list, blank=True, help_text="Extracted education")
    certifications = models.JSONField(default=list, blank=True, help_text="Extracted certifications")
    experience_years = models.FloatField(null=True, blank=True, help_text="Total years of experience")
    certification_score = models.FloatField(null=True, blank=True)
    reasoning = models.TextField(blank=True, help_text="AI reasoning for recommendation")
    
    SCREENING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    screening_status = models.CharField(
        max_length=20, 
        choices=SCREENING_STATUS_CHOICES, 
        default='pending'
    )
    
    class Meta:
        db_table = 'resumes'
        ordering = ['-final_score', '-created_at']
        indexes = [
            models.Index(fields=['job', 'is_deleted'], name='resume_job_deleted_idx'),
            models.Index(fields=['tier'], name='resume_tier_idx'),
            models.Index(fields=['-final_score'], name='resume_score_idx'),
            models.Index(fields=['screening_status'], name='resume_status_idx'),
        ]
    
    def __str__(self):
        return f"{self.candidate_name} - {self.job.title}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate tier and recommendation based on final_score."""
        if self.final_score is not None:
            if self.final_score >= 80:
                self.tier = 'top'
                self.recommendation = 'interview'
            elif self.final_score >= 60:
                self.tier = 'mid'
                self.recommendation = 'talent_pool'
            else:
                self.tier = 'low'
                self.recommendation = 'reject'
        super().save(*args, **kwargs)
