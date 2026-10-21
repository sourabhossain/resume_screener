"""
End-to-end tests for image-only (scanned) resumes: upload → Celery task (eager) →
text extraction / OCR fallback → screening → status. Only the OpenAI calls are mocked;
PDFs and DOCX files are real and go through pypdf, pypdfium2 and python-docx.
"""
import io
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image, ImageDraw

from apps.core.models import Resume
from apps.core.services.document_extractor import DocumentExtractor
from apps.core.services.llm_client import llm_client

OCR_TEXT = (
    "Jane Doe\nFinance Operations Associate\n"
    "Reconciled monthly bank statements, prepared financial reports, "
    "supported audit preparation and monitored cash flow for three years. "
    "Skills: Excel, reconciliation, reporting, budgeting."
)
TEXT_LAYER = (
    "John Smith Senior Python Developer with seven years of experience building "
    "Django REST APIs, Celery pipelines and PostgreSQL data models for fintech products."
)


def screening_result(name='Screened Candidate'):
    return {
        'candidate_name': name,
        'skills': ['Excel'],
        'education': [],
        'certifications': [],
        'achievements': [],
        'experience_years': 3.0,
        'matched_skills': ['Excel'],
        'missing_skills': [],
        'skill_score': 80.0,
        'experience_score': 75.0,
        'education_score': 60.0,
        'certification_score': 0.0,
        'achievement_score': 50.0,
        'final_score': 72.0,
        'reasoning': 'ok',
    }


def image_only_pdf(width=595, height=842, pages=1):
    """A PDF whose pages are pictures of text, with no text layer (like a Canva/phone export)."""
    images = []
    for _ in range(pages):
        image = Image.new('RGB', (width, height), 'white')
        ImageDraw.Draw(image).text((40, 40), 'Jane Doe - Finance Operations', fill='black')
        images.append(image)
    buffer = io.BytesIO()
    images[0].save(buffer, format='PDF', save_all=True, append_images=images[1:])
    return buffer.getvalue()


def text_pdf(text=TEXT_LAYER):
    """A minimal valid PDF with a real text layer."""
    stream = f"BT /F1 10 Tf 40 800 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def docx_bytes(*paragraphs):
    import docx
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / 'media')


@pytest.fixture
def mock_ocr():
    with patch.object(llm_client, 'invoke_vision', return_value=OCR_TEXT) as mock:
        yield mock


@pytest.fixture
def mock_screen():
    with patch('apps.core.services.ai_screener.screen_resume',
               return_value=screening_result()) as mock:
        yield mock


def upload(client, job, name, content, filename):
    return client.post(
        reverse('core:resume_create', kwargs={'job_pk': job.pk}),
        {'candidate_name': name, 'file': SimpleUploadedFile(filename, content)},
    )


@pytest.mark.django_db
class TestFixtures:
    """The generated files really are what the other tests assume."""

    def test_image_only_pdf_has_no_text_layer(self, tmp_path):
        path = tmp_path / 'scan.pdf'
        path.write_bytes(image_only_pdf())
        assert DocumentExtractor._extract_pdf_text_layer(str(path)).strip() == ''

    def test_text_pdf_has_text_layer(self, tmp_path):
        path = tmp_path / 'cv.pdf'
        path.write_bytes(text_pdf())
        assert DocumentExtractor.has_enough_text(DocumentExtractor._extract_pdf_text_layer(str(path)))


@pytest.mark.django_db
class TestUploadFlow:

    def test_scanned_pdf_is_read_with_ocr_and_screened(self, authenticated_client, sample_job,
                                                       mock_ocr, mock_screen):
        response = upload(authenticated_client, sample_job, 'Jane Doe', image_only_pdf(), 'scan.pdf')

        assert response.status_code == 302
        resume = Resume.objects.get(candidate_name='Screened Candidate')
        assert resume.screening_status == 'completed'
        assert resume.raw_text == OCR_TEXT
        assert resume.final_score == 72
        mock_ocr.assert_called_once()
        images = mock_ocr.call_args.args[1]
        assert len(images) == 1 and images[0].startswith(b'\xff\xd8')
        assert mock_screen.call_args.args[0] == OCR_TEXT

    def test_text_pdf_skips_ocr(self, authenticated_client, sample_job, mock_ocr, mock_screen):
        upload(authenticated_client, sample_job, 'John Smith', text_pdf(), 'cv.pdf')

        resume = Resume.objects.get()
        assert resume.screening_status == 'completed'
        assert 'Senior Python Developer' in resume.raw_text
        mock_ocr.assert_not_called()

    def test_unreadable_scan_fails_without_screening(self, authenticated_client, sample_job, mock_screen):
        with patch.object(llm_client, 'invoke_vision', return_value=''):
            upload(authenticated_client, sample_job, 'Blank Scan', image_only_pdf(), 'scan.pdf')

        resume = Resume.objects.get(candidate_name='Blank Scan')
        assert resume.screening_status == 'failed'
        assert resume.raw_text == ''
        assert resume.final_score is None
        mock_screen.assert_not_called()

    def test_ocr_api_error_fails_cleanly(self, authenticated_client, sample_job, mock_screen):
        with patch.object(llm_client, 'invoke_vision', side_effect=RuntimeError('LLM not initialized')):
            response = upload(authenticated_client, sample_job, 'Err Scan', image_only_pdf(), 'scan.pdf')

        assert response.status_code == 302
        assert Resume.objects.get(candidate_name='Err Scan').screening_status == 'failed'
        mock_screen.assert_not_called()

    def test_nearly_empty_docx_fails_without_ocr(self, authenticated_client, sample_job,
                                                 mock_ocr, mock_screen):
        upload(authenticated_client, sample_job, 'Short Docx', docx_bytes('Jane Doe'), 'cv.docx')

        assert Resume.objects.get(candidate_name='Short Docx').screening_status == 'failed'
        mock_ocr.assert_not_called()
        mock_screen.assert_not_called()

    def test_full_docx_is_screened(self, authenticated_client, sample_job, mock_ocr, mock_screen):
        upload(authenticated_client, sample_job, 'Docx', docx_bytes(TEXT_LAYER, 'Skills: Python'), 'cv.docx')

        assert Resume.objects.get().screening_status == 'completed'
        mock_ocr.assert_not_called()

    def test_corrupt_pdf_fails_cleanly(self, authenticated_client, sample_job, mock_ocr, mock_screen):
        upload(authenticated_client, sample_job, 'Corrupt', b'%PDF-1.4 not really a pdf', 'bad.pdf')

        assert Resume.objects.get(candidate_name='Corrupt').screening_status == 'failed'
        mock_screen.assert_not_called()

    def test_encrypted_pdf_fails_cleanly(self, authenticated_client, sample_job, mock_ocr, mock_screen):
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(text_pdf())))
        writer.encrypt(user_password='secret')
        buffer = io.BytesIO()
        writer.write(buffer)

        upload(authenticated_client, sample_job, 'Locked', buffer.getvalue(), 'locked.pdf')

        assert Resume.objects.get(candidate_name='Locked').screening_status == 'failed'
        mock_screen.assert_not_called()

    def test_bulk_upload_mixed_files(self, authenticated_client, sample_job, mock_ocr, mock_screen):
        response = authenticated_client.post(
            reverse('core:resume_bulk_create', kwargs={'job_pk': sample_job.pk}),
            {'files': [
                SimpleUploadedFile('text_cv.pdf', text_pdf()),
                SimpleUploadedFile('scanned_cv.pdf', image_only_pdf(pages=2)),
            ]},
        )

        assert response.status_code == 302
        resumes = Resume.objects.all()
        assert resumes.count() == 2
        assert {r.screening_status for r in resumes} == {'completed'}
        mock_ocr.assert_called_once()  # only the scanned one
        assert len(mock_ocr.call_args.args[1]) == 2


@pytest.mark.django_db
class TestRescreenAndEdit:

    def _resume_with_file(self, job, content, raw_text):
        resume = Resume(job=job, candidate_name='Old', raw_text=raw_text, screening_status='completed')
        resume.file.save('old_scan.pdf', SimpleUploadedFile('old_scan.pdf', content), save=True)
        return resume

    def test_rescreen_reextracts_stale_short_text(self, authenticated_client, sample_job,
                                                  mock_ocr, mock_screen):
        """Resumes saved before this fix with raw_text like "(8th)" recover on rescreen."""
        resume = self._resume_with_file(sample_job, image_only_pdf(), '(8th)\n')

        authenticated_client.post(reverse('core:resume_rescreen', kwargs={'pk': resume.pk}))

        resume.refresh_from_db()
        assert resume.screening_status == 'completed'
        assert resume.raw_text == OCR_TEXT
        assert mock_screen.call_args.args[0] == OCR_TEXT

    def test_rescreen_reuses_good_cached_text(self, authenticated_client, sample_job,
                                              mock_ocr, mock_screen):
        resume = self._resume_with_file(sample_job, image_only_pdf(), OCR_TEXT)

        with patch.object(DocumentExtractor, 'extract') as mock_extract:
            authenticated_client.post(reverse('core:resume_rescreen', kwargs={'pk': resume.pk}))

        mock_extract.assert_not_called()
        mock_ocr.assert_not_called()
        resume.refresh_from_db()
        assert resume.screening_status == 'completed'

    def test_replacing_file_clears_cached_text(self, authenticated_client, sample_job):
        resume = self._resume_with_file(sample_job, image_only_pdf(), OCR_TEXT)

        authenticated_client.post(
            reverse('core:resume_edit', kwargs={'pk': resume.pk}),
            {'candidate_name': 'Old', 'file': SimpleUploadedFile('new_cv.pdf', text_pdf())},
        )

        resume.refresh_from_db()
        assert resume.raw_text == ''
        assert resume.file_name == 'new_cv.pdf'

    def test_editing_without_new_file_keeps_cached_text(self, authenticated_client, sample_job):
        resume = self._resume_with_file(sample_job, image_only_pdf(), OCR_TEXT)

        authenticated_client.post(
            reverse('core:resume_edit', kwargs={'pk': resume.pk}),
            {'candidate_name': 'Renamed'},
        )

        resume.refresh_from_db()
        assert resume.candidate_name == 'Renamed'
        assert resume.raw_text == OCR_TEXT


@pytest.mark.django_db
class TestOcrInternals:

    def test_oversized_page_is_capped(self, tmp_path):
        path = tmp_path / 'poster.pdf'
        path.write_bytes(image_only_pdf(width=3000, height=6000))

        images = DocumentExtractor._render_pdf_pages(str(path))

        width, height = Image.open(io.BytesIO(images[0])).size
        assert max(width, height) <= DocumentExtractor.OCR_MAX_IMAGE_SIDE

    def test_a4_page_renders_at_full_scale(self, tmp_path):
        path = tmp_path / 'a4.pdf'
        path.write_bytes(image_only_pdf())

        images = DocumentExtractor._render_pdf_pages(str(path))

        width, _ = Image.open(io.BytesIO(images[0])).size
        assert width == pytest.approx(595 * DocumentExtractor.OCR_RENDER_SCALE, abs=2)

    def test_vision_result_is_cached(self):
        from unittest.mock import MagicMock
        from django.core.cache import cache

        cache.clear()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='Text')
        with patch.object(llm_client, '_llm', mock_llm):
            assert llm_client.invoke_vision('Read', [b'\xff\xd8a']) == 'Text'
            assert llm_client.invoke_vision('Read', [b'\xff\xd8a']) == 'Text'
            llm_client.invoke_vision('Read', [b'\xff\xd8b'])

        assert mock_llm.invoke.call_count == 2  # different image → new call

    def test_vision_content_blocks_are_joined(self):
        from unittest.mock import MagicMock
        from django.core.cache import cache

        cache.clear()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=[{'type': 'text', 'text': 'Hello '}, {'type': 'text', 'text': 'world'}]
        )
        with patch.object(llm_client, '_llm', mock_llm):
            assert llm_client.invoke_vision('Read', [b'\xff\xd8c']) == 'Hello world'
