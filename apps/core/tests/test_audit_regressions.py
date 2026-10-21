"""
Regression tests for bugs found in the full-system audit (each test failed before its fix).
"""
import asyncio
import functools
import io
from unittest.mock import patch

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.models import Resume

PDF = b'%PDF-1.4 minimal'


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / 'media')


@pytest.fixture
def active_job(sample_job):
    sample_job.status = 'active'
    sample_job.save()
    return sample_job


@pytest.fixture
def no_task():
    with patch('apps.core.tasks.screen_resume_task.delay') as mock:
        yield mock


@pytest.mark.django_db
class TestUploadForms:

    def test_resume_without_file_is_rejected(self, authenticated_client, active_job, no_task):
        response = authenticated_client.post(
            reverse('core:resume_create', kwargs={'job_pk': active_job.pk}),
            {'candidate_name': 'No File'},
        )
        assert response.status_code == 200
        assert not Resume.objects.filter(candidate_name='No File').exists()
        no_task.assert_not_called()

    def _resume(self, job):
        resume = Resume(job=job, candidate_name='Jane', file_name='jane_cv.pdf', file_type='pdf',
                        raw_text='cached text')
        resume.file.save('jane_cv.pdf', SimpleUploadedFile('jane_cv.pdf', PDF), save=True)
        return resume

    def test_edit_without_new_file_keeps_original_file_name(self, authenticated_client, active_job):
        resume = self._resume(active_job)
        assert resume.file.name != 'jane_cv.pdf'  # storage path, e.g. resumes/jane_cv.pdf

        response = authenticated_client.post(
            reverse('core:resume_edit', kwargs={'pk': resume.pk}),
            {'candidate_name': 'Jane Doe', 'final_score': '70'},
        )

        assert response.status_code == 302
        resume.refresh_from_db()
        assert resume.file_name == 'jane_cv.pdf'
        assert resume.raw_text == 'cached text'

    def test_edit_without_new_file_does_not_reopen_stored_file(self, authenticated_client, active_job):
        """A stored file that left disk must not break editing scores."""
        import os
        resume = self._resume(active_job)
        os.remove(resume.file.path)

        response = authenticated_client.post(
            reverse('core:resume_edit', kwargs={'pk': resume.pk}),
            {'candidate_name': 'Jane Doe', 'final_score': '70'},
        )

        assert response.status_code == 302


@pytest.mark.django_db
class TestProtectedMedia:

    def test_directory_path_is_404_not_500(self, authenticated_client, settings, tmp_path):
        os_dir = tmp_path / 'media' / 'resumes'
        os_dir.mkdir(parents=True)
        response = authenticated_client.get('/media/resumes/')
        assert response.status_code == 404


@pytest.mark.django_db
class TestResumeAPIUpload:

    def _post(self, client, **data):
        return client.post('/api/resumes/', data, format='multipart')

    def test_upload_creates_resume_and_queues_screening(self, authenticated_client, active_job, no_task):
        response = self._post(authenticated_client, candidate_name='API Jane', job=active_job.pk,
                              file=SimpleUploadedFile('api_cv.pdf', PDF))
        assert response.status_code == 201, response.content
        resume = Resume.objects.get(candidate_name='API Jane')
        assert resume.job == active_job
        assert resume.file_name == 'api_cv.pdf'
        assert resume.file_type == 'pdf'
        assert resume.screening_status == 'processing'
        no_task.assert_called_once_with(resume.id)

    @pytest.mark.parametrize('filename,content', [
        ('notes.txt', b'hello'),
        ('fake.pdf', b'not a pdf'),
        ('big.pdf', b'%PDF' + b'0' * (5 * 1024 * 1024 + 1)),
    ], ids=['wrong-type', 'wrong-content', 'too-large'])
    def test_upload_rejects_invalid_files(self, authenticated_client, active_job, no_task, filename, content):
        response = self._post(authenticated_client, candidate_name='Bad', job=active_job.pk,
                              file=SimpleUploadedFile(filename, content))
        assert response.status_code == 400
        assert 'file' in response.json()
        no_task.assert_not_called()

    def test_upload_requires_file(self, authenticated_client, active_job, no_task):
        response = self._post(authenticated_client, candidate_name='No File', job=active_job.pk)
        assert response.status_code == 400
        assert 'file' in response.json()

    def test_upload_requires_active_job(self, authenticated_client, sample_job, no_task):
        sample_job.status = 'closed'
        sample_job.save()
        response = self._post(authenticated_client, candidate_name='Late', job=sample_job.pk,
                              file=SimpleUploadedFile('cv.pdf', PDF))
        assert response.status_code == 400
        assert 'job' in response.json()

    def test_non_numeric_job_filter_is_400(self, authenticated_client):
        response = authenticated_client.get('/api/resumes/?job=abc')
        assert response.status_code == 400


@pytest.mark.django_db
class TestScreeningRobustness:

    def test_null_values_from_llm_do_not_fail_screening(self):
        from apps.core.services import ai_screener
        replies = iter([
            {'job_type': 'sales_marketing'},
            {'candidate_name': None, 'skills': None, 'experience_years': None,
             'education': [{'degree': 'BBA'}], 'certifications': None, 'achievements': 'Top seller'},
            {'matched_skills': None, 'missing_skills': ['CRM'], 'experience_match_score': None,
             'education_match_score': '70', 'achievement_score': None},
        ])
        with patch.object(ai_screener.llm_client, 'invoke_json', side_effect=lambda *a, **k: next(replies)), \
             patch.object(ai_screener.llm_client, 'invoke_text', return_value='ok'):
            result = ai_screener.screen_resume('Fresh graduate ' * 20, 'Sales role')

        assert result['error'] is None
        assert result['experience_years'] == 0.0
        assert result['achievements'] == ['Top seller']
        assert result['education_score'] == 70.0

    def test_unknown_ai_name_keeps_hr_entered_name(self, sample_resume):
        from apps.core.services.resume_service import ResumeService
        ResumeService.apply_screening_result(sample_resume, {'candidate_name': 'Unknown', 'final_score': 50})
        sample_resume.refresh_from_db()
        assert sample_resume.candidate_name == 'John Doe'

    def test_long_ai_name_is_truncated(self, sample_resume):
        from apps.core.services.resume_service import ResumeService
        ResumeService.apply_screening_result(sample_resume, {'candidate_name': 'A' * 300, 'final_score': 50})
        sample_resume.refresh_from_db()
        assert len(sample_resume.candidate_name) == 255

    def test_two_page_resume_is_not_cut_at_4000_chars(self, settings):
        assert settings.AI_SCREENING_CONFIG['MAX_RESUME_CHARS'] >= 8000


class TestLinkExtraction:

    def test_email_addresses_are_not_links(self):
        from apps.core.services.link_extractor import LinkExtractor
        text = 'Reference: md.monir@dgepay.net | Email: jane.doe@company.co.uk'
        assert LinkExtractor.extract(text) == []

    def test_real_links_still_found(self):
        from apps.core.services.link_extractor import LinkExtractor
        text = ('GitHub: github.com/octocat, site https://janedoe.dev/work and www.portfolio.io. '
                'Contact jane@janedoe.dev')
        urls = [link.url for link in LinkExtractor.extract(text)]
        assert urls == ['https://github.com/octocat', 'https://janedoe.dev/work', 'https://www.portfolio.io']

    def test_confidence_from_llm_is_coerced(self):
        from apps.core.services.link_verifier import LinkVerifier
        assert LinkVerifier._as_confidence(None) == 0.0
        assert LinkVerifier._as_confidence('0.7') == 0.7
        assert LinkVerifier._as_confidence(5) == 1.0


class TestCrawlerRedirects:

    def _crawl(self, handler, url):
        from apps.core.services import link_crawler
        client = functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler))
        with patch.object(link_crawler.httpx, 'AsyncClient', client):
            return asyncio.run(link_crawler.LinkCrawler._crawl_with_httpx(url))

    def test_redirect_to_metadata_ip_is_blocked(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://169.254.169.254/latest/meta-data/'})

        result = self._crawl(handler, 'http://93.184.215.14/profile')

        assert result.success is False
        assert 'blocked redirect' in result.error
        assert seen == ['http://93.184.215.14/profile']  # metadata URL never requested

    def test_safe_redirect_is_followed(self):
        def handler(request):
            if request.url.path == '/old':
                return httpx.Response(301, headers={'location': '/new'})
            return httpx.Response(200, text='<title>Jane</title>hello')

        result = self._crawl(handler, 'http://93.184.215.14/old')

        assert result.success is True
        assert result.title == 'Jane'

    def test_redirect_loop_stops(self):
        def handler(request):
            return httpx.Response(302, headers={'location': '/again'})

        result = self._crawl(handler, 'http://93.184.215.14/start')

        assert result.success is False
        assert result.error == 'too many redirects'
