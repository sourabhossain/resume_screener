"""
Tests for AI Services: ai_screener, llm_client, document_extractor, resume_service.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import os


@pytest.mark.django_db
class TestDocumentExtractor:
    """Tests for DocumentExtractor service."""
    
    def test_extract_from_txt_is_unsupported(self, tmp_path):
        from apps.core.services.document_extractor import DocumentExtractor

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is test resume content.\nSkills: Python, Django")

        with pytest.raises(ValueError, match="Unsupported file type"):
            DocumentExtractor.extract(str(txt_file))

    def test_unsupported_file_type(self, tmp_path):
        """Test that unsupported file types raise ValueError."""
        from apps.core.services.document_extractor import DocumentExtractor
        
        # Create a temp file with unsupported extension
        xyz_file = tmp_path / "test.xyz"
        xyz_file.write_text("some content")
        
        with pytest.raises(ValueError, match="Unsupported file type"):
            DocumentExtractor.extract(str(xyz_file))
    
    def test_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        from apps.core.services.document_extractor import DocumentExtractor
        
        with pytest.raises(FileNotFoundError):
            DocumentExtractor.extract("/nonexistent/file.pdf")
    
    def test_is_supported(self):
        """Test is_supported method. .doc is no longer supported (python-docx is .docx only)."""
        from apps.core.services.document_extractor import DocumentExtractor

        assert DocumentExtractor.is_supported("resume.pdf") is True
        assert DocumentExtractor.is_supported("resume.docx") is True
        assert DocumentExtractor.is_supported("resume.doc") is False
        assert DocumentExtractor.is_supported("resume.txt") is False
        assert DocumentExtractor.is_supported("resume.xyz") is False

    def test_has_enough_text(self):
        """Stray overlay text from an image-only CV is not enough to screen."""
        from apps.core.services.document_extractor import DocumentExtractor

        assert DocumentExtractor.has_enough_text("") is False
        assert DocumentExtractor.has_enough_text(None) is False
        assert DocumentExtractor.has_enough_text("(8th)\n") is False
        assert DocumentExtractor.has_enough_text("x" * 200) is False  # long but one word
        assert DocumentExtractor.has_enough_text("Python developer with Django " * 10) is True

    def test_pdf_with_text_layer_skips_ocr(self, tmp_path):
        """A PDF with a real text layer is not sent to OCR."""
        from apps.core.services.document_extractor import DocumentExtractor

        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        text = "Python developer with Django " * 10
        with patch.object(DocumentExtractor, '_extract_pdf_text_layer', return_value=text), \
             patch.object(DocumentExtractor, '_ocr_pdf') as mock_ocr:
            assert DocumentExtractor.extract(str(pdf)) == text
        mock_ocr.assert_not_called()

    def test_image_only_pdf_falls_back_to_ocr(self, tmp_path):
        """An image-only PDF is read with OCR."""
        from apps.core.services.document_extractor import DocumentExtractor

        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        ocr_text = "MD JESUNUR ALAM JESUN Finance operation associate " * 5
        with patch.object(DocumentExtractor, '_extract_pdf_text_layer', return_value="(8th)\n"), \
             patch.object(DocumentExtractor, '_ocr_pdf', return_value=ocr_text):
            assert DocumentExtractor.extract(str(pdf)) == ocr_text

    def test_ocr_returning_less_keeps_text_layer(self, tmp_path):
        """If OCR reads nothing, the (short) text layer is returned unchanged."""
        from apps.core.services.document_extractor import DocumentExtractor

        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        with patch.object(DocumentExtractor, '_extract_pdf_text_layer', return_value="(8th)\n"), \
             patch.object(DocumentExtractor, '_ocr_pdf', return_value=""):
            assert DocumentExtractor.extract(str(pdf)) == "(8th)\n"

    def test_ocr_sends_rendered_pages_to_vision_llm(self, tmp_path):
        """Pages are rendered to JPEG, capped at OCR_MAX_PAGES, and sent in one call."""
        from pypdf import PdfWriter
        from apps.core.services.document_extractor import DocumentExtractor

        writer = PdfWriter()
        for _ in range(DocumentExtractor.OCR_MAX_PAGES + 2):
            writer.add_blank_page(width=200, height=200)
        pdf = tmp_path / "scanned.pdf"
        with open(pdf, 'wb') as f:
            writer.write(f)

        with patch('apps.core.services.document_extractor.llm_client') as mock_llm:
            mock_llm.invoke_vision.return_value = "OCR text"
            assert DocumentExtractor._ocr_pdf(str(pdf)) == "OCR text"

        images = mock_llm.invoke_vision.call_args.args[1]
        assert len(images) == DocumentExtractor.OCR_MAX_PAGES
        assert all(image.startswith(b'\xff\xd8') for image in images)  # JPEG magic


@pytest.mark.django_db
class TestPromptLoader:
    """Tests for PromptLoader utility."""
    
    def test_load_extraction_prompt(self):
        """Test loading extraction prompt template."""
        from apps.core.services.prompt_loader import get_extraction_prompt
        
        prompt = get_extraction_prompt(resume_text="Sample resume text")
        
        assert "Sample resume text" in prompt
        assert "experience_years" in prompt
    
    def test_load_matching_prompt(self):
        """Test loading matching prompt template."""
        from apps.core.services.prompt_loader import get_matching_prompt
        
        prompt = get_matching_prompt(
            job_description="Python Developer needed",
            candidate_name="John Doe",
            skills="Python, Django",
            experience_years=5.0,
            education="BSc Computer Science",
            certifications="AWS Certified"
        )
        
        assert "Python Developer needed" in prompt
        assert "John Doe" in prompt
    
    def test_load_reasoning_prompt(self):
        """Test loading reasoning prompt template."""
        from apps.core.services.prompt_loader import get_reasoning_prompt
        
        prompt = get_reasoning_prompt(
            candidate_name="Jane Doe",
            final_score=85.0,
            tier="Top",
            matched_skills="Python, Django",
            missing_skills="Kubernetes",
            experience_years=7.0
        )
        
        assert "Jane Doe" in prompt
        assert "85" in prompt


@pytest.mark.django_db  
class TestLLMClient:
    """Tests for LLMClient with mocked OpenAI calls."""
    
    @patch('apps.core.services.llm_client.ChatOpenAI')
    def test_invoke_json_returns_dict(self, mock_chat):
        """Test that invoke_json returns parsed dictionary."""
        # This is a mock test - actual LLM calls are expensive
        pass
    
    @patch('apps.core.services.llm_client.ChatOpenAI')
    def test_invoke_text_returns_string(self, mock_chat):
        """Test that invoke_text returns string."""
        pass

    def test_invoke_vision_sends_images_as_data_urls(self):
        """Images go in one message as base64 JPEG data URLs after the prompt."""
        from django.core.cache import cache
        from apps.core.services.llm_client import llm_client

        cache.clear()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Transcribed text")
        with patch.object(llm_client, '_llm', mock_llm):
            result = llm_client.invoke_vision("Read this", [b'\xff\xd8one', b'\xff\xd8two'])

        assert result == "Transcribed text"
        content = mock_llm.invoke.call_args.args[0][1].content
        assert content[0] == {"type": "text", "text": "Read this"}
        assert [part["type"] for part in content[1:]] == ["image_url", "image_url"]
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.django_db
class TestResumeService:
    """Tests for ResumeService."""
    
    def test_apply_screening_result(self, sample_job, sample_resume):
        """Test applying screening results to resume."""
        from apps.core.services.resume_service import ResumeService
        
        result = {
            'candidate_name': 'Test Candidate',
            'skills': ['Python', 'Django'],
            'education': ['BSc CS'],
            'certifications': ['AWS'],
            'experience_years': 5.0,
            'matched_skills': ['Python'],
            'missing_skills': ['Go'],
            'skill_score': 80.0,
            'experience_score': 90.0,
            'education_score': 85.0,
            'certification_score': 25.0,
            'final_score': 82.5,
            'achievement_score': 88.0,
            'achievements': ['Shipped billing refactor'],
            'tier': 'Top',
            'recommendation': 'Interview',
            'reasoning': 'Strong candidate'
        }
        
        ResumeService.apply_screening_result(sample_resume, result)
        
        sample_resume.refresh_from_db()
        assert sample_resume.skills == ['Python', 'Django']
        assert sample_resume.final_score == 82  # Rounded
        assert sample_resume.tier == 'top'
        assert sample_resume.screening_status == 'completed'
        assert sample_resume.achievements == ['Shipped billing refactor']
        assert sample_resume.achievement_score == 88

    def test_extract_text_rejects_too_little_text(self, sample_resume, tmp_path):
        """Near-empty extraction fails instead of being screened (and scored ~0)."""
        from apps.core.exceptions import DocumentExtractionError
        from apps.core.services.resume_service import ResumeService

        sample_resume.file.name = 'resumes/scanned.pdf'
        with patch('apps.core.services.document_extractor.DocumentExtractor.extract',
                   return_value="(8th)\n"):
            with pytest.raises(DocumentExtractionError, match="Too little text"):
                ResumeService.extract_text(sample_resume)

        sample_resume.refresh_from_db()
        assert sample_resume.raw_text == ''

    def test_process_resume_marks_too_little_text_failed(self, sample_resume):
        """HR sees 'failed' rather than a misleading low score."""
        from apps.core.services.resume_service import ResumeService

        sample_resume.file.name = 'resumes/scanned.pdf'
        with patch('apps.core.services.document_extractor.DocumentExtractor.extract',
                   return_value="(8th)\n"), \
             patch.object(ResumeService, 'run_screening') as mock_screen:
            result = ResumeService.process_resume(sample_resume)

        mock_screen.assert_not_called()
        assert result['success'] is False
        assert result['error_type'] == 'extraction'
        sample_resume.refresh_from_db()
        assert sample_resume.screening_status == 'failed'


@pytest.mark.django_db
class TestExceptions:
    """Tests for custom exceptions."""
    
    def test_document_extraction_error(self):
        """Test DocumentExtractionError."""
        from apps.core.exceptions import DocumentExtractionError
        
        error = DocumentExtractionError("Failed to read", file_path="/path/to/file.pdf")
        assert error.file_path == "/path/to/file.pdf"
        assert "Failed to read" in str(error)
    
    def test_ai_screening_error(self):
        """Test AIScreeningError."""
        from apps.core.exceptions import AIScreeningError
        
        error = AIScreeningError("LLM failed", stage="extraction")
        assert error.stage == "extraction"
        assert "LLM failed" in str(error)
    
    def test_invalid_file_type_error(self):
        """Test InvalidFileTypeError."""
        from apps.core.exceptions import InvalidFileTypeError
        
        error = InvalidFileTypeError("xyz")
        assert error.file_type == "xyz"
        assert "Unsupported file type: xyz" in str(error)
    
    def test_file_too_large_error(self):
        """Test FileTooLargeError."""
        from apps.core.exceptions import FileTooLargeError
        
        error = FileTooLargeError(size=10*1024*1024, max_size=5*1024*1024)
        assert error.size == 10*1024*1024
        assert "exceeds limit" in str(error)
