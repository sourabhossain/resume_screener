"""
Celery tasks for async resume screening.
"""
import logging
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def screen_resume_task(self, resume_id: int):
    """
    Async task to screen a resume using AI.
    
    Args:
        resume_id: ID of the Resume model instance
    """
    from apps.core.models import Resume
    from apps.core.services.resume_service import ResumeService
    
    try:
        resume = Resume.objects.select_related('job').get(id=resume_id)
        logger.info(f"Starting screening for resume {resume_id}")
        
        result = ResumeService.process_resume(resume)
        
        if result.get('success'):
            logger.info(f"Completed screening for resume {resume_id}: Score={result.get('final_score')}, Tier={result.get('tier')}")
            return result
        else:
            logger.error(f"Screening failed for resume {resume_id}: {result.get('error')}")
            return result
        
    except Resume.DoesNotExist:
        logger.error(f"Resume {resume_id} not found")
        return {'error': 'Resume not found'}
    
    except Exception as e:
        logger.exception(f"Error screening resume {resume_id}: {e}")
        
        try:
            from apps.core.models import Resume
            Resume.objects.filter(id=resume_id).update(screening_status='failed')
        except:
            pass
        
        raise self.retry(exc=e, countdown=60)


@shared_task
def batch_screen_resumes(job_id: int):
    """
    Screen all pending resumes for a job.
    
    Args:
        job_id: ID of the Job model instance
    """
    from apps.core.models import Resume
    
    pending_resumes = Resume.objects.filter(
        job_id=job_id,
        screening_status='pending',
        is_deleted=False
    ).values_list('id', flat=True)
    
    for resume_id in pending_resumes:
        screen_resume_task.delay(resume_id)
    
    return {'queued': len(pending_resumes)}
