"""
Utility functions for AutoAuth Agent
"""
import json
import re
from typing import Dict, Any, Optional


def extract_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extract and parse JSON from LLM response
    
    Handles:
    - Markdown code blocks (```json ... ```)
    - Text before/after JSON
    - Common JSON formatting issues
    - Multi-line strings
    
    Args:
        response_text: Raw response from LLM
        
    Returns:
        Parsed JSON as dictionary, or None if parsing fails
    """
    
    # Try direct parsing first
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code blocks
    json_patterns = [
        r'```json\s*\n(.*?)\n```',  # ```json ... ```
        r'```\s*\n(.*?)\n```',       # ``` ... ```
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, response_text, re.DOTALL)
        if matches:
            json_str = matches[0] if isinstance(matches[0], str) else matches[0]
            try:
                return json.loads(json_str.strip())
            except json.JSONDecodeError:
                continue
    
    # Try finding JSON object boundaries
    try:
        # Find first { and last }
        start = response_text.find('{')
        end = response_text.rfind('}')
        
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end+1]
            
            return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Last resort: try to fix common issues
    try:
        start = response_text.find('{')
        end = response_text.rfind('}')
        
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end+1]
            
            # Try some basic fixes
            json_str = fix_json_issues(json_str)
            
            return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def fix_json_issues(json_str: str) -> str:
    """
    Attempt to fix common JSON formatting issues
    
    Args:
        json_str: Potentially malformed JSON string
        
    Returns:
        Cleaned JSON string
    """
    
    # Remove any trailing commas before closing braces/brackets
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Remove any control characters except newlines in strings
    # This is tricky - be conservative
    
    return json_str


def safe_json_parse(response_text: str, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely parse JSON with fallback
    
    Args:
        response_text: Raw response from LLM
        fallback: Fallback value if parsing fails
        
    Returns:
        Parsed JSON or fallback value
        
    Raises:
        ValueError: If parsing fails and no fallback provided
    """
    result = extract_json_from_response(response_text)
    
    if result is None:
        if fallback is not None:
            return fallback
        
        # Provide helpful error message with response preview
        preview = response_text[:500] if len(response_text) > 500 else response_text
        raise ValueError(
            f"Failed to parse JSON from LLM response.\n"
            f"Response preview (first 500 chars):\n{preview}\n\n"
            f"This usually happens when the LLM includes extra text or formatting.\n"
            f"Check if the LLM is following the JSON-only instruction in the prompt."
        )
    
    return result


def validate_json_structure(data: Dict[str, Any], required_keys: list[str]) -> bool:
    """
    Validate that JSON has required keys
    
    Args:
        data: Parsed JSON dictionary
        required_keys: List of required key names
        
    Returns:
        True if all required keys present, False otherwise
    """
    return all(key in data for key in required_keys)


def extract_json_array_from_response(response_text: str) -> Optional[list]:
    """
    Extract JSON array from response (for batch operations)
    
    Args:
        response_text: Raw response from LLM
        
    Returns:
        Parsed JSON array or None if parsing fails
    """
    
    # Try direct parsing
    try:
        result = json.loads(response_text.strip())
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown
    json_patterns = [
        r'```json\s*\n(.*?)\n```',
        r'```\s*\n(.*?)\n```',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, response_text, re.DOTALL)
        if matches:
            json_str = matches[0] if isinstance(matches[0], str) else matches[0]
            try:
                result = json.loads(json_str.strip())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue
    
    # Try finding array boundaries
    try:
        start = response_text.find('[')
        end = response_text.rfind(']')
        
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end+1]
            result = json.loads(json_str)
            if isinstance(result, list):
                return result
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None