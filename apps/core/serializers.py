"""
Django REST Framework Serializers for Job and Resume.
"""
from rest_framework import serializers
from .models import Job, Resume


class ResumeSerializer(serializers.ModelSerializer):
    tier_display = serializers.CharField(source='get_tier_display', read_only=True)
    recommendation_display = serializers.CharField(source='get_recommendation_display', read_only=True)
    
    class Meta:
        model = Resume
        fields = [
            'id', 'candidate_name', 'file', 'file_name', 'file_type',
            'tier', 'tier_display', 'recommendation', 'recommendation_display',
            'experience_score', 'education_score', 'skills_score', 'final_score',
            'matched_skills', 'missing_skills',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_name', 'file_type', 'created_at', 'updated_at']


class JobListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    resume_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'status', 'status_display',
            'posted_date', 'closing_date', 'resume_count', 'created_at'
        ]


class JobDetailSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    resumes = ResumeSerializer(many=True, read_only=True, source='active_resumes')
    resume_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'title', 'description', 'status', 'status_display',
            'posted_date', 'closing_date',
            'file', 'file_name', 'file_type',
            'resume_count', 'resumes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'file_name', 'file_type', 'created_at', 'updated_at']
    
    def get_resume_count(self, obj):
        return obj.active_resumes.count()
