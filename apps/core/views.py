from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg
from django.http import JsonResponse
from django.db import connection
from .models import Job, Resume
from .forms import JobForm, ResumeForm, ResumeEditForm


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
        return JsonResponse({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }, status=503)


@login_required
def dashboard(request):
    """Dashboard with overview statistics."""
    total_jobs = Job.objects.count()
    active_jobs = Job.objects.filter(status='active').count()
    
    active_resumes_qs = Resume.objects.filter(job__is_deleted=False)
    
    total_resumes = active_resumes_qs.count()
    avg_score = active_resumes_qs.filter(final_score__isnull=False).aggregate(Avg('final_score'))['final_score__avg'] or 0
    

    top_tier = active_resumes_qs.filter(tier='top').count()
    mid_tier = active_resumes_qs.filter(tier='mid').count()
    low_tier = active_resumes_qs.filter(tier='low').count()
    

    pending_screening = active_resumes_qs.filter(screening_status='pending').count()
    processing_screening = active_resumes_qs.filter(screening_status='processing').count()
    
    recent_jobs = Job.objects.all()[:5]
    recent_resumes = active_resumes_qs.select_related('job')[:5]
    
    context = {
        'total_jobs': total_jobs,
        'active_jobs': active_jobs,
        'total_resumes': total_resumes,
        'avg_score': round(avg_score, 1),
        'recent_jobs': recent_jobs,
        'recent_resumes': recent_resumes,
        'top_tier': top_tier,
        'mid_tier': mid_tier,
        'low_tier': low_tier,
        'pending_screening': pending_screening,
        'processing_screening': processing_screening,
    }
    return render(request, 'core/dashboard.html', context)



@login_required
def job_list(request):
    """List all jobs with search, filter, and pagination support."""
    from django.db.models import Q
    from django.core.paginator import Paginator
    
    jobs = Job.objects.annotate(resume_count=Count('resumes'))
    

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
    resumes = job.resumes.filter(is_deleted=False).order_by('-final_score')
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
            
            try:
                from apps.core.services.resume_service import ResumeService
                result = ResumeService.process_resume(resume)
                
                if result.get('success'):
                    messages.success(request, f'Resume added and AI screening completed! Score: {result.get("final_score", 0):.0f}%')
                else:
                    error_type = result.get('error_type', 'unknown')
                    if error_type == 'extraction':
                        messages.warning(request, f'Resume added but could not extract text: {result.get("error")}')
                    elif error_type == 'job_description':
                        messages.warning(request, 'Resume added but job has no description for AI screening.')
                    else:
                        messages.warning(request, f'Resume added but screening failed: {result.get("error")}')
                        
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Resume processing failed: {e}")
                messages.success(request, 'Resume added successfully!')
            
            return redirect('core:job_detail', pk=job_pk)
    else:
        form = ResumeForm()
    return render(request, 'core/resume_form.html', {'form': form, 'job': job, 'title': 'Add Resume'})


@login_required
def resume_detail(request, pk):
    """View resume details."""
    resume = get_object_or_404(Resume, pk=pk)
    return render(request, 'core/resume_detail.html', {'resume': resume})


@login_required
def resume_edit(request, pk):
    """Edit an existing resume with full control over AI-generated fields."""
    resume = get_object_or_404(Resume, pk=pk)
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