import logging
import os
import secrets
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Case, Count, IntegerField, Prefetch, Q, Value, When
from django.http import JsonResponse, FileResponse, Http404
from django.db import connection, transaction
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from .models import Job, Resume, Organization, OrganizationMember, OrganizationInvite
from .forms import JobForm, ResumeForm, ResumeEditForm
from .utils import candidate_initial

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tenant guard decorator
# ---------------------------------------------------------------------------

def require_org(view_func):
    """Ensure request.organization is set and user is authenticated + a member."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.organization:
            # Send to org_picker, not landing — landing redirects back to
            # dashboard for authenticated users, which would loop forever.
            return redirect('core:org_picker')
        if not request.user.is_superuser:
            if not OrganizationMember.objects.filter(
                organization=request.organization,
                user=request.user
            ).exists():
                messages.error(request, "You don't have access to this organization.")
                return redirect('core:org_picker')
        return view_func(request, *args, **kwargs)
    return wrapper


def require_admin(view_func):
    """Ensure authenticated user is an org admin (or superuser)."""
    @wraps(view_func)
    @require_org
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            if not OrganizationMember.objects.filter(
                organization=request.organization,
                user=request.user,
                role='admin'
            ).exists():
                messages.error(request, "Admin access required.")
                return redirect('core:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ordered_active_resumes_queryset(resume_qs):
    return resume_qs.filter(is_deleted=False).annotate(
        decision_rank=Case(
            When(recommendation='interview', then=Value(3)),
            When(recommendation='talent_pool', then=Value(2)),
            When(recommendation='reject', then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by('-decision_rank', '-final_score', '-created_at')


def _pipeline_stats(resume_qs):
    stats = {
        'total': resume_qs.count(),
        'interview': 0,
        'talent_pool': 0,
        'reject': 0,
        'undecided': 0,
    }
    for row in resume_qs.values('recommendation').annotate(c=Count('id')):
        key = (row['recommendation'] or '').strip()
        n = row['c']
        if key == 'interview':
            stats['interview'] = n
        elif key == 'talent_pool':
            stats['talent_pool'] = n
        elif key == 'reject':
            stats['reject'] = n
        else:
            stats['undecided'] += n
    return stats


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({'status': 'healthy', 'database': 'connected', 'version': '1.0.0'})
    except Exception as e:
        logger.error(f"Health check database connectivity failed: {e}")
        return JsonResponse({'status': 'unhealthy', 'database': 'disconnected'}, status=503)


def landing(request):
    if request.organization and request.user.is_authenticated:
        # Only redirect when the user will actually make it past @require_org.
        # Without the membership check, non-members loop:
        #   landing → dashboard → require_org → landing → ...
        can_enter = request.user.is_superuser or OrganizationMember.objects.filter(
            organization=request.organization,
            user=request.user,
        ).exists()
        if can_enter:
            return redirect('core:dashboard')
    return render(request, 'core/landing.html')


# ---------------------------------------------------------------------------
# Tenant-scoped views
# ---------------------------------------------------------------------------

@require_org
def dashboard(request):
    org = request.organization

    job_stats = Job.objects.filter(organization=org).aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='active'))
    )

    resume_stats = Resume.objects.filter(
        organization=org, job__is_deleted=False
    ).aggregate(
        total=Count('id'),
        avg_score=Avg('final_score', filter=Q(final_score__isnull=False)),
        top_tier=Count('id', filter=Q(tier='top')),
        mid_tier=Count('id', filter=Q(tier='mid')),
        low_tier=Count('id', filter=Q(tier='low')),
        pending=Count('id', filter=Q(screening_status='pending')),
        processing=Count('id', filter=Q(screening_status='processing')),
    )

    recent_jobs = Job.objects.filter(organization=org).select_related('organization').annotate(
        resume_count=Count('resumes', filter=Q(resumes__is_deleted=False))
    )[:5]
    recent_resumes = Resume.objects.filter(
        organization=org, job__is_deleted=False
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


@require_org
def job_list(request):
    from django.core.paginator import Paginator

    org = request.organization
    resume_prefetch = Prefetch(
        'resumes',
        queryset=_ordered_active_resumes_queryset(Resume.all_objects.all()),
    )

    jobs = Job.objects.filter(organization=org).annotate(
        resume_count=Count('resumes', filter=Q(resumes__is_deleted=False))
    ).prefetch_related(resume_prefetch)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        jobs = jobs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    status_filter = request.GET.get('status', 'active').strip()
    if status_filter in ['active', 'draft', 'closed']:
        jobs = jobs.filter(status=status_filter)

    jobs = jobs.order_by('-created_at')

    paginator = Paginator(jobs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

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


@require_org
def job_create(request):
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save(commit=False)
            job.organization = request.organization
            job.save()
            messages.success(request, 'Job created successfully!')
            return redirect('core:job_detail', pk=job.pk)
    else:
        form = JobForm()
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Post New Job'})


@require_org
def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk, organization=request.organization)
    resumes = _ordered_active_resumes_queryset(job.resumes)
    return render(
        request,
        'core/job_detail.html',
        {
            'job': job,
            'resumes': resumes,
            'pipeline_stats': _pipeline_stats(resumes),
        },
    )


@require_org
def job_edit(request, pk):
    job = get_object_or_404(Job, pk=pk, organization=request.organization)
    if request.method == 'POST':
        form = JobForm(request.POST, request.FILES, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Job updated successfully!')
            return redirect('core:job_detail', pk=pk)
    else:
        form = JobForm(instance=job)
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Edit Job', 'job': job})


@require_org
def job_delete(request, pk):
    job = get_object_or_404(Job, pk=pk, organization=request.organization)
    if request.method == 'POST':
        job.soft_delete()
        messages.success(request, f'Job "{job.title}" deleted successfully!')
        return redirect('core:job_list')
    return render(request, 'core/confirm_delete.html', {'object': job, 'type': 'job'})


@require_org
def resume_create(request, job_pk):
    job = get_object_or_404(Job, pk=job_pk, organization=request.organization)

    if job.status != 'active':
        status_label = 'Draft' if job.status == 'draft' else 'Closed'
        messages.error(request, f'Cannot add resume. This job is currently {status_label}.')
        return redirect('core:job_detail', pk=job_pk)

    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.job = job
            resume.organization = request.organization
            resume.screening_status = 'processing'
            resume.save()

            from apps.core.tasks import screen_resume_task
            transaction.on_commit(lambda: screen_resume_task.delay(resume.id))

            messages.success(
                request,
                'Resume added. AI screening is running in the background—the pipeline row will refresh automatically.',
            )
            return redirect('core:job_detail', pk=job_pk)
    else:
        form = ResumeForm()
    return render(request, 'core/resume_form.html', {'form': form, 'job': job, 'title': 'Add Resume'})


@require_org
def resume_detail(request, pk):
    resume = get_object_or_404(
        Resume.objects.select_related('job'),
        pk=pk,
        organization=request.organization
    )
    return render(request, 'core/resume_detail.html', {'resume': resume})


@require_org
def resume_edit(request, pk):
    resume = get_object_or_404(
        Resume.objects.select_related('job'),
        pk=pk,
        organization=request.organization
    )
    if request.method == 'POST':
        form = ResumeEditForm(request.POST, request.FILES, instance=resume)
        if form.is_valid():
            form.save()
            messages.success(request, 'Resume updated successfully!')
            return redirect('core:resume_detail', pk=pk)
    else:
        form = ResumeEditForm(instance=resume)
    return render(request, 'core/resume_edit_form.html', {'form': form, 'job': resume.job, 'title': 'Edit Resume', 'resume': resume})


@require_org
def resume_delete(request, pk):
    resume = get_object_or_404(Resume, pk=pk, organization=request.organization)
    job_pk = resume.job.pk
    if request.method == 'POST':
        resume.soft_delete()
        messages.success(request, f'Resume for "{resume.candidate_name}" deleted successfully!')
        return redirect('core:job_detail', pk=job_pk)
    return render(request, 'core/confirm_delete.html', {'object': resume, 'type': 'resume', 'job_pk': job_pk})


@login_required
@ratelimit(key='user', rate='60/m', block=True)
def serve_protected_media(request, path):
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    media_root = os.path.abspath(settings.MEDIA_ROOT) + os.sep
    if not os.path.abspath(full_path).startswith(media_root):
        raise Http404
    if not os.path.exists(full_path):
        raise Http404
    return FileResponse(open(full_path, 'rb'))


@require_org
def resume_status_fragment(request, pk):
    resume = get_object_or_404(
        Resume.objects.select_related('job'),
        pk=pk,
        organization=request.organization
    )
    return render(request, 'core/partials/resume_status.html', {'resume': resume})


@require_org
def resume_row_fragment(request, pk):
    resume = get_object_or_404(
        Resume.objects.select_related('job'),
        pk=pk,
        organization=request.organization
    )
    return render(request, 'core/partials/resume_row.html', {'resume': resume})


@require_org
def resume_bulk_create(request, job_pk):
    job = get_object_or_404(Job, pk=job_pk, organization=request.organization)

    if job.status != 'active':
        status_label = 'Draft' if job.status == 'draft' else 'Closed'
        messages.error(request, f'Cannot add resumes. This job is currently {status_label}.')
        return redirect('core:job_detail', pk=job_pk)

    if request.method == 'POST':
        files = request.FILES.getlist('files')

        if not files:
            messages.error(request, 'Please select at least one file.')
            return render(request, 'core/resume_bulk_form.html', {'job': job})

        if len(files) > 20:
            messages.error(request, 'Maximum 20 files per upload.')
            return render(request, 'core/resume_bulk_form.html', {'job': job})

        from apps.core.tasks import screen_resume_task

        ALLOWED = {'pdf', 'docx'}
        MAX_SIZE = 5 * 1024 * 1024
        MAGIC = {'pdf': b'%PDF', 'docx': b'PK\x03\x04'}

        queued = 0
        skipped = []

        for file in files:
            if file.size > MAX_SIZE:
                skipped.append(f'"{file.name}" exceeds the 5 MB limit')
                continue

            _, raw_ext = os.path.splitext(file.name)
            ext = raw_ext.lstrip('.').lower()
            if ext not in ALLOWED:
                skipped.append(f'"{file.name}" — only PDF or DOCX supported')
                continue

            file.seek(0)
            header = file.read(8)
            file.seek(0)
            if not header.startswith(MAGIC[ext]):
                skipped.append(f'"{file.name}" — file content does not match {ext.upper()} format')
                continue

            candidate_name = os.path.splitext(file.name)[0].replace('_', ' ').replace('-', ' ').strip() or 'Unknown'

            resume = Resume(
                job=job,
                organization=request.organization,
                candidate_name=candidate_name,
                file_name=file.name,
                file_type=ext,
                screening_status='processing',
            )
            resume.file.save(file.name, file, save=True)
            resume_id = resume.id
            transaction.on_commit(lambda rid=resume_id: screen_resume_task.delay(rid))
            queued += 1

        if queued:
            messages.success(request, f'{queued} resume{"s" if queued != 1 else ""} uploaded. AI screening is running in the background.')
        for msg in skipped:
            messages.warning(request, msg)

        return redirect('core:job_detail', pk=job_pk)

    return render(request, 'core/resume_bulk_form.html', {'job': job})


@require_org
def resume_rescreen(request, pk):
    resume = get_object_or_404(Resume, pk=pk, organization=request.organization)

    if request.method != 'POST':
        return redirect('core:resume_detail', pk=pk)

    from apps.core.tasks import screen_resume_task
    updated = Resume.objects.filter(
        pk=pk, screening_status__in=['pending', 'completed', 'failed']
    ).update(screening_status='processing')
    if not updated:
        messages.info(request, 'Screening is already in progress. Please wait for it to complete.')
        return redirect('core:resume_detail', pk=pk)

    screen_resume_task.delay(resume.id)
    messages.success(request, 'AI screening queued! Results will appear shortly.')
    return redirect('core:resume_detail', pk=pk)


# ---------------------------------------------------------------------------
# Organization registration
# ---------------------------------------------------------------------------

def org_register(request):
    """Public registration: create org + admin user."""
    from django.utils.text import slugify
    from django.contrib.auth.models import User

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip() or slugify(name)
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        RESERVED_SLUGS = {
            'admin', 'superadmin', 'www', 'api', 'static', 'media',
            'health', 'login', 'logout', 'register', 'invite', 'dashboard',
        }

        errors = {}
        if not name:
            errors['name'] = 'Company name is required.'
        if not slug:
            errors['slug'] = 'Slug is required.'
        elif slug in RESERVED_SLUGS:
            errors['slug'] = f'"{slug}" is a reserved name and cannot be used as a slug.'
        elif Organization.objects.filter(slug=slug).exists():
            errors['slug'] = 'This slug is already taken.'
        if not email:
            errors['email'] = 'Email is required.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'A user with this email already exists.'
        if not password:
            errors['password'] = 'Password is required.'
        elif len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif password != password2:
            errors['password'] = 'Passwords do not match.'

        if errors:
            return render(request, 'core/register.html', {
                'errors': errors, 'name': name, 'slug': slug, 'email': email,
            })

        org = Organization.objects.create(name=name, slug=slug)
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        user = User.objects.create_user(username=username, email=email, password=password)
        OrganizationMember.objects.create(organization=org, user=user, role='admin')

        from django.contrib.auth import authenticate, login as auth_login
        user = authenticate(request, username=username, password=password)
        if user:
            auth_login(request, user)

        messages.success(request, f'Welcome to {org.name}! Your organization has been created.')
        # In dev (FORCE_TENANT_SLUG matches new org), stay on current domain.
        # In production, redirect to the org's own subdomain.
        if request.organization and request.organization == org:
            return redirect('core:dashboard')
        return redirect(org.subdomain_url)

    return render(request, 'core/register.html')


# ---------------------------------------------------------------------------
# Organization settings (admin only)
# ---------------------------------------------------------------------------

@require_admin
def org_settings(request):
    org = request.organization
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            org.name = name
        if 'logo' in request.FILES:
            org.logo = request.FILES['logo']
        org.save()
        messages.success(request, 'Organization settings updated.')
        return redirect('core:org_settings')

    member_count = org.members.count()
    job_count = Job.objects.filter(organization=org).count()
    return render(request, 'core/org_settings.html', {
        'org': org,
        'member_count': member_count,
        'job_count': job_count,
    })


# ---------------------------------------------------------------------------
# Member management (admin only)
# ---------------------------------------------------------------------------

@require_admin
def org_members(request):
    from django.utils import timezone
    from django.core.mail import send_mail
    from django.contrib.auth.models import User

    org = request.organization
    members = OrganizationMember.objects.filter(
        organization=org
    ).select_related('user').order_by('joined_at')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'invite':
            email = request.POST.get('email', '').strip()
            role = request.POST.get('role', 'member')
            if not email:
                messages.error(request, 'Email is required.')
            elif OrganizationMember.objects.filter(
                organization=org, user__email=email
            ).exists():
                messages.error(request, f'{email} is already a member.')
            else:
                token = secrets.token_urlsafe(32)
                invite = OrganizationInvite.objects.create(
                    organization=org,
                    email=email,
                    role=role,
                    token=token,
                    invited_by=request.user,
                    expires_at=timezone.now() + timezone.timedelta(days=7),
                )
                invite_url = request.build_absolute_uri(
                    f'/invite/{token}/'
                )
                send_mail(
                    subject=f"You're invited to join {org.name} on ResumeAI",
                    message=f"You've been invited to join {org.name}.\n\nAccept here: {invite_url}\n\nThis link expires in 7 days.",
                    from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@resumeai.com',
                    recipient_list=[email],
                    fail_silently=True,
                )
                messages.success(request, f'Invitation sent to {email}.')

        elif action == 'remove':
            member_id = request.POST.get('member_id')
            member = get_object_or_404(OrganizationMember, pk=member_id, organization=org)
            if member.user == request.user:
                messages.error(request, "You cannot remove yourself.")
            else:
                member.delete()
                messages.success(request, f'Removed {member.user.email}.')

        elif action == 'change_role':
            member_id = request.POST.get('member_id')
            new_role = request.POST.get('role')
            member = get_object_or_404(OrganizationMember, pk=member_id, organization=org)
            if new_role in dict(OrganizationMember.ROLE_CHOICES):
                member.role = new_role
                member.save()
                messages.success(request, f'Role updated for {member.user.email}.')

        return redirect('core:org_members')

    pending_invites = OrganizationInvite.objects.filter(
        organization=org, status='pending'
    ).order_by('-created_at')

    return render(request, 'core/members.html', {
        'org': org,
        'members': members,
        'pending_invites': pending_invites,
    })


# ---------------------------------------------------------------------------
# Accept invite
# ---------------------------------------------------------------------------

def accept_invite(request, token):
    from django.contrib.auth.models import User
    from django.utils import timezone

    invite = get_object_or_404(OrganizationInvite, token=token)

    if not invite.is_valid():
        messages.error(request, 'This invitation has expired or is no longer valid.')
        return redirect('core:landing')

    if request.method == 'POST':
        action = request.POST.get('action')

        if request.user.is_authenticated:
            user = request.user
        else:
            if action == 'login':
                from django.contrib.auth import authenticate, login as auth_login
                username = request.POST.get('username', '')
                password = request.POST.get('password', '')
                user = authenticate(request, username=username, password=password)
                if not user:
                    messages.error(request, 'Invalid credentials.')
                    return render(request, 'core/accept_invite.html', {'invite': invite})
                auth_login(request, user)
            elif action == 'register':
                email = request.POST.get('email', invite.email)
                password = request.POST.get('password', '')
                password2 = request.POST.get('password2', '')
                if password != password2 or len(password) < 8:
                    messages.error(request, 'Password must be at least 8 characters and match.')
                    return render(request, 'core/accept_invite.html', {'invite': invite})
                if User.objects.filter(email=email).exists():
                    messages.error(request, 'An account with this email already exists. Please log in.')
                    return render(request, 'core/accept_invite.html', {'invite': invite})
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                user = User.objects.create_user(username=username, email=email, password=password)
                from django.contrib.auth import login as auth_login
                auth_login(request, user)
            else:
                return render(request, 'core/accept_invite.html', {'invite': invite})

        if not OrganizationMember.objects.filter(
            organization=invite.organization, user=user
        ).exists():
            OrganizationMember.objects.create(
                organization=invite.organization,
                user=user,
                role=invite.role,
                invited_by=invite.invited_by,
            )

        invite.status = 'accepted'
        invite.save()

        messages.success(request, f"Welcome to {invite.organization.name}!")
        if request.organization and request.organization == invite.organization:
            return redirect('core:dashboard')
        return redirect(invite.organization.subdomain_url)

    return render(request, 'core/accept_invite.html', {'invite': invite})


# ---------------------------------------------------------------------------
# Super admin
# ---------------------------------------------------------------------------

def superadmin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            raise Http404
        return view_func(request, *args, **kwargs)
    return wrapper


@superadmin_required
def superadmin_dashboard(request):
    orgs = Organization.objects.annotate(
        member_count=Count('members'),
        job_count=Count('jobs'),
        resume_count=Count('resumes'),
    ).order_by('-created_at')

    stats = {
        'Total Orgs': Organization.objects.count(),
        'Active Orgs': Organization.objects.filter(is_active=True).count(),
        'Total Users': OrganizationMember.objects.values('user').distinct().count(),
        'Total Resumes': Resume.objects.count(),
    }
    return render(request, 'core/superadmin/dashboard.html', {'orgs': orgs, 'stats': stats})


@superadmin_required
def superadmin_org_detail(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    members = OrganizationMember.objects.filter(organization=org).select_related('user')
    jobs = Job.objects.filter(organization=org)[:20]
    return render(request, 'core/superadmin/org_detail.html', {
        'org': org, 'members': members, 'jobs': jobs,
    })


@superadmin_required
def superadmin_toggle_org(request, pk):
    if request.method != 'POST':
        return redirect('core:superadmin_dashboard')
    org = get_object_or_404(Organization, pk=pk)
    org.is_active = not org.is_active
    org.save()
    state = 'activated' if org.is_active else 'deactivated'
    messages.success(request, f'Organization "{org.name}" {state}.')
    return redirect('core:superadmin_dashboard')


# ---------------------------------------------------------------------------
# Login with multi-tenant org picker
# ---------------------------------------------------------------------------

@login_required
def org_picker(request):
    """Shown after login when user belongs to multiple orgs."""
    memberships = OrganizationMember.objects.filter(
        user=request.user
    ).select_related('organization')
    count = memberships.count()

    if count == 0:
        return render(request, 'core/no_org.html')

    if count == 1:
        org = memberships.first().organization
        # Only go to dashboard if we are already in this org's context
        # (FORCE_TENANT_SLUG matches, or correct subdomain). Otherwise send
        # the user to the org's own subdomain URL so the middleware can
        # resolve the org — this also prevents a redirect loop when the
        # forced org in dev differs from the user's actual org.
        if request.organization and request.organization.pk == org.pk:
            return redirect('core:dashboard')
        return redirect(org.subdomain_url)

    return render(request, 'core/org_picker.html', {'memberships': memberships})
