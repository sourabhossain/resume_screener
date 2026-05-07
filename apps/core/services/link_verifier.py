"""
Link Verifier — compares crawled page content against CV claims using LLM.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any

from apps.core.services.link_crawler import LinkCrawler, CrawlResult
from apps.core.services.link_extractor import LinkExtractor, LinkType

logger = logging.getLogger(__name__)


class LinkVerifier:

    # Verification prompt for LLM
    VERIFY_PROMPT = """You are verifying a job candidate's online presence against their CV claims.

<cv_context>
{cv_excerpt}
</cv_context>

<page_url>{url}</page_url>
<page_type>{link_type}</page_type>
<page_content>
{page_content}
</page_content>

Analyze this page and determine:
1. Does this page belong to the candidate? (name match, handle match)
2. What can you verify from this page? (skills, experience, projects, activity)
3. Are there any discrepancies with the CV claims?

Return ONLY valid JSON:
{{
    "belongs_to_candidate": true,
    "verified_claims": ["claim1", "claim2"],
    "discrepancies": ["discrepancy1", "discrepancy2"],
    "additional_insights": ["insight1", "insight2"],
    "confidence": 0.0
}}

confidence: 0.0-1.0 (how confident you are in this verification)
If page is inaccessible or irrelevant, return belongs_to_candidate: false with empty arrays.
"""

    @classmethod
    def verify_resume(cls, resume) -> dict[str, Any]:
        """
        Main entry point — extract links, crawl, verify.
        Returns verification results dict.
        """
        try:
            # Extract links from CV text
            if not resume.raw_text:
                return cls._skip_result("No CV text available")

            links = LinkExtractor.extract(resume.raw_text)
            if not links:
                return cls._skip_result("No verifiable links found in CV")

            # Store extracted links
            resume.extracted_links = [
                {'url': l.url, 'type': l.link_type, 'context': l.raw_text}
                for l in links
            ]
            resume.save(update_fields=['extracted_links'])

            # Crawl all links
            urls = [l.url for l in links]
            crawl_results = asyncio.run(LinkCrawler.crawl_many(urls))

            # Build a map: url → crawl result
            crawl_map = {r.url: r for r in crawl_results}

            # Verify each link with LLM
            from apps.core.services.llm_client import LLMClient
            llm = LLMClient()

            verification_details = []
            all_verified_claims = []
            all_discrepancies = []

            for link in links:
                crawl_result = crawl_map.get(link.url)
                if not crawl_result or not crawl_result.success:
                    verification_details.append({
                        'url': link.url,
                        'type': link.link_type,
                        'status': 'unreachable',
                        'verified_claims': [],
                        'discrepancies': [],
                        'additional_insights': [],
                        'confidence': 0.0
                    })
                    continue

                # Truncate content for LLM
                page_content = cls._clean_html(crawl_result.content)[:3000]

                prompt = cls.VERIFY_PROMPT.format(
                    cv_excerpt=resume.raw_text[:1000],
                    url=link.url,
                    link_type=link.link_type,
                    page_content=page_content
                )

                try:
                    result = llm.invoke_json(prompt)
                    verification_details.append({
                        'url': link.url,
                        'type': link.link_type,
                        'title': crawl_result.title,
                        'status': 'verified' if result.get('belongs_to_candidate') else 'not_matched',
                        'verified_claims': result.get('verified_claims', []),
                        'discrepancies': result.get('discrepancies', []),
                        'additional_insights': result.get('additional_insights', []),
                        'confidence': result.get('confidence', 0.0)
                    })
                    all_verified_claims.extend(result.get('verified_claims', []))
                    all_discrepancies.extend(result.get('discrepancies', []))
                except Exception as e:
                    logger.warning(f"LLM verification failed for {link.url}: {e}")
                    verification_details.append({
                        'url': link.url,
                        'type': link.link_type,
                        'status': 'error',
                        'error': str(e),
                        'verified_claims': [],
                        'discrepancies': [],
                        'additional_insights': [],
                        'confidence': 0.0
                    })

            # Calculate overall verification score
            verification_score = cls._calculate_score(verification_details)

            return {
                'status': 'completed',
                'links_found': len(links),
                'links_verified': sum(1 for d in verification_details if d['status'] == 'verified'),
                'verification_score': verification_score,
                'verified_claims': all_verified_claims,
                'discrepancies': all_discrepancies,
                'details': verification_details,
                'verified_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.exception(f"Link verification failed for resume {resume.id}: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'links_found': 0,
                'links_verified': 0,
                'verification_score': None,
                'verified_claims': [],
                'discrepancies': [],
                'details': []
            }

    @classmethod
    def _calculate_score(cls, details: list) -> float:
        """
        Score based on:
        - Links successfully verified (belong to candidate)
        - Claims verified vs discrepancies found
        - Confidence levels
        """
        if not details:
            return 0.0

        verified = [d for d in details if d['status'] == 'verified']
        if not verified:
            return 0.0

        total_claims = sum(len(d['verified_claims']) for d in verified)
        total_discrepancies = sum(len(d['discrepancies']) for d in verified)
        avg_confidence = sum(d['confidence'] for d in verified) / len(verified)

        if total_claims + total_discrepancies == 0:
            base_score = 50.0
        else:
            claim_ratio = total_claims / (total_claims + total_discrepancies)
            base_score = claim_ratio * 100

        # Weight by confidence
        final_score = base_score * avg_confidence + base_score * (1 - avg_confidence) * 0.5
        return round(min(final_score, 100.0), 1)

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strip HTML tags, keep readable text."""
        import re
        # Remove script and style blocks
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all tags
        html = re.sub(r'<[^>]+>', ' ', html)
        # Normalize whitespace
        html = re.sub(r'\s+', ' ', html).strip()
        return html

    @staticmethod
    def _skip_result(reason: str) -> dict:
        return {
            'status': 'skipped',
            'reason': reason,
            'links_found': 0,
            'links_verified': 0,
            'verification_score': None,
            'verified_claims': [],
            'discrepancies': [],
            'details': []
        }
