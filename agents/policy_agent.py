"""
Policy Agent - Evaluates clinical evidence against payer coverage policies
"""
from typing import Dict, Any
import json
from models import ClinicalEvidence, PolicyAnalysis, ApprovalLikelihood
from llm_client import UniversalLLMClient
from data.mock_data.payer_policies import get_policy_for_procedure
from utils import safe_json_parse


class PolicyAgent:
    """
    Agent responsible for retrieving payer policies and determining if
    clinical evidence meets coverage criteria
    """
    
    def __init__(self):
        self.client = UniversalLLMClient()
        
    def evaluate_against_policy(
        self,
        clinical_evidence: ClinicalEvidence,
        insurance_plan: str = "UnitedHealth"
    ) -> PolicyAnalysis:
        """
        Evaluate clinical evidence against payer policy criteria
        
        Args:
            clinical_evidence: Extracted clinical evidence
            insurance_plan: Name of insurance plan
            
        Returns:
            PolicyAnalysis with approval likelihood and reasoning
        """
        
        # Get the relevant policy document
        procedure_code = clinical_evidence.procedure_codes[0] if clinical_evidence.procedure_codes else ""
        policy_text = get_policy_for_procedure(procedure_code, insurance_plan)
        
        if "Policy not found" in policy_text:
            return PolicyAnalysis(
                approval_likelihood=ApprovalLikelihood.MEDIUM,
                met_criteria=["Procedure code provided"],
                missing_criteria=["Policy guidelines not available"],
                required_documentation=[],
                policy_reference=f"{insurance_plan} - Policy Not Available",
                reasoning="Unable to locate specific policy for this procedure. Manual review recommended."
            )
        
        # Analyze evidence against policy
        prompt = self._build_policy_analysis_prompt(clinical_evidence, policy_text, insurance_plan)
        
        # Use universal client
        response_text = self.client.generate(prompt)
        
        # Use robust JSON parser with fallback
        try:
            analysis_dict = safe_json_parse(response_text)
            return PolicyAnalysis(**analysis_dict)
        except (json.JSONDecodeError, ValueError) as e:
            # If JSON parsing completely fails, create a fallback response
            print(f"[POLICY AGENT] JSON parsing failed: {e}")
            print(f"[POLICY AGENT] Response preview: {response_text[:500]}...")
            
            # Return a safe fallback analysis
            return PolicyAnalysis(
                approval_likelihood=ApprovalLikelihood.MEDIUM,
                met_criteria=["Clinical evidence provided"],
                missing_criteria=["Unable to parse complete policy analysis - LLM response formatting issue"],
                required_documentation=["Manual review of policy compliance recommended"],
                policy_reference=insurance_plan,
                reasoning=f"Automated policy analysis encountered a parsing error. The LLM did not return properly formatted JSON. Manual review is recommended to ensure policy compliance. Technical error: {str(e)[:200]}"
            )
    
    def _build_policy_analysis_prompt(
        self,
        evidence: ClinicalEvidence,
        policy_text: str,
        insurance_plan: str
    ) -> str:
        """Build prompt for policy analysis"""
        
        evidence_summary = f"""
CLINICAL EVIDENCE:
- Diagnosis Codes: {', '.join(evidence.diagnosis_codes)}
- Procedure Codes: {', '.join(evidence.procedure_codes)}
- Supporting Evidence: {evidence.supporting_evidence}
- Symptoms: {evidence.symptoms}
- Prior Treatments: {evidence.prior_treatments}
- Severity Indicators: {evidence.severity_indicators}
"""
        
        return f"""You are a prior authorization specialist evaluating whether clinical evidence meets payer policy criteria.

INSURANCE PLAN: {insurance_plan}

PAYER POLICY DOCUMENT:
{policy_text}

{evidence_summary}

Your task is to systematically evaluate whether the clinical evidence meets the policy requirements for approval.

Analyze each policy criterion and determine:
1. Which criteria are clearly satisfied by the clinical evidence
2. Which criteria are not met or have insufficient documentation
3. What additional documentation might be needed
4. The overall likelihood of approval

Return ONLY a valid JSON object (no markdown, no explanations):

{{
  "approval_likelihood": "high|medium|low",
  "met_criteria": [
    "specific criterion from policy that IS satisfied",
    "cite specific evidence that satisfies it"
  ],
  "missing_criteria": [
    "specific criterion that is NOT met",
    "explain what's missing"
  ],
  "required_documentation": [
    "additional documents or information needed"
  ],
  "policy_reference": "{insurance_plan} Policy [policy number if available]",
  "reasoning": "Detailed explanation of the determination including key factors supporting approval, any concerns or gaps, specific policy requirements and how evidence addresses them, and recommendations for strengthening the request"
}}

CRITICAL FORMATTING RULES:
1. Return ONLY the JSON object - no other text before or after
2. Do NOT use markdown code blocks (no ```json)
3. Ensure all strings are on single lines (no literal newlines in string values)
4. Use proper JSON escaping for quotes and special characters
5. Keep the reasoning field as a single paragraph (no newlines)

APPROVAL LIKELIHOOD GUIDELINES:
- HIGH: All major criteria met, strong supporting evidence, minimal or no missing elements
- MEDIUM: Most criteria met but some gaps, or criteria met but borderline documentation
- LOW: Missing major criteria, insufficient conservative treatment, or contradictory evidence

Be thorough but fair in your analysis. Consider the totality of clinical evidence.

Analyze now:"""
    
    def check_red_flags(self, evidence: ClinicalEvidence) -> Dict[str, Any]:
        """
        Check for red flags that might expedite approval or require special handling
        
        Returns:
            Dictionary with red flag assessment
        """
        red_flags = []
        
        # Check for neurological red flags
        neurological_keywords = [
            "progressive", "weakness", "numbness", "bladder", "bowel",
            "saddle anesthesia", "cauda equina", "cord compression"
        ]
        
        for indicator in evidence.severity_indicators:
            indicator_lower = indicator.lower()
            for keyword in neurological_keywords:
                if keyword in indicator_lower:
                    red_flags.append(f"Neurological concern: {indicator}")
                    break
        
        # Check for infection/malignancy red flags
        serious_keywords = ["fever", "cancer", "infection", "weight loss", "night pain"]
        
        for symptom in evidence.symptoms:
            symptom_lower = symptom.lower()
            for keyword in serious_keywords:
                if keyword in symptom_lower:
                    red_flags.append(f"Serious concern: {symptom}")
                    break
        
        return {
            "has_red_flags": len(red_flags) > 0,
            "red_flags": red_flags,
            "expedited_review_recommended": len(red_flags) > 1
        }
    
    def suggest_improvements(self, analysis: PolicyAnalysis) -> list[str]:
        """
        Suggest ways to improve the authorization request
        
        Returns:
            List of actionable suggestions
        """
        suggestions = []
        
        if analysis.approval_likelihood == ApprovalLikelihood.LOW:
            suggestions.append("Consider obtaining additional clinical documentation")
            suggestions.append("Ensure all conservative treatments are documented with dates and outcomes")
        
        if analysis.missing_criteria:
            for criterion in analysis.missing_criteria:
                if "conservative" in criterion.lower():
                    suggestions.append("Document all conservative treatments attempted including duration and response")
                elif "imaging" in criterion.lower():
                    suggestions.append("Obtain and document preliminary imaging results (X-rays)")
                elif "duration" in criterion.lower():
                    suggestions.append("Clarify symptom duration and timeline")
        
        if analysis.required_documentation:
            suggestions.append("Gather the following documentation before resubmission:")
            suggestions.extend([f"  - {doc}" for doc in analysis.required_documentation])
        
        return suggestions