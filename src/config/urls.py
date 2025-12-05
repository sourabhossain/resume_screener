"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Job URLs
    path('jobs/', views.job_list, name='job_list'),
    path('jobs/create/', views.job_create, name='job_create'),
    path('jobs/<int:pk>/', views.job_detail, name='job_detail'),
    path('jobs/<int:pk>/edit/', views.job_edit, name='job_edit'),
    path('jobs/<int:pk>/delete/', views.job_delete, name='job_delete'),
    
    # Resume URLs
    path('jobs/<int:job_pk>/resumes/add/', views.resume_create, name='resume_create'),
    path('resumes/<int:pk>/', views.resume_detail, name='resume_detail'),
    path('resumes/<int:pk>/edit/', views.resume_edit, name='resume_edit'),
    path('resumes/<int:pk>/delete/', views.resume_delete, name='resume_delete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)