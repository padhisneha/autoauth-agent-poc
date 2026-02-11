"""
Clinical Reader Agent - Extracts clinical evidence from unstructured patient notes
"""
from typing import Dict, Any
import json
from models import ClinicalEvidence
from llm_client import UniversalLLMClient
from utils import safe_json_parse


class ClinicalReaderAgent:
    """
    Agent responsible for analyzing patient clinical notes and extracting
    structured clinical evidence for prior authorization
    """
    
    def __init__(self):
        self.client = UniversalLLMClient()
        
    def extract_clinical_evidence(
        self, 
        patient_notes: str, 
        procedure_code: str
    ) -> ClinicalEvidence:
        """
        Extract structured clinical evidence from unstructured patient notes
        
        Args:
            patient_notes: Raw clinical notes from EHR
            procedure_code: CPT code for requested procedure
            
        Returns:
            ClinicalEvidence object with extracted information
        """
        
        prompt = self._build_extraction_prompt(patient_notes, procedure_code)
        
        # Use universal client
        response_text = self.client.generate(prompt)
        
        # Use robust JSON parser
        try:
            evidence_dict = safe_json_parse(response_text)
            return ClinicalEvidence(**evidence_dict)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[CLINICAL READER] JSON parsing failed: {e}")
            print(f"[CLINICAL READER] Response preview: {response_text[:500]}...")
            raise ValueError(f"Failed to parse clinical evidence from LLM response: {str(e)}")
    
    def _build_extraction_prompt(self, patient_notes: str, procedure_code: str) -> str:
        """Build the prompt for clinical evidence extraction"""
        
        return f"""You are a clinical documentation specialist extracting structured data from patient notes for prior authorization.

PATIENT CLINICAL NOTES:
{patient_notes}

REQUESTED PROCEDURE CODE: {procedure_code}

Your task is to extract ALL relevant clinical information that would support a prior authorization request. Be thorough and precise.

Extract the following information and return ONLY a valid JSON object (no markdown, no explanations):

{{
  "diagnosis_codes": ["list of ICD-10 codes mentioned or implied"],
  "procedure_codes": ["list of CPT codes for requested procedures"],
  "supporting_evidence": [
    "specific clinical findings that justify the procedure",
    "objective test results",
    "physical examination findings",
    "symptom severity indicators"
  ],
  "symptoms": [
    "chief complaints",
    "associated symptoms",
    "symptom duration and severity"
  ],
  "prior_treatments": [
    "conservative treatments attempted",
    "duration of each treatment",
    "outcome/response to treatment"
  ],
  "contraindications": ["any contraindications to current or alternative treatments"],
  "relevant_dates": {{
    "symptom_onset": "date when symptoms began",
    "treatment_dates": "dates of prior treatments"
  }},
  "severity_indicators": [
    "red flags or concerning features",
    "functional impairments",
    "objective severity measures"
  ]
}}

IMPORTANT GUIDELINES:
1. Use standard ICD-10 codes (e.g., M54.16 for lumbar radiculopathy)
2. Include specific dates when mentioned
3. List treatments in chronological order
4. Quote specific measurements when available (pain scores, ROM, strength grades)
5. Identify red flags that might expedite authorization
6. Be precise and factual - only extract what is explicitly stated or clearly implied
7. If information is not present in notes, use empty lists [] not null
8. Return ONLY the JSON object, no other text
9. Do NOT include any markdown formatting like ```json
10. Ensure all strings are properly escaped (no unescaped quotes or newlines)

Extract the information now:"""
    
    def validate_completeness(self, evidence: ClinicalEvidence) -> Dict[str, Any]:
        """
        Validate if extracted evidence is complete for PA submission
        
        Returns:
            Dictionary with completeness assessment
        """
        issues = []
        
        if not evidence.diagnosis_codes:
            issues.append("Missing diagnosis codes")
        
        if not evidence.procedure_codes:
            issues.append("Missing procedure codes")
            
        if not evidence.supporting_evidence:
            issues.append("Missing supporting clinical evidence")
            
        if not evidence.prior_treatments and not evidence.severity_indicators:
            issues.append("Missing prior treatments or red flags justifying immediate imaging")
        
        if len(evidence.symptoms) < 2:
            issues.append("Limited symptom documentation")
        
        is_complete = len(issues) == 0
        
        return {
            "is_complete": is_complete,
            "missing_elements": issues,
            "completeness_score": max(0, 100 - (len(issues) * 15))
        }