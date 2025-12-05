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
    from apps.core.services.document_extractor import DocumentExtractor
    from apps.core.services.ai_screener import screen_resume
    
    try:
        resume = Resume.objects.select_related('job').get(id=resume_id)
        
        # Update status to processing
        resume.screening_status = 'processing'
        resume.save(update_fields=['screening_status'])
        
        logger.info(f"Starting screening for resume {resume_id}")
        
        # Extract text from resume file if not already extracted
        if not resume.raw_text and resume.file:
            try:
                resume.raw_text = DocumentExtractor.extract(resume.file.path)
                resume.save(update_fields=['raw_text'])
            except Exception as e:
                logger.error(f"Failed to extract text from resume {resume_id}: {e}")
                resume.screening_status = 'failed'
                resume.save(update_fields=['screening_status'])
                return {'error': str(e)}
        
        if not resume.raw_text:
            logger.error(f"No text content for resume {resume_id}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'error': 'No resume text available'}
        
        # Get job description
        job_description = resume.job.description
        if not job_description:
            logger.error(f"No job description for resume {resume_id}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'error': 'No job description available'}
        
        # Run AI screening
        result = screen_resume(resume.raw_text, job_description)
        
        if result.get('error'):
            logger.error(f"Screening failed for resume {resume_id}: {result['error']}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return result
        
        # Update resume with screening results
        with transaction.atomic():
            resume.candidate_name = result.get('candidate_name', resume.candidate_name)
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
        
        logger.info(f"Completed screening for resume {resume_id}: Score={resume.final_score}, Tier={resume.tier}")
        
        return {
            'resume_id': resume_id,
            'candidate_name': resume.candidate_name,
            'final_score': resume.final_score,
            'tier': resume.tier,
            'recommendation': resume.recommendation
        }
        
    except Resume.DoesNotExist:
        logger.error(f"Resume {resume_id} not found")
        return {'error': 'Resume not found'}
    
    except Exception as e:
        logger.exception(f"Error screening resume {resume_id}: {e}")
        
        # Update status to failed
        try:
            Resume.objects.filter(id=resume_id).update(screening_status='failed')
        except:
            pass
        
        # Retry the task
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
