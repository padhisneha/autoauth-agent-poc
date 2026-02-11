"""
Universal LLM Client - Supports multiple AI providers
"""
from typing import Optional, List, Dict, Any
from enum import Enum
from config import settings


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"  # For future support


class UniversalLLMClient:
    """
    Universal client that works with multiple LLM providers
    Switch providers by changing config without code changes
    """
    
    def __init__(self, provider: Optional[str] = None):
        """
        Initialize LLM client
        
        Args:
            provider: LLM provider name (anthropic, gemini, openai)
                     If None, reads from settings
        """
        self.provider = provider or settings.llm_provider
        self.model = settings.llm_model
        self.max_tokens = settings.max_tokens
        self.temperature = settings.temperature
        
        # Initialize the appropriate client
        if self.provider == LLMProvider.ANTHROPIC:
            self._init_anthropic()
        elif self.provider == LLMProvider.GEMINI:
            self._init_gemini()
        elif self.provider == LLMProvider.OPENAI:
            self._init_openai()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _init_anthropic(self):
        """Initialize Anthropic client"""
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=settings.anthropic_api_key)
            # Use Claude model if not specified
            if not self.model or self.model == "auto":
                self.model = "claude-sonnet-4-20250514"
        except ImportError:
            raise ImportError("Anthropic package not installed. Run: pip install anthropic")
    
    def _init_gemini(self):
        """Initialize Gemini client"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            # Use Gemini model if not specified
            if not self.model or self.model == "auto":
                self.model = "gemini-1.5-pro"
            self.client = genai.GenerativeModel(self.model)
        except ImportError:
            raise ImportError("Google Generative AI package not installed. Run: pip install google-generativeai")
    
    def _init_openai(self):
        """Initialize OpenAI client (for future support)"""
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.openai_api_key)
            if not self.model or self.model == "auto":
                self.model = "gpt-4"
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
    
    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate response from LLM (unified interface)
        
        Args:
            prompt: The user prompt
            max_tokens: Maximum tokens to generate (overrides default)
            temperature: Temperature for generation (overrides default)
            system_prompt: System prompt (for supported providers)
            
        Returns:
            Generated text response
        """
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature
        
        if self.provider == LLMProvider.ANTHROPIC:
            return self._generate_anthropic(prompt, max_tokens, temperature, system_prompt)
        elif self.provider == LLMProvider.GEMINI:
            return self._generate_gemini(prompt, max_tokens, temperature, system_prompt)
        elif self.provider == LLMProvider.OPENAI:
            return self._generate_openai(prompt, max_tokens, temperature, system_prompt)
    
    def _generate_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate using Anthropic API"""
        messages = [{"role": "user", "content": prompt}]
        
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        
        if system_prompt:
            kwargs["system"] = system_prompt
        
        response = self.client.messages.create(**kwargs)
        return response.content[0].text
    
    def _generate_gemini(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate using Gemini API"""
        # Combine system prompt with user prompt if provided
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        # Configure generation settings
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        
        response = self.client.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        
        return response.text
    
    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> str:
        """Generate using OpenAI API"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        return response.choices[0].message.content
    
    def get_provider_info(self) -> Dict[str, str]:
        """Get current provider information"""
        return {
            "provider": self.provider,
            "model": self.model,
            "max_tokens": str(self.max_tokens),
            "temperature": str(self.temperature)
        }