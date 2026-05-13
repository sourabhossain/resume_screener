"""
URL patterns for the core app.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Public
    path('', views.landing, name='landing'),
    path('health/', views.health_check, name='health_check'),
    path('register/', views.org_register, name='org_register'),
    path('invite/<str:token>/', views.accept_invite, name='accept_invite'),

    # Dashboard (requires org)
    path('dashboard/', views.dashboard, name='dashboard'),

    # Job URLs
    path('jobs/', views.job_list, name='job_list'),
    path('jobs/create/', views.job_create, name='job_create'),
    path('jobs/<int:pk>/', views.job_detail, name='job_detail'),
    path('jobs/<int:pk>/edit/', views.job_edit, name='job_edit'),
    path('jobs/<int:pk>/delete/', views.job_delete, name='job_delete'),

    # Resume URLs
    path('jobs/<int:job_pk>/resumes/add/', views.resume_create, name='resume_create'),
    path('jobs/<int:job_pk>/resumes/bulk/', views.resume_bulk_create, name='resume_bulk_create'),
    path('resumes/<int:pk>/', views.resume_detail, name='resume_detail'),
    path('resumes/<int:pk>/edit/', views.resume_edit, name='resume_edit'),
    path('resumes/<int:pk>/delete/', views.resume_delete, name='resume_delete'),
    path('resumes/<int:pk>/rescreen/', views.resume_rescreen, name='resume_rescreen'),
    path('resumes/<int:pk>/status/', views.resume_status_fragment, name='resume_status_fragment'),
    path('resumes/<int:pk>/row/', views.resume_row_fragment, name='resume_row_fragment'),

    # Org settings (admin only)
    path('settings/', views.org_settings, name='org_settings'),
    path('settings/members/', views.org_members, name='org_members'),

    # Org picker (multi-org users)
    path('pick-org/', views.org_picker, name='org_picker'),

    # Super admin
    path('superadmin/', views.superadmin_dashboard, name='superadmin_dashboard'),
    path('superadmin/<int:pk>/', views.superadmin_org_detail, name='superadmin_org_detail'),
    path('superadmin/<int:pk>/toggle/', views.superadmin_toggle_org, name='superadmin_toggle_org'),
]
