import logging
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Case, Count, IntegerField, Prefetch, Q, Value, When
from django.http import JsonResponse, FileResponse, Http404
from django.db import connection
from django.conf import settings
from .models import Job, Resume
from .forms import JobForm, ResumeForm, ResumeEditForm
from .utils import candidate_initial

logger = logging.getLogger(__name__)


def _ordered_active_resumes_queryset(resume_qs):
    """Match job detail ordering: interview recommendations first, then score."""
    return resume_qs.filter(is_deleted=False).annotate(
        decision_rank=Case(
            When(recommendation='interview', then=Value(3)),
            When(recommendation='talent_pool', then=Value(2)),
            When(recommendation='reject', then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by('-decision_rank', '-final_score', '-created_at')


def health_check(request):
    """Health check endpoint for monitoring and load balancers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return JsonResponse({
            'status': 'healthy',
            'database': 'connected',
            'version': '1.0.0'
        })
    except Exception as e:
        logger.error(f"Health check database connectivity failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'database': 'disconnected',
        }, status=503)


@login_required
def dashboard(request):
    """Dashboard with overview statistics."""
    # Single query for job counts
    job_stats = Job.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active'))
    )
    
    # Single aggregated query for all resume stats (reduces 8 queries to 1)
    resume_stats = Resume.objects.filter(job__is_deleted=False).aggregate(
        total=Count('id'),
        avg_score=Avg('final_score', filter=Q(final_score__isnull=False)),
        top_tier=Count('id', filter=Q(tier='top')),
        mid_tier=Count('id', filter=Q(tier='mid')),
        low_tier=Count('id', filter=Q(tier='low')),
        pending=Count('id', filter=Q(screening_status='pending')),
        processing=Count('id', filter=Q(screening_status='processing')),
    )
    
    recent_jobs = Job.objects.annotate(
        resume_count=Count('resumes', filter=Q(resumes__is_deleted=False))
    )[:5]
    recent_resumes = Resume.objects.filter(
        job__is_deleted=False
    ).select_related('job')[:5]
    
    context = {
        'total_jobs': job_stats['total'],
        'active_jobs': job_stats['active'],
        'total_resumes': resume_stats['total'],
        'avg_score': round(resume_stats['avg_score'] or 0, 1),
        'recent_jobs': recent_jobs,
        'recent_resumes': recent_resumes,
        'top_tier': resume_stats['top_tier'],
        'mid_tier': resume_stats['mid_tier'],
        'low_tier': resume_stats['low_tier'],
        'pending_screening': resume_stats['pending'],
        'processing_screening': resume_stats['processing'],
    }
    return render(request, 'core/dashboard.html', context)



@login_required
def job_list(request):
    """List all jobs with search, filter, and pagination support."""
    from django.core.paginator import Paginator

    resume_prefetch = Prefetch(
        'resumes',
        queryset=_ordered_active_resumes_queryset(Resume.objects),
    )

    jobs = Job.objects.annotate(resume_count=Count('resumes')).prefetch_related(resume_prefetch)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    

    status_filter = request.GET.get('status', 'active').strip()
    
    if status_filter == 'all':
        pass
    elif status_filter in ['active', 'draft', 'closed']:
        jobs = jobs.filter(status=status_filter)
    
    jobs = jobs.order_by('-created_at')
    

    paginator = Paginator(jobs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    for job in page_obj.object_list:
        job.preview_initials = [
            candidate_initial(r.candidate_name)
            for r in list(job.resumes.all())[:3]
        ]
    
    context = {
        'jobs': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'core/job_list.html', context)


@login_required
def job_create(request):
    """Create a new job."""
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            messages.success(request, 'Job created successfully!')
            return redirect('core:job_detail', pk=job.pk)
    else:
        form = JobForm()
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Post New Job'})


@login_required
def job_detail(request, pk):
    """View job details with associated resumes."""
    job = get_object_or_404(Job, pk=pk)
    resumes = _ordered_active_resumes_queryset(job.resumes)
    return render(request, 'core/job_detail.html', {'job': job, 'resumes': resumes})


@login_required
def job_edit(request, pk):
    """Edit an existing job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Job updated successfully!')
            return redirect('core:job_detail', pk=pk)
    else:
        form = JobForm(instance=job)
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Edit Job', 'job': job})


@login_required
def job_delete(request, pk):
    """Soft delete a job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        job.soft_delete()
        messages.success(request, f'Job "{job.title}" deleted successfully!')
        return redirect('core:job_list')
    return render(request, 'core/confirm_delete.html', {'object': job, 'type': 'job'})



@login_required
def resume_create(request, job_pk):
    """Create a new resume for a job."""
    job = get_object_or_404(Job, pk=job_pk)
    
    if job.status != 'active':
        status_label = 'Draft' if job.status == 'draft' else 'Closed'
        messages.error(request, f'Cannot add resume. This job is currently {status_label}.')
        return redirect('core:job_detail', pk=job_pk)
    
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.job = job
            resume.screening_status = 'pending'
            resume.save()
            
            # Queue for async AI screening - user won't have to wait
            from apps.core.tasks import screen_resume_task
            screen_resume_task.delay(resume.id)
            
            messages.success(
                request, 
                'Resume added successfully! AI screening is in progress - refresh to see results.'
            )
            
            return redirect('core:job_detail', pk=job_pk)
    else:
        form = ResumeForm()
    return render(request, 'core/resume_form.html', {'form': form, 'job': job, 'title': 'Add Resume'})


@login_required
def resume_detail(request, pk):
    """View resume details."""
    resume = get_object_or_404(Resume.objects.select_related('job'), pk=pk)
    return render(request, 'core/resume_detail.html', {'resume': resume})


@login_required
def resume_edit(request, pk):
    """Edit an existing resume with full control over AI-generated fields."""
    resume = get_object_or_404(Resume.objects.select_related('job'), pk=pk)
    if request.method == 'POST':
        form = ResumeEditForm(request.POST, request.FILES, instance=resume)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resume updated successfully!')
            return redirect('core:resume_detail', pk=pk)
    else:
        form = ResumeEditForm(instance=resume)
    return render(request, 'core/resume_edit_form.html', {'form': form, 'job': resume.job, 'title': 'Edit Resume', 'resume': resume})


@login_required
def resume_delete(request, pk):
    """Soft delete a resume."""
    resume = get_object_or_404(Resume, pk=pk)
    job_pk = resume.job.pk
    if request.method == 'POST':
        resume.soft_delete()
        messages.success(request, f'Resume for "{resume.candidate_name}" deleted successfully!')
        return redirect('core:job_detail', pk=job_pk)
    return render(request, 'core/confirm_delete.html', {'object': resume, 'type': 'resume', 'job_pk': job_pk})


@login_required
def serve_protected_media(request, path):
    """Serve media files with authentication to prevent unauthenticated access to PII."""
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    # Prevent path traversal outside MEDIA_ROOT
    if not os.path.abspath(full_path).startswith(os.path.abspath(settings.MEDIA_ROOT)):
        raise Http404
    if not os.path.exists(full_path):
        raise Http404
    return FileResponse(open(full_path, 'rb'))


@login_required
def resume_rescreen(request, pk):
    """Manually trigger AI screening for a resume."""
    resume = get_object_or_404(Resume, pk=pk)
    
    if request.method != 'POST':
        return redirect('core:resume_detail', pk=pk)
    
    try:
        from apps.core.services.resume_service import ResumeService
        result = ResumeService.process_resume(resume)
        
        if result.get('success'):
            messages.success(request, f'AI screening completed! Score: {result.get("final_score", 0):.0f}%')
        else:
            error_type = result.get('error_type', 'unknown')
            if error_type == 'extraction':
                messages.error(request, f'Failed to extract text: {result.get("error")}')
            elif error_type == 'job_description':
                messages.error(request, 'Job description is required for screening.')
            else:
                messages.error(request, f'Screening failed: {result.get("error")}')
                
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Re-screening failed: {e}")
        resume.screening_status = 'failed'
        resume.save(update_fields=['screening_status'])
        messages.error(request, f'Screening failed: {str(e)}')
    
    return redirect('core:resume_detail', pk=pk)