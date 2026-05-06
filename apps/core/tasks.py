"""
Celery tasks for async resume screening.
"""
import logging
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, soft_time_limit=120, time_limit=150, acks_late=True)
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

    except SoftTimeLimitExceeded:
        logger.error(f"Resume {resume_id} screening timed out after 120s")
        try:
            Resume.objects.filter(id=resume_id).update(screening_status='failed')
        except Exception as update_err:
            logger.warning(f"Could not update status after timeout for resume {resume_id}: {update_err}")
        return {'error': 'timeout', 'resume_id': resume_id}

    except Resume.DoesNotExist:
        logger.error(f"Resume {resume_id} not found")
        return {'error': 'Resume not found'}

    except Exception as e:
        logger.exception(f"Error screening resume {resume_id}: {e}")

        retries_left = self.max_retries - self.request.retries
        if retries_left > 0:
            # Will be retried — keep as pending so UI shows it queued, not failed
            try:
                Resume.objects.filter(id=resume_id).update(screening_status='pending')
            except Exception as update_err:
                logger.warning(f"Could not reset status to pending for resume {resume_id}: {update_err}")
        else:
            # All retries exhausted — mark as permanently failed
            try:
                Resume.objects.filter(id=resume_id).update(screening_status='failed')
            except Exception as update_err:
                logger.warning(f"Could not update status to failed for resume {resume_id}: {update_err}")
            logger.error(f"Resume {resume_id} permanently failed after {self.max_retries} retries")

        raise self.retry(exc=e, countdown=60)


@shared_task
def batch_screen_resumes(job_id: int):
    """
    Screen all pending resumes for a job.

    Args:
        job_id: ID of the Job model instance
    """
    from apps.core.models import Resume

    # Cap at 500 to avoid unbounded memory usage
    resume_ids = list(
        Resume.objects.filter(
            job_id=job_id,
            screening_status='pending',
            is_deleted=False
        ).values_list('id', flat=True)[:500]
    )

    if not resume_ids:
        return {'queued': 0}

    # Bulk update to 'processing' before queuing to prevent duplicate task dispatch
    Resume.objects.filter(id__in=resume_ids).update(screening_status='processing')

    for resume_id in resume_ids:
        screen_resume_task.delay(resume_id)

    return {'queued': len(resume_ids)}
