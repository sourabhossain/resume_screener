"""
Django REST Framework Serializers for Job and Resume.
"""
import os

from django import forms
from rest_framework import serializers

from .forms import FileValidationMixin
from .models import Job, Resume


class ResumeSerializer(serializers.ModelSerializer):
    """Serializer for Resume with computed display fields."""
    job = serializers.PrimaryKeyRelatedField(queryset=Job.objects.all())
    tier_display = serializers.CharField(source='get_tier_display', read_only=True)
    recommendation_display = serializers.CharField(source='get_recommendation_display', read_only=True)
    screening_status_display = serializers.CharField(source='get_screening_status_display', read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)

    class Meta:
        model = Resume
        fields = [
            'id', 'job', 'candidate_name', 'file', 'file_name', 'file_type',
            'tier', 'tier_display', 'recommendation', 'recommendation_display',
            'screening_status', 'screening_status_display',
            'experience_score', 'education_score', 'skills_score',
            'certification_score', 'achievement_score', 'final_score',
            'matched_skills', 'missing_skills', 'skills', 'education', 'certifications',
            'achievements',
            'reasoning',
            'extracted_links', 'verification_results', 'verification_status',
            'verification_status_display', 'verification_score', 'verified_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'file_name', 'file_type', 'created_at', 'updated_at',
            'tier', 'tier_display', 'recommendation', 'recommendation_display',
            'screening_status', 'screening_status_display',
            'achievement_score', 'skills', 'education', 'certifications', 'achievements',
            'matched_skills', 'missing_skills', 'reasoning',
            'extracted_links', 'verification_results', 'verification_status',
            'verification_status_display', 'verification_score', 'verified_at',
        ]

    def validate_file(self, file):
        """Same type/size/magic-byte checks as the upload forms."""
        try:
            return FileValidationMixin().validate_resume_file(file)
        except forms.ValidationError as e:
            raise serializers.ValidationError(e.messages)

    def validate(self, attrs):
        # Same rules as the upload views: a new resume needs a file and an active job
        if self.instance is None:
            if not attrs.get('file'):
                raise serializers.ValidationError({'file': 'This field is required.'})
            if attrs['job'].status != 'active':
                raise serializers.ValidationError({'job': 'Cannot add resume. This job is not active.'})
        return attrs

    @staticmethod
    def _apply_file_metadata(validated_data):
        file = validated_data.get('file')
        if file:
            validated_data['file_name'] = file.name
            validated_data['file_type'] = os.path.splitext(file.name)[1].lstrip('.').lower()
            # Text cached from a previous file would otherwise be screened again
            validated_data['raw_text'] = ''

    def create(self, validated_data):
        self._apply_file_metadata(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._apply_file_metadata(validated_data)
        return super().update(instance, validated_data)


class JobListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for job listings."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    resume_count = serializers.IntegerField(read_only=True)  # Expects annotation from viewset
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'status', 'status_display',
            'posted_date', 'closing_date', 'resume_count', 'created_at'
        ]


class JobDetailSerializer(serializers.ModelSerializer):
    """Full serializer for job details with resumes."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    resumes = ResumeSerializer(many=True, read_only=True, source='_active_resumes')
    resume_count = serializers.IntegerField(read_only=True)  # Uses annotation from viewset
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'description', 'status', 'status_display',
            'posted_date', 'closing_date',
            'file', 'file_name', 'file_type',
            'required_skills', 'required_experience', 'required_education',
            'resume_count', 'resumes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_name', 'file_type', 'created_at', 'updated_at']

