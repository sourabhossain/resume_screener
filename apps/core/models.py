import secrets

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=100, unique=True, help_text="Used as subdomain: slug.resumeai.com"
    )
    logo = models.ImageField(upload_to="org_logos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    max_jobs = models.PositiveIntegerField(default=10)
    max_resumes_per_month = models.PositiveIntegerField(default=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def subdomain_url(self):
        base = getattr(settings, "BASE_DOMAIN", "resumeai.com")
        scheme = (
            "http" if (base == "localhost" or base.endswith(".localhost")) else "https"
        )
        return f"{scheme}://{self.slug}.{base}"


class OrganizationMember(models.Model):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("member", "Member"),
        ("viewer", "Viewer"),
    ]
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="org_memberships"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    invited_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invites",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "user")]
        indexes = [
            models.Index(fields=["organization"], name="orgmember_org_idx"),
            models.Index(fields=["user"], name="orgmember_user_idx"),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.organization.name} ({self.role})"


class OrganizationInvite(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("expired", "Expired"),
    ]
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invites"
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20, choices=OrganizationMember.ROLE_CHOICES, default="member"
    )
    token = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite {self.email} → {self.organization.name}"

    def is_valid(self):
        return self.status == "pending" and self.expires_at > timezone.now()


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
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class Job(SoftDeleteModel):
    """Job Description model - stores job postings for resume screening."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("closed", "Closed"),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ("full_time", "Full-time"),
        ("part_time", "Part-time"),
        ("contract", "Contract"),
        ("freelance", "Freelance"),
        ("internship", "Internship"),
    ]

    LOCATION_TYPE_CHOICES = [
        ("on_site", "On-site"),
        ("remote", "Remote"),
        ("hybrid", "Hybrid"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to="jobs/", blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    employment_type = models.CharField(
        max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True
    )
    location_type = models.CharField(
        max_length=10, choices=LOCATION_TYPE_CHOICES, blank=True
    )
    location = models.CharField(max_length=255, blank=True)
    posted_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_type = models.CharField(max_length=50, blank=True)

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="jobs",
        null=True,
    )
    required_skills = models.JSONField(
        default=list, blank=True, help_text="Required skills for matching"
    )
    required_experience = models.FloatField(
        null=True, blank=True, help_text="Required years of experience"
    )
    required_education = models.JSONField(
        default=list, blank=True, help_text="Required education levels"
    )

    class Meta:
        db_table = "job_description"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "is_deleted"], name="job_status_deleted_idx"
            ),
            models.Index(fields=["-created_at"], name="job_created_idx"),
            models.Index(fields=["title"], name="job_title_idx"),
            models.Index(fields=["organization"], name="job_org_idx"),
            models.Index(fields=["organization", "status"], name="job_org_status_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def active_resumes(self):
        return self.resumes.filter(is_deleted=False)


class Resume(SoftDeleteModel):
    """Resume model - stores candidate resumes and their screening results."""

    TIER_CHOICES = [
        ("low", "Low"),
        ("mid", "Mid"),
        ("top", "Top"),
    ]

    RECOMMENDATION_CHOICES = [
        ("interview", "Interview"),
        ("talent_pool", "Talent Pool"),
        ("reject", "Reject"),
    ]

    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="resumes", db_column="job_id"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="resumes",
        null=True,
    )
    file_name = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to="resumes/", blank=True, null=True)
    candidate_name = models.CharField(max_length=255)
    raw_text = models.TextField(blank=True)
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, blank=True)
    recommendation = models.CharField(
        max_length=20, choices=RECOMMENDATION_CHOICES, blank=True
    )
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    experience_score = models.FloatField(null=True, blank=True)
    education_score = models.FloatField(null=True, blank=True)
    skills_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_type = models.CharField(max_length=50, blank=True)

    skills = models.JSONField(
        default=list, blank=True, help_text="Extracted skills from resume"
    )
    education = models.JSONField(
        default=list, blank=True, help_text="Extracted education"
    )
    certifications = models.JSONField(
        default=list, blank=True, help_text="Extracted certifications"
    )
    achievements = models.JSONField(
        default=list, blank=True, help_text="Extracted quantifiable achievements"
    )
    experience_years = models.FloatField(
        null=True, blank=True, help_text="Total years of experience"
    )
    certification_score = models.FloatField(null=True, blank=True)
    achievement_score = models.FloatField(null=True, blank=True)
    reasoning = models.TextField(
        blank=True, help_text="AI reasoning for recommendation"
    )

    SCREENING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    screening_status = models.CharField(
        max_length=20, choices=SCREENING_STATUS_CHOICES, default="pending"
    )

    # Link Verification
    extracted_links = models.JSONField(default=list, blank=True)
    verification_results = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        default="pending",
    )
    verification_score = models.FloatField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "resumes"
        ordering = [F("final_score").desc(nulls_last=True), "-created_at"]
        indexes = [
            models.Index(fields=["job", "is_deleted"], name="resume_job_deleted_idx"),
            models.Index(fields=["tier"], name="resume_tier_idx"),
            models.Index(fields=["-final_score"], name="resume_score_idx"),
            models.Index(fields=["screening_status"], name="resume_status_idx"),
            models.Index(fields=["organization"], name="resume_org_idx"),
            models.Index(
                fields=["verification_status"], name="resume_verification_idx"
            ),
            models.Index(
                fields=["organization", "screening_status"],
                name="resume_org_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.candidate_name} - {self.job.title}"

    def assign_tier_and_recommendation_from_final_score(self) -> None:
        """Align tier and decision with final_score using AI_SCREENING_CONFIG thresholds."""
        if self.final_score is None:
            return
        cfg = settings.AI_SCREENING_CONFIG
        score = self.final_score
        if score >= cfg["TOP_TIER_THRESHOLD"]:
            self.tier = "top"
            self.recommendation = "interview"
        elif score >= cfg["MID_TIER_THRESHOLD"]:
            self.tier = "mid"
            self.recommendation = "talent_pool"
        else:
            self.tier = "low"
            self.recommendation = "reject"

    def save(self, *args, **kwargs):
        self.assign_tier_and_recommendation_from_final_score()
        super().save(*args, **kwargs)
