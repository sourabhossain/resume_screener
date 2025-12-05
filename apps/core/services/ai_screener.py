"""
AI Resume Screening Engine using LangGraph.
Implements the full screening workflow: Extract → Match → Score → Rank
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, List, Dict, Any, Optional

from django.conf import settings
from langgraph.graph import StateGraph, END

from .llm_client import llm_client

logger = logging.getLogger(__name__)


# Enums for classification
class Tier(str, Enum):
    TOP = "Top"
    MID = "Mid"
    LOW = "Low"


class Recommendation(str, Enum):
    INTERVIEW = "Interview"
    TALENT_POOL = "Talent Pool"
    REJECT = "Reject"


# State definition for LangGraph
class ResumeScreeningState(TypedDict):
    # Inputs
    resume_text: str
    job_description: str
    
    # Extraction results
    candidate_name: str
    skills: List[str]
    experience_years: float
    education: List[str]
    certifications: List[str]
    
    # Matching results
    matched_skills: List[str]
    missing_skills: List[str]
    experience_match_score: float
    education_match_score: float
    
    # Scoring results
    skill_score: float
    experience_score: float
    education_score: float
    certification_score: float
    final_score: float
    
    # Ranking results
    tier: str
    recommendation: str
    reasoning: str
    
    # Error tracking
    error: Optional[str]


# Prompts
EXTRACTION_PROMPT = """Extract information from this resume:

{resume_text}

Return ONLY valid JSON with this exact structure:
{{
    "candidate_name": "Full Name",
    "skills": ["skill1", "skill2", ...],
    "experience_years": 0.0,
    "education": ["degree1", "degree2", ...],
    "certifications": ["cert1", "cert2", ...]
}}

Be thorough in extracting ALL skills mentioned, including technical skills, tools, and frameworks.
Calculate total years of experience from work history.
List all educational qualifications.
List all certifications and courses."""


MATCHING_PROMPT = """Compare this candidate against the job requirements:

JOB REQUIREMENTS:
{job_description}

CANDIDATE PROFILE:
- Name: {candidate_name}
- Skills: {skills}
- Experience: {experience_years} years
- Education: {education}
- Certifications: {certifications}

Return ONLY valid JSON with this exact structure:
{{
    "matched_skills": ["skill1", "skill2", ...],
    "missing_skills": ["skill1", "skill2", ...],
    "experience_match_score": 0.0,
    "education_match_score": 0.0
}}

experience_match_score: 0-100 based on how well experience matches requirements.
education_match_score: 0-100 based on how well education matches requirements."""


REASONING_PROMPT = """Based on this screening analysis, provide a brief recommendation:

Candidate: {candidate_name}
Final Score: {final_score}/100
Tier: {tier}
Matched Skills: {matched_skills}
Missing Skills: {missing_skills}
Experience: {experience_years} years

Provide a 2-3 sentence reasoning for the recommendation.
Be specific about strengths and gaps."""


# Workflow nodes
def extract_node(state: ResumeScreeningState) -> ResumeScreeningState:
    """Extract candidate profile from resume text."""
    try:
        config = settings.AI_SCREENING_CONFIG
        resume_text = state['resume_text'][:config['MAX_RESUME_CHARS']]
        
        prompt = EXTRACTION_PROMPT.format(resume_text=resume_text)
        response = llm_client.invoke_json(prompt, "You are an expert resume parser.")
        
        state['candidate_name'] = response.get('candidate_name', 'Unknown')
        state['skills'] = response.get('skills', [])
        state['experience_years'] = float(response.get('experience_years', 0))
        state['education'] = response.get('education', [])
        state['certifications'] = response.get('certifications', [])
        
        logger.info(f"Extracted profile for: {state['candidate_name']}")
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        state['error'] = str(e)
    
    return state


def match_node(state: ResumeScreeningState) -> ResumeScreeningState:
    """Match candidate profile against job requirements."""
    if state.get('error'):
        return state
    
    try:
        config = settings.AI_SCREENING_CONFIG
        job_desc = state['job_description'][:config['MAX_JOB_DESC_CHARS']]
        
        prompt = MATCHING_PROMPT.format(
            job_description=job_desc,
            candidate_name=state['candidate_name'],
            skills=", ".join(state['skills']),
            experience_years=state['experience_years'],
            education=", ".join(state['education']),
            certifications=", ".join(state['certifications'])
        )
        
        response = llm_client.invoke_json(prompt, "You are an expert HR analyst.")
        
        state['matched_skills'] = response.get('matched_skills', [])
        state['missing_skills'] = response.get('missing_skills', [])
        state['experience_match_score'] = float(response.get('experience_match_score', 0))
        state['education_match_score'] = float(response.get('education_match_score', 0))
        
        logger.info(f"Matched {len(state['matched_skills'])} skills for {state['candidate_name']}")
        
    except Exception as e:
        logger.error(f"Matching failed: {e}")
        state['error'] = str(e)
    
    return state


def score_node(state: ResumeScreeningState) -> ResumeScreeningState:
    """Calculate weighted scores."""
    if state.get('error'):
        return state
    
    try:
        config = settings.AI_SCREENING_CONFIG
        
        # Calculate skill score based on match ratio
        total_skills = len(state['matched_skills']) + len(state['missing_skills'])
        if total_skills > 0:
            state['skill_score'] = (len(state['matched_skills']) / total_skills) * 100
        else:
            state['skill_score'] = 0
        
        # Use LLM scores for experience and education
        state['experience_score'] = state['experience_match_score']
        state['education_score'] = state['education_match_score']
        
        # Certification score (bonus for each cert, max 100)
        state['certification_score'] = min(len(state['certifications']) * 25, 100)
        
        # Calculate weighted final score
        state['final_score'] = (
            state['skill_score'] * config['SKILL_WEIGHT'] +
            state['experience_score'] * config['EXPERIENCE_WEIGHT'] +
            state['education_score'] * config['EDUCATION_WEIGHT'] +
            state['certification_score'] * config['CERTIFICATION_WEIGHT']
        )
        
        logger.info(f"Scored {state['candidate_name']}: {state['final_score']:.1f}/100")
        
    except Exception as e:
        logger.error(f"Scoring failed: {e}")
        state['error'] = str(e)
    
    return state


def rank_node(state: ResumeScreeningState) -> ResumeScreeningState:
    """Assign tier and recommendation based on score."""
    if state.get('error'):
        return state
    
    try:
        config = settings.AI_SCREENING_CONFIG
        score = state['final_score']
        
        # Determine tier
        if score >= config['TOP_TIER_THRESHOLD']:
            state['tier'] = Tier.TOP.value
            state['recommendation'] = Recommendation.INTERVIEW.value
        elif score >= config['MID_TIER_THRESHOLD']:
            state['tier'] = Tier.MID.value
            state['recommendation'] = Recommendation.TALENT_POOL.value
        else:
            state['tier'] = Tier.LOW.value
            state['recommendation'] = Recommendation.REJECT.value
        
        # Generate reasoning
        prompt = REASONING_PROMPT.format(
            candidate_name=state['candidate_name'],
            final_score=state['final_score'],
            tier=state['tier'],
            matched_skills=", ".join(state['matched_skills'][:5]),
            missing_skills=", ".join(state['missing_skills'][:3]),
            experience_years=state['experience_years']
        )
        
        state['reasoning'] = llm_client.invoke_text(prompt, "You are a hiring manager.")
        
        logger.info(f"Ranked {state['candidate_name']}: {state['tier']} ({state['recommendation']})")
        
    except Exception as e:
        logger.error(f"Ranking failed: {e}")
        state['error'] = str(e)
    
    return state


def create_screening_workflow() -> StateGraph:
    """Create the LangGraph screening workflow."""
    workflow = StateGraph(ResumeScreeningState)
    
    # Add nodes
    workflow.add_node("extract", extract_node)
    workflow.add_node("match", match_node)
    workflow.add_node("score", score_node)
    workflow.add_node("rank", rank_node)
    
    # Define edges
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "match")
    workflow.add_edge("match", "score")
    workflow.add_edge("score", "rank")
    workflow.add_edge("rank", END)
    
    return workflow.compile()


# Main screening function
def screen_resume(resume_text: str, job_description: str) -> Dict[str, Any]:
    """
    Screen a resume against a job description.
    
    Args:
        resume_text: Extracted text from resume
        job_description: Job description text
        
    Returns:
        Dictionary with screening results
    """
    if not resume_text or not job_description:
        return {
            'error': 'Resume text and job description are required',
            'final_score': 0,
            'tier': Tier.LOW.value,
            'recommendation': Recommendation.REJECT.value
        }
    
    # Create initial state
    initial_state: ResumeScreeningState = {
        'resume_text': resume_text,
        'job_description': job_description,
        'candidate_name': '',
        'skills': [],
        'experience_years': 0.0,
        'education': [],
        'certifications': [],
        'matched_skills': [],
        'missing_skills': [],
        'experience_match_score': 0.0,
        'education_match_score': 0.0,
        'skill_score': 0.0,
        'experience_score': 0.0,
        'education_score': 0.0,
        'certification_score': 0.0,
        'final_score': 0.0,
        'tier': '',
        'recommendation': '',
        'reasoning': '',
        'error': None
    }
    
    # Run workflow
    workflow = create_screening_workflow()
    result = workflow.invoke(initial_state)
    
    return result
