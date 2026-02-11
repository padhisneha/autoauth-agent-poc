"""
Appeal Agent - Generates appeals for denied prior authorizations
"""
from typing import Dict, Any
from datetime import datetime

from models import ClinicalEvidence, PolicyAnalysis, AppealLetter
from llm_client import UniversalLLMClient


class AppealAgent:
    """
    Agent responsible for drafting appeal letters when authorization is denied
    """
    
    def __init__(self):
        self.client = UniversalLLMClient()
    
    def generate_appeal_letter(
        self,
        denial_reason: str,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis,
        patient_name: str,
        provider_name: str,
        insurance_plan: str
    ) -> AppealLetter:
        """
        Generate a professional appeal letter for denied authorization
        
        Args:
            denial_reason: Reason provided for denial
            clinical_evidence: Original clinical evidence
            policy_analysis: Policy analysis results
            patient_name: Patient's name
            provider_name: Provider's name
            insurance_plan: Insurance plan name
            
        Returns:
            AppealLetter object with generated content
        """
        
        prompt = self._build_appeal_prompt(
            denial_reason,
            clinical_evidence,
            policy_analysis,
            patient_name,
            provider_name,
            insurance_plan
        )
        
        # Use universal client with slightly higher temperature for natural writing
        letter_content = self.client.generate(prompt, temperature=0.1)
        
        # Extract structured components
        rebuttal_points = self._extract_rebuttal_points(clinical_evidence, policy_analysis)
        additional_evidence = self._identify_additional_evidence(clinical_evidence, denial_reason)
        
        return AppealLetter(
            denial_reason=denial_reason,
            rebuttal_points=rebuttal_points,
            additional_evidence=additional_evidence,
            letter_content=letter_content,
            attachments=self._suggest_attachments(clinical_evidence),
            generated_at=datetime.now()
        )
    
    def _build_appeal_prompt(
        self,
        denial_reason: str,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis,
        patient_name: str,
        provider_name: str,
        insurance_plan: str
    ) -> str:
        """Build the prompt for appeal letter generation"""
        
        return f"""You are a healthcare attorney and clinical documentation specialist drafting a formal appeal letter for a denied prior authorization.

CONTEXT:
Insurance Plan: {insurance_plan}
Patient: {patient_name}
Provider: {provider_name}
Date: {datetime.now().strftime('%B %d, %Y')}

DENIAL REASON:
{denial_reason}

CLINICAL EVIDENCE:
Diagnoses: {', '.join(evidence.diagnosis_codes)}
Procedures Requested: {', '.join(evidence.procedure_codes)}

Supporting Clinical Evidence:
{chr(10).join(f'- {item}' for item in evidence.supporting_evidence)}

Patient Symptoms:
{chr(10).join(f'- {item}' for item in evidence.symptoms)}

Conservative Treatments Attempted:
{chr(10).join(f'- {item}' for item in evidence.prior_treatments)}

Severity Indicators:
{chr(10).join(f'- {item}' for item in evidence.severity_indicators)}

POLICY ANALYSIS:
Met Criteria: {', '.join(analysis.met_criteria[:5])}
Policy Reference: {analysis.policy_reference}

Your task is to write a professional, persuasive appeal letter that:

1. Opens with formal business letter formatting
2. Clearly states the purpose: appeal of denied prior authorization
3. Provides a point-by-point rebuttal of the denial reason
4. Cites specific clinical evidence that supports medical necessity
5. References relevant medical guidelines or literature when appropriate
6. Explains why alternative treatments are inappropriate or have failed
7. Emphasizes patient safety and quality of care concerns if applicable
8. Requests expedited review if there are urgent clinical factors
9. Closes professionally with clear next steps

TONE: Professional, factual, persuasive, respectful but firm
LENGTH: 2-3 pages (comprehensive but concise)
FORMAT: Formal business letter

Write the complete appeal letter now:"""
    
    def _extract_rebuttal_points(
        self,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis
    ) -> list[str]:
        """Extract key rebuttal points from evidence"""
        
        points = []
        
        # Conservative treatment attempted
        if evidence.prior_treatments:
            points.append(
                f"Multiple conservative treatments attempted: {', '.join(evidence.prior_treatments[:3])}"
            )
        
        # Clinical severity
        if evidence.severity_indicators:
            points.append(
                f"Documented severity indicators: {', '.join(evidence.severity_indicators[:2])}"
            )
        
        # Met policy criteria
        if len(analysis.met_criteria) > 0:
            points.append(
                f"Request meets {len(analysis.met_criteria)} policy criteria including: {analysis.met_criteria[0]}"
            )
        
        # Objective findings
        if evidence.supporting_evidence:
            points.append(
                f"Objective clinical findings support necessity: {evidence.supporting_evidence[0]}"
            )
        
        return points
    
    def _identify_additional_evidence(
        self,
        evidence: ClinicalEvidence,
        denial_reason: str
    ) -> list[str]:
        """Identify what additional evidence might strengthen appeal"""
        
        additional = []
        
        denial_lower = denial_reason.lower()
        
        if "conservative" in denial_lower or "treatment" in denial_lower:
            if len(evidence.prior_treatments) < 3:
                additional.append("Additional documentation of conservative treatments with specific dates and outcomes")
        
        if "medical necessity" in denial_lower or "not medically necessary" in denial_lower:
            additional.append("Peer-reviewed literature supporting medical necessity for this condition")
            additional.append("Clinical guidelines from professional societies")
        
        if "criteria" in denial_lower:
            additional.append("Point-by-point documentation showing how each policy criterion is met")
        
        if "documentation" in denial_lower:
            additional.append("Complete clinical notes with detailed examination findings")
            additional.append("Diagnostic test results and imaging reports")
        
        # General additions
        if evidence.severity_indicators:
            additional.append("Detailed documentation of severity indicators and red flags")
        
        return additional
    
    def _suggest_attachments(self, evidence: ClinicalEvidence) -> list[str]:
        """Suggest relevant attachments for the appeal"""
        
        attachments = [
            "Original prior authorization request",
            "Complete clinical notes from treating provider",
            "Denial letter from insurance company"
        ]
        
        if evidence.prior_treatments:
            attachments.append("Documentation of conservative treatment attempts with dates and outcomes")
        
        if evidence.supporting_evidence:
            attachments.append("Diagnostic test results and clinical findings")
        
        # Add imaging if mentioned
        if any("x-ray" in item.lower() or "imaging" in item.lower() 
               for item in evidence.supporting_evidence):
            attachments.append("Previous imaging reports")
        
        attachments.extend([
            "Relevant medical literature supporting treatment",
            "Clinical practice guidelines from professional societies"
        ])
        
        return attachments
    
    def assess_appeal_strength(
        self,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis,
        denial_reason: str
    ) -> Dict[str, Any]:
        """
        Assess the strength of the appeal case
        
        Returns:
            Assessment with strength rating and recommendations
        """
        
        strength_score = 0
        factors = []
        
        # Strong conservative treatment history
        if len(clinical_evidence.prior_treatments) >= 3:
            strength_score += 25
            factors.append("Multiple conservative treatments documented")
        elif len(clinical_evidence.prior_treatments) >= 1:
            strength_score += 10
        
        # Red flags or severity indicators
        if len(clinical_evidence.severity_indicators) >= 2:
            strength_score += 30
            factors.append("Multiple severity indicators present")
        elif len(clinical_evidence.severity_indicators) >= 1:
            strength_score += 15
        
        # Policy criteria met
        if len(policy_analysis.met_criteria) >= 3:
            strength_score += 25
            factors.append(f"{len(policy_analysis.met_criteria)} policy criteria satisfied")
        elif len(policy_analysis.met_criteria) >= 1:
            strength_score += 10
        
        # Strong supporting evidence
        if len(clinical_evidence.supporting_evidence) >= 4:
            strength_score += 20
            factors.append("Comprehensive clinical evidence")
        elif len(clinical_evidence.supporting_evidence) >= 2:
            strength_score += 10
        
        # Determine rating
        if strength_score >= 75:
            rating = "STRONG"
            recommendation = "High likelihood of successful appeal. Proceed with submission."
        elif strength_score >= 50:
            rating = "MODERATE"
            recommendation = "Reasonable chance of success. Consider gathering additional supporting documentation."
        else:
            rating = "WEAK"
            recommendation = "Appeal may be challenging. Strongly recommend obtaining additional clinical evidence and specialist consultation."
        
        return {
            "strength_score": strength_score,
            "rating": rating,
            "supporting_factors": factors,
            "recommendation": recommendation
        }