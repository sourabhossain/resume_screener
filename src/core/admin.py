from django.contrib import admin
from .models import Job, Resume

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'posted_date', 'closing_date')
    list_filter = ('status', 'posted_date')
    search_fields = ('title',)

@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('candidate_name', 'job', 'final_score', 'tier', 'created_at')
    list_filter = ('tier', 'job') 
    search_fields = ('candidate_name',)