from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Avg
from .models import Job, Resume
from .forms import JobForm, ResumeForm


def dashboard(request):
    """Dashboard with overview statistics."""
    total_jobs = Job.objects.count()
    active_jobs = Job.objects.filter(status='active').count()
    total_resumes = Resume.objects.count()
    avg_score = Resume.objects.filter(final_score__isnull=False).aggregate(Avg('final_score'))['final_score__avg'] or 0
    
    recent_jobs = Job.objects.all()[:5]
    recent_resumes = Resume.objects.select_related('job')[:5]
    
    context = {
        'total_jobs': total_jobs,
        'active_jobs': active_jobs,
        'total_resumes': total_resumes,
        'avg_score': round(avg_score, 1),
        'recent_jobs': recent_jobs,
        'recent_resumes': recent_resumes,
    }
    return render(request, 'core/dashboard.html', context)


def job_list(request):
    """List all jobs."""
    jobs = Job.objects.annotate(resume_count=Count('resumes')).order_by('-created_at')
    return render(request, 'core/job_list.html', {'jobs': jobs})


def job_create(request):
    """Create a new job."""
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Job created successfully!')
            return redirect('job_list')
    else:
        form = JobForm()
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Post New Job'})


def job_detail(request, pk):
    """View job details with associated resumes."""
    job = get_object_or_404(Job, pk=pk)
    resumes = job.resumes.filter(is_deleted=False).order_by('-final_score')
    return render(request, 'core/job_detail.html', {'job': job, 'resumes': resumes})


def job_edit(request, pk):
    """Edit an existing job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Job updated successfully!')
            return redirect('job_detail', pk=pk)
    else:
        form = JobForm(instance=job)
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Edit Job', 'job': job})


def job_delete(request, pk):
    """Soft delete a job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        job.soft_delete()
        messages.success(request, f'Job "{job.title}" deleted successfully!')
        return redirect('job_list')
    return render(request, 'core/confirm_delete.html', {'object': job, 'type': 'job'})


# Resume Views
def resume_create(request, job_pk):
    """Create a new resume for a job."""
    job = get_object_or_404(Job, pk=job_pk)
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.job = job
            resume.save()
            messages.success(request, 'Resume added successfully!')
            return redirect('job_detail', pk=job_pk)
    else:
        form = ResumeForm()
    return render(request, 'core/resume_form.html', {'form': form, 'job': job, 'title': 'Add Resume'})


def resume_detail(request, pk):
    """View resume details."""
    resume = get_object_or_404(Resume, pk=pk)
    return render(request, 'core/resume_detail.html', {'resume': resume})


def resume_edit(request, pk):
    """Edit an existing resume."""
    resume = get_object_or_404(Resume, pk=pk)
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES, instance=resume)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resume updated successfully!')
            return redirect('resume_detail', pk=pk)
    else:
        form = ResumeForm(instance=resume)
    return render(request, 'core/resume_form.html', {'form': form, 'job': resume.job, 'title': 'Edit Resume', 'resume': resume})


def resume_delete(request, pk):
    """Soft delete a resume."""
    resume = get_object_or_404(Resume, pk=pk)
    job_pk = resume.job.pk
    if request.method == 'POST':
        resume.soft_delete()
        messages.success(request, f'Resume for "{resume.candidate_name}" deleted successfully!')
        return redirect('job_detail', pk=job_pk)
    return render(request, 'core/confirm_delete.html', {'object': resume, 'type': 'resume', 'job_pk': job_pk})