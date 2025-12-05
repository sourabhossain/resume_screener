"""
Django REST Framework ViewSets for Job and Resume.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

from .models import Job, Resume
from .serializers import JobListSerializer, JobDetailSerializer, ResumeSerializer


@method_decorator(ratelimit(key='user_or_ip', rate='30/m', method='GET', block=True), name='list')
@method_decorator(ratelimit(key='user_or_ip', rate='30/m', method='GET', block=True), name='retrieve')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='POST', block=True), name='create')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='PUT', block=True), name='update')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='PATCH', block=True), name='partial_update')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='DELETE', block=True), name='destroy')
class JobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Job CRUD operations.
    
    list: GET /api/jobs/
    create: POST /api/jobs/
    retrieve: GET /api/jobs/{id}/
    update: PUT /api/jobs/{id}/
    partial_update: PATCH /api/jobs/{id}/
    destroy: DELETE /api/jobs/{id}/
    """
    queryset = Job.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        return JobDetailSerializer
    
    def get_queryset(self):
        queryset = Job.objects.annotate(resume_count=Count('resumes'))
        
        # Search filter
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(title__icontains=search)
        
        # Status filter
        status_filter = self.request.query_params.get('status', None)
        if status_filter in ['active', 'draft', 'closed']:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
    
    def perform_destroy(self, instance):
        """Soft delete instead of hard delete."""
        instance.soft_delete()
    
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore a soft-deleted job."""
        job = Job.objects.all_with_deleted().get(pk=pk)
        job.restore()
        return Response({'status': 'restored'})


@method_decorator(ratelimit(key='user_or_ip', rate='30/m', method='GET', block=True), name='list')
@method_decorator(ratelimit(key='user_or_ip', rate='30/m', method='GET', block=True), name='retrieve')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='POST', block=True), name='create')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='PUT', block=True), name='update')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='PATCH', block=True), name='partial_update')
@method_decorator(ratelimit(key='user_or_ip', rate='10/m', method='DELETE', block=True), name='destroy')
class ResumeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Resume CRUD operations.
    """
    queryset = Resume.objects.all()
    serializer_class = ResumeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Resume.objects.select_related('job')
        
        # Filter by job
        job_id = self.request.query_params.get('job', None)
        if job_id:
            queryset = queryset.filter(job_id=job_id)
        
        # Filter by tier
        tier = self.request.query_params.get('tier', None)
        if tier in ['top', 'mid', 'low']:
            queryset = queryset.filter(tier=tier)
        
        return queryset.order_by('-final_score', '-created_at')
    
    def perform_destroy(self, instance):
        """Soft delete instead of hard delete."""
        instance.soft_delete()
