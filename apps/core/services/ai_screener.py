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
from .prompt_loader import get_extraction_prompt, get_matching_prompt, get_reasoning_prompt

logger = logging.getLogger(__name__)



class Tier(str, Enum):
    TOP = "Top"
    MID = "Mid"
    LOW = "Low"


class Recommendation(str, Enum):
    INTERVIEW = "Interview"
    TALENT_POOL = "Talent Pool"
    REJECT = "Reject"


class ResumeScreeningState(TypedDict):
    resume_text: str
    job_description: str
    

    candidate_name: str
    skills: List[str]
    experience_years: float
    education: List[str]
    certifications: List[str]
    

    matched_skills: List[str]
    missing_skills: List[str]
    experience_match_score: float
    education_match_score: float
    

    skill_score: float
    experience_score: float
    education_score: float
    certification_score: float
    final_score: float
    

    tier: str
    recommendation: str
    reasoning: str
    

    error: Optional[str]



def extract_node(state: ResumeScreeningState) -> ResumeScreeningState:
    """Extract candidate profile from resume text."""
    try:
        config = settings.AI_SCREENING_CONFIG
        resume_text = state['resume_text'][:config['MAX_RESUME_CHARS']]
        
        prompt = get_extraction_prompt(resume_text=resume_text)
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
        
        prompt = get_matching_prompt(
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
        

        total_skills = len(state['matched_skills']) + len(state['missing_skills'])
        if total_skills > 0:
            state['skill_score'] = (len(state['matched_skills']) / total_skills) * 100
        else:
            state['skill_score'] = 0
        

        state['experience_score'] = state['experience_match_score']
        state['education_score'] = state['education_match_score']
        

        state['certification_score'] = min(len(state['certifications']) * 25, 100)
        

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
        

        if score >= config['TOP_TIER_THRESHOLD']:
            state['tier'] = Tier.TOP.value
            state['recommendation'] = Recommendation.INTERVIEW.value
        elif score >= config['MID_TIER_THRESHOLD']:
            state['tier'] = Tier.MID.value
            state['recommendation'] = Recommendation.TALENT_POOL.value
        else:
            state['tier'] = Tier.LOW.value
            state['recommendation'] = Recommendation.REJECT.value
        

        prompt = get_reasoning_prompt(
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
    

    workflow.add_node("extract", extract_node)
    workflow.add_node("match", match_node)
    workflow.add_node("score", score_node)
    workflow.add_node("rank", rank_node)
    

    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "match")
    workflow.add_edge("match", "score")
    workflow.add_edge("score", "rank")
    workflow.add_edge("rank", END)
    
    return workflow.compile()



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
    

    workflow = create_screening_workflow()
    result = workflow.invoke(initial_state)
    
    return result
