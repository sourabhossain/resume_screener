from django.contrib import admin
from .models import Job, Resume


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'posted_date', 'closing_date', 'resume_count', 'is_deleted')
    list_filter = ('status', 'posted_date', 'is_deleted')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 20
    
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'status')
        }),
        ('Dates', {
            'fields': ('posted_date', 'closing_date')
        }),
        ('File', {
            'fields': ('file', 'file_name', 'file_type'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'is_deleted'),
            'classes': ('collapse',)
        }),
    )
    
    def resume_count(self, obj):
        return obj.resumes.filter(is_deleted=False).count()
    resume_count.short_description = 'Resumes'


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('candidate_name', 'job', 'final_score', 'tier', 'recommendation', 'created_at', 'is_deleted')
    list_filter = ('tier', 'recommendation', 'job', 'is_deleted')
    search_fields = ('candidate_name', 'job__title')
    date_hierarchy = 'created_at'
    ordering = ('-final_score', '-created_at')
    list_per_page = 25
    
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Candidate Info', {
            'fields': ('candidate_name', 'job')
        }),
        ('Scores', {
            'fields': ('experience_score', 'education_score', 'skills_score', 'final_score')
        }),
        ('Assessment', {
            'fields': ('tier', 'recommendation')
        }),
        ('Skills Analysis', {
            'fields': ('matched_skills', 'missing_skills'),
            'classes': ('collapse',)
        }),
        ('File', {
            'fields': ('file', 'file_name', 'file_type'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'is_deleted'),
            'classes': ('collapse',)
        }),
    )