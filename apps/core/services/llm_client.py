"""
OpenAI LLM Client with caching and retry logic.
"""
import hashlib
import json
import logging
from typing import Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Singleton LLM client with caching and retry logic.
    Uses OpenAI GPT-4o for best quality responses.
    """
    
    _instance = None
    _llm = None
    _llm_json = None
    
    CACHE_TIMEOUT = 3600  # 1 hour
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._llm is None:
            api_key = settings.OPENAI_API_KEY
            model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o')
            
            if not api_key:
                logger.warning("OPENAI_API_KEY not configured")
                return
            
            # Regular LLM for text responses
            self._llm = ChatOpenAI(
                model=model,
                temperature=0.0,
                api_key=api_key
            )
            
            # JSON-mode LLM for structured responses
            self._llm_json = ChatOpenAI(
                model=model,
                temperature=0.0,
                api_key=api_key,
                model_kwargs={"response_format": {"type": "json_object"}}
            )
            
            logger.info(f"LLMClient initialized with model: {model}")
    
    def _get_cache_key(self, prompt: str) -> str:
        """Generate cache key from prompt."""
        return f"llm_cache_{hashlib.md5(prompt.encode()).hexdigest()}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def invoke_json(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> Dict[str, Any]:
        """
        Invoke LLM and return parsed JSON response.
        Uses caching to avoid duplicate API calls.
        
        Args:
            prompt: The user prompt
            system_prompt: The system prompt
            
        Returns:
            Parsed JSON response as dictionary
        """
        if not self._llm_json:
            raise RuntimeError("LLM not initialized. Check OPENAI_API_KEY.")
        
        # Check cache
        cache_key = self._get_cache_key(f"{system_prompt}:{prompt}")
        cached = cache.get(cache_key)
        if cached:
            logger.debug("LLM cache hit")
            return cached
        
        # Call LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]
        
        response = self._llm_json.invoke(messages)
        result = json.loads(response.content)
        
        # Cache result
        cache.set(cache_key, result, self.CACHE_TIMEOUT)
        
        return result
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def invoke_text(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """
        Invoke LLM and return text response.
        Uses caching to avoid duplicate API calls.
        
        Args:
            prompt: The user prompt
            system_prompt: The system prompt
            
        Returns:
            Text response
        """
        if not self._llm:
            raise RuntimeError("LLM not initialized. Check OPENAI_API_KEY.")
        
        # Check cache
        cache_key = self._get_cache_key(f"text:{system_prompt}:{prompt}")
        cached = cache.get(cache_key)
        if cached:
            logger.debug("LLM text cache hit")
            return cached
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]
        
        response = self._llm.invoke(messages)
        result = response.content
        
        # Cache result
        cache.set(cache_key, result, self.CACHE_TIMEOUT)
        
        return result


# Singleton instance
llm_client = LLMClient()
