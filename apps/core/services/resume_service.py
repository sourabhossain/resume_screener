"""
Resume Service - Centralized resume processing logic.
Eliminates code duplication across views and tasks.
"""
import logging
from typing import Dict, Any, Optional

from django.db import transaction

from apps.core.exceptions import (
    DocumentExtractionError,
    AIScreeningError,
    MissingJobDescriptionError
)
from apps.core.types import ScreeningResult

logger = logging.getLogger(__name__)


class ResumeService:
    """
    Service class for resume processing operations.
    Centralizes screening logic to avoid code duplication.
    """
    
    @staticmethod
    def extract_text(resume) -> str:
        """
        Extract text from resume file.
        
        Args:
            resume: Resume model instance
            
        Returns:
            Extracted text content
            
        Raises:
            DocumentExtractionError: If extraction fails
        """
        from apps.core.services.document_extractor import DocumentExtractor
        
        if resume.raw_text:
            return resume.raw_text
        
        if not resume.file:
            raise DocumentExtractionError("No file attached to resume")
        
        try:
            text = DocumentExtractor.extract(resume.file.path)
            resume.raw_text = text
            resume.save(update_fields=['raw_text'])
            return text
        except Exception as e:
            raise DocumentExtractionError(str(e), file_path=resume.file.path)
    
    @staticmethod
    def run_screening(resume) -> ScreeningResult:
        """
        Run AI screening on a resume.
        
        Args:
            resume: Resume model instance with raw_text
            
        Returns:
            ScreeningResult dictionary
            
        Raises:
            AIScreeningError: If screening fails
            MissingJobDescriptionError: If job has no description
        """
        from apps.core.services.ai_screener import screen_resume
        
        if not resume.job.description:
            raise MissingJobDescriptionError(resume.job.id)
        
        if not resume.raw_text:
            raise AIScreeningError("No resume text available", stage="extraction")
        
        result = screen_resume(resume.raw_text, resume.job.description)
        
        if result.get('error'):
            raise AIScreeningError(result['error'], stage="screening")
        
        return result
    
    @staticmethod
    def apply_screening_result(resume, result: ScreeningResult) -> None:
        """
        Apply AI screening result to resume model and save.
        
        Args:
            resume: Resume model instance
            result: ScreeningResult dictionary from AI screening
        """
        with transaction.atomic():
            # Extracted data
            resume.candidate_name = result.get('candidate_name', resume.candidate_name)
            resume.skills = result.get('skills', [])
            resume.education = result.get('education', [])
            resume.certifications = result.get('certifications', [])
            resume.experience_years = round(result.get('experience_years', 0), 1)
            
            # Matching data
            resume.matched_skills = result.get('matched_skills', [])
            resume.missing_skills = result.get('missing_skills', [])
            
            # Scores (rounded for clean display)
            resume.skills_score = round(result.get('skill_score', 0))
            resume.experience_score = round(result.get('experience_score', 0))
            resume.education_score = round(result.get('education_score', 0))
            resume.certification_score = round(result.get('certification_score', 0))
            resume.final_score = round(result.get('final_score', 0))
            
            # Tier and recommendation
            resume.tier = result.get('tier', '').lower()
            resume.recommendation = result.get('recommendation', '').lower().replace(' ', '_')
            resume.reasoning = result.get('reasoning', '')
            
            # Update status
            resume.screening_status = 'completed'
            resume.save()
    
    @classmethod
    def process_resume(cls, resume) -> Dict[str, Any]:
        """
        Complete resume processing: extract text, run screening, apply results.
        
        Args:
            resume: Resume model instance
            
        Returns:
            Dictionary with processing results
        """
        try:
            # Update status
            resume.screening_status = 'processing'
            resume.save(update_fields=['screening_status'])
            
            # Extract text
            cls.extract_text(resume)
            
            # Run AI screening
            result = cls.run_screening(resume)
            
            # Apply results
            cls.apply_screening_result(resume, result)
            
            logger.info(f"Completed processing resume {resume.id}: Score={resume.final_score}")
            
            return {
                'success': True,
                'resume_id': resume.id,
                'candidate_name': resume.candidate_name,
                'final_score': resume.final_score,
                'tier': resume.tier,
                'recommendation': resume.recommendation
            }
            
        except DocumentExtractionError as e:
            logger.error(f"Document extraction failed for resume {resume.id}: {e}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'success': False, 'error': str(e), 'error_type': 'extraction'}
            
        except AIScreeningError as e:
            logger.error(f"AI screening failed for resume {resume.id}: {e}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'success': False, 'error': str(e), 'error_type': 'screening'}
            
        except MissingJobDescriptionError as e:
            logger.error(f"Missing job description for resume {resume.id}: {e}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'success': False, 'error': str(e), 'error_type': 'job_description'}
            
        except Exception as e:
            logger.exception(f"Unexpected error processing resume {resume.id}: {e}")
            resume.screening_status = 'failed'
            resume.save(update_fields=['screening_status'])
            return {'success': False, 'error': str(e), 'error_type': 'unknown'}


# Convenience function for sync processing
def process_resume_sync(resume) -> Dict[str, Any]:
    """Synchronously process a resume through AI screening."""
    return ResumeService.process_resume(resume)
