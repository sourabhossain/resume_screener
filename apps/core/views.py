from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg
from django.http import JsonResponse
from django.db import connection
from .models import Job, Resume
from .forms import JobForm, ResumeForm


def health_check(request):
    """Health check endpoint for monitoring and load balancers."""
    try:
        # Check database connectivity
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
    
    # Filter out resumes from deleted jobs
    active_resumes_qs = Resume.objects.filter(job__is_deleted=False)
    
    total_resumes = active_resumes_qs.count()
    avg_score = active_resumes_qs.filter(final_score__isnull=False).aggregate(Avg('final_score'))['final_score__avg'] or 0
    
    # Tier distribution
    top_tier = active_resumes_qs.filter(tier='top').count()
    mid_tier = active_resumes_qs.filter(tier='mid').count()
    low_tier = active_resumes_qs.filter(tier='low').count()
    
    # Screening status
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
        # Tier distribution
        'top_tier': top_tier,
        'mid_tier': mid_tier,
        'low_tier': low_tier,
        # Screening status
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
    
    # Search functionality
    search_query = request.GET.get('q', '').strip()
    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    # Status filter - default to 'active' if not specified
    status_filter = request.GET.get('status', 'active').strip()
    
    # Handle 'all' to show all jobs (no filter)
    if status_filter == 'all':
        pass  # No filtering
    elif status_filter in ['active', 'draft', 'closed']:
        jobs = jobs.filter(status=status_filter)
    
    jobs = jobs.order_by('-created_at')
    
    # Pagination - 10 items per page
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


# Resume Views
@login_required
def resume_create(request, job_pk):
    """Create a new resume for a job."""
    job = get_object_or_404(Job, pk=job_pk)
    
    # Only allow resume creation for active jobs
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
            
            # Trigger AI screening task
            try:
                from apps.core.tasks import screen_resume_task
                screen_resume_task.delay(resume.id)
                messages.success(request, 'Resume added! AI screening started in background.')
            except Exception as e:
                # Celery/Redis not available - run synchronous screening
                try:
                    from apps.core.services.document_extractor import DocumentExtractor
                    from apps.core.services.ai_screener import screen_resume
                    
                    # Extract text from resume
                    if resume.file:
                        resume.raw_text = DocumentExtractor.extract(resume.file.path)
                        resume.save(update_fields=['raw_text'])
                    
                    # Run AI screening synchronously
                    if resume.raw_text and job.description:
                        resume.screening_status = 'processing'
                        resume.save(update_fields=['screening_status'])
                        
                        result = screen_resume(resume.raw_text, job.description)
                        
                        if not result.get('error'):
                            resume.skills = result.get('skills', [])
                            resume.education = result.get('education', [])
                            resume.certifications = result.get('certifications', [])
                            resume.experience_years = result.get('experience_years', 0)
                            resume.matched_skills = result.get('matched_skills', [])
                            resume.missing_skills = result.get('missing_skills', [])
                            resume.skills_score = result.get('skill_score', 0)
                            resume.experience_score = result.get('experience_score', 0)
                            resume.education_score = result.get('education_score', 0)
                            resume.certification_score = result.get('certification_score', 0)
                            resume.final_score = result.get('final_score', 0)
                            resume.tier = result.get('tier', '').lower()
                            resume.recommendation = result.get('recommendation', '').lower().replace(' ', '_')
                            resume.reasoning = result.get('reasoning', '')
                            resume.screening_status = 'completed'
                            resume.save()
                            messages.success(request, 'Resume added and AI screening completed!')
                        else:
                            resume.screening_status = 'failed'
                            resume.save(update_fields=['screening_status'])
                            messages.warning(request, f'Resume added but screening failed: {result.get("error")}')
                    else:
                        messages.success(request, 'Resume added successfully!')
                except Exception as sync_error:
                    import logging
                    logging.getLogger(__name__).error(f"Sync screening failed: {sync_error}")
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
    """Edit an existing resume."""
    resume = get_object_or_404(Resume, pk=pk)
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES, instance=resume)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resume updated successfully!')
            return redirect('core:resume_detail', pk=pk)
    else:
        form = ResumeForm(instance=resume)
    return render(request, 'core/resume_form.html', {'form': form, 'job': resume.job, 'title': 'Edit Resume', 'resume': resume})


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
        from apps.core.services.document_extractor import DocumentExtractor
        from apps.core.services.ai_screener import screen_resume
        
        # Extract text if not already done
        if not resume.raw_text and resume.file:
            resume.raw_text = DocumentExtractor.extract(resume.file.path)
            resume.save(update_fields=['raw_text'])
        
        if not resume.raw_text:
            messages.error(request, 'No resume text available for screening.')
            return redirect('core:resume_detail', pk=pk)
        
        if not resume.job.description:
            messages.error(request, 'Job description is required for screening.')
            return redirect('core:resume_detail', pk=pk)
        
        # Run AI screening
        resume.screening_status = 'processing'
        resume.save(update_fields=['screening_status'])
        
        result = screen_resume(resume.raw_text, resume.job.description)
        
        if not result.get('error'):
            resume.skills = result.get('skills', [])
            resume.education = result.get('education', [])
            resume.certifications = result.get('certifications', [])
            resume.experience_years = result.get('experience_years', 0)
            resume.matched_skills = result.get('matched_skills', [])
            resume.missing_skills = result.get('missing_skills', [])
            resume.skills_score = result.get('skill_score', 0)
            resume.experience_score = result.get('experience_score', 0)
            resume.education_score = result.get('education_score', 0)
            resume.certification_score = result.get('certification_score', 0)
            resume.final_score = result.get('final_score', 0)
            resume.tier = result.get('tier', '').lower()
            resume.recommendation = result.get('recommendation', '').lower().replace(' ', '_')
            resume.reasoning = result.get('reasoning', '')
            resume.screening_status = 'completed'
            resume.save()
            messages.success(request, f'AI screening completed! Score: {resume.final_score:.0f}%')
        else:
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            messages.error(request, f'Screening failed: {result.get("error")}')
            
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Re-screening failed: {e}")
        resume.screening_status = 'failed'
        resume.save(update_fields=['screening_status'])
        messages.error(request, f'Screening failed: {str(e)}')
    
    return redirect('core:resume_detail', pk=pk)