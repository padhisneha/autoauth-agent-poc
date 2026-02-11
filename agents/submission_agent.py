"""
Submission Agent - Generates FHIR resources and authorization forms
"""
from typing import Dict, Any, Optional
import json
from datetime import datetime
from fhir.resources.servicerequest import ServiceRequest
from fhir.resources.patient import Patient
from fhir.resources.practitioner import Practitioner
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.reference import Reference

from models import (
    ClinicalEvidence, 
    PolicyAnalysis, 
    PatientInfo, 
    ProviderInfo,
    FHIRServiceRequest
)
from llm_client import UniversalLLMClient
from config import settings


class SubmissionAgent:
    """
    Agent responsible for generating FHIR resources and submitting
    prior authorization requests
    """
    
    def __init__(self):
        self.client = UniversalLLMClient()
        
    def create_fhir_service_request(
        self,
        patient_info: PatientInfo,
        provider_info: ProviderInfo,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis
    ) -> Dict[str, Any]:
        """
        Create a FHIR ServiceRequest resource for prior authorization
        
        Args:
            patient_info: Patient demographic information
            provider_info: Provider/facility information
            clinical_evidence: Clinical justification
            policy_analysis: Policy analysis results
            
        Returns:
            FHIR ServiceRequest as dictionary
        """
        
        # Create the primary procedure code
        procedure_code = clinical_evidence.procedure_codes[0] if clinical_evidence.procedure_codes else "Unknown"
        
        # Build reason codes from diagnosis codes
        reason_codes = []
        for dx_code in clinical_evidence.diagnosis_codes:
            reason_codes.append({
                "coding": [{
                    "system": "http://hl7.org/fhir/sid/icd-10",
                    "code": dx_code,
                    "display": f"Diagnosis: {dx_code}"
                }]
            })
        
        # Create FHIR ServiceRequest
        service_request = {
            "resourceType": "ServiceRequest",
            "id": f"pa-request-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "active",
            "intent": "order",
            "priority": "urgent" if policy_analysis.approval_likelihood == "high" else "routine",
            "code": {
                "coding": [{
                    "system": "http://www.ama-assn.org/go/cpt",
                    "code": procedure_code,
                    "display": f"CPT {procedure_code}"
                }],
                "text": f"Prior Authorization Request for {procedure_code}"
            },
            "subject": {
                "reference": f"Patient/{patient_info.patient_id}",
                "display": patient_info.name
            },
            "encounter": {
                "reference": f"Encounter/{patient_info.patient_id}-{datetime.now().strftime('%Y%m%d')}"
            },
            "authoredOn": datetime.now().isoformat(),
            "requester": {
                "reference": f"Practitioner/{provider_info.provider_id}",
                "display": provider_info.name,
                "identifier": {
                    "system": "http://hl7.org/fhir/sid/us-npi",
                    "value": provider_info.npi
                }
            },
            "reasonCode": reason_codes,
            "reasonReference": [],
            "insurance": [{
                "reference": f"Coverage/{patient_info.member_id}",
                "display": patient_info.insurance_plan
            }],
            "supportingInfo": self._build_supporting_info(clinical_evidence, policy_analysis),
            "note": [{
                "text": self._generate_clinical_summary(clinical_evidence, policy_analysis)
            }]
        }
        
        return service_request
    
    def _build_supporting_info(
        self,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis
    ) -> list[Dict[str, Any]]:
        """Build supporting information references"""
        
        supporting_info = []
        
        # Add conservative treatment history
        if evidence.prior_treatments:
            supporting_info.append({
                "reference": "DocumentReference/conservative-treatment-history",
                "display": f"Conservative treatments: {', '.join(evidence.prior_treatments[:3])}"
            })
        
        # Add severity indicators
        if evidence.severity_indicators:
            supporting_info.append({
                "reference": "DocumentReference/severity-indicators",
                "display": f"Clinical indicators: {', '.join(evidence.severity_indicators[:2])}"
            })
        
        # Add policy analysis
        supporting_info.append({
            "reference": "DocumentReference/policy-analysis",
            "display": f"Policy Analysis: {analysis.approval_likelihood.value} likelihood"
        })
        
        return supporting_info
    
    def _generate_clinical_summary(
        self,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis
    ) -> str:
        """Generate a concise clinical summary for the authorization request"""
        
        summary_parts = []
        
        # Diagnosis
        if evidence.diagnosis_codes:
            summary_parts.append(f"DIAGNOSES: {', '.join(evidence.diagnosis_codes)}")
        
        # Key symptoms
        if evidence.symptoms:
            summary_parts.append(f"SYMPTOMS: {'; '.join(evidence.symptoms[:3])}")
        
        # Conservative treatment
        if evidence.prior_treatments:
            summary_parts.append(f"CONSERVATIVE TREATMENT: {'; '.join(evidence.prior_treatments[:3])}")
        
        # Red flags/severity
        if evidence.severity_indicators:
            summary_parts.append(f"CLINICAL INDICATORS: {'; '.join(evidence.severity_indicators[:2])}")
        
        # Supporting evidence
        if evidence.supporting_evidence:
            summary_parts.append(f"CLINICAL FINDINGS: {'; '.join(evidence.supporting_evidence[:3])}")
        
        # Policy analysis
        summary_parts.append(f"POLICY ANALYSIS: {analysis.approval_likelihood.value.upper()} likelihood of approval")
        summary_parts.append(f"MET CRITERIA: {len(analysis.met_criteria)} criteria satisfied")
        
        if analysis.missing_criteria:
            summary_parts.append(f"MISSING CRITERIA: {len(analysis.missing_criteria)} criteria need attention")
        
        return "\n\n".join(summary_parts)
    
    def generate_authorization_form(
        self,
        patient_info: PatientInfo,
        provider_info: ProviderInfo,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis
    ) -> str:
        """
        Generate a human-readable authorization form using LLM
        
        Returns:
            Formatted authorization form as string
        """
        
        prompt = f"""Generate a professional Prior Authorization Request Form with the following information:

PATIENT INFORMATION:
- Name: {patient_info.name}
- Patient ID: {patient_info.patient_id}
- Date of Birth: {patient_info.date_of_birth}
- Gender: {patient_info.gender}
- Insurance: {patient_info.insurance_plan}
- Member ID: {patient_info.member_id}

PROVIDER INFORMATION:
- Provider: {provider_info.name}
- NPI: {provider_info.npi}
- Specialty: {provider_info.specialty}
- Facility: {provider_info.facility}
- Phone: {provider_info.phone}

REQUESTED SERVICE:
- Procedure Codes: {', '.join(clinical_evidence.procedure_codes)}
- Diagnosis Codes: {', '.join(clinical_evidence.diagnosis_codes)}

CLINICAL JUSTIFICATION:
Supporting Evidence:
{chr(10).join(f'- {item}' for item in clinical_evidence.supporting_evidence)}

Symptoms:
{chr(10).join(f'- {item}' for item in clinical_evidence.symptoms)}

Prior Treatments Attempted:
{chr(10).join(f'- {item}' for item in clinical_evidence.prior_treatments)}

Severity Indicators:
{chr(10).join(f'- {item}' for item in clinical_evidence.severity_indicators)}

POLICY ANALYSIS:
- Approval Likelihood: {policy_analysis.approval_likelihood.value.upper()}
- Criteria Met: {len(policy_analysis.met_criteria)}
- Policy Reference: {policy_analysis.policy_reference}

Generate a professional, formatted Prior Authorization Request Form. Make it clear, concise, and suitable for submission to the insurance company."""

        # Use universal client
        return self.client.generate(prompt, max_tokens=2048)
    
    def submit_authorization_request(
        self,
        fhir_request: Dict[str, Any],
        payer_endpoint: str = None
    ) -> Dict[str, Any]:
        """
        Submit authorization request to payer FHIR endpoint
        
        For POC: This just logs the request instead of actual submission
        
        Args:
            fhir_request: FHIR ServiceRequest resource
            payer_endpoint: Payer's FHIR endpoint URL
            
        Returns:
            Submission result
        """
        
        # In production: POST to payer_endpoint
        # For POC: Just simulate successful submission
        
        submission_result = {
            "submitted": True,
            "submission_id": f"SUB-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "endpoint": payer_endpoint or settings.fhir_base_url,
            "status": "pending_review",
            "estimated_response_time": "2-5 business days"
        }
        
        # Log submission (in production: save to database)
        print(f"[SUBMISSION] Request {submission_result['submission_id']} submitted successfully")
        
        return submission_result
    
    def validate_fhir_request(self, fhir_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate FHIR ServiceRequest for completeness
        
        Returns:
            Validation result with any errors
        """
        errors = []
        warnings = []
        
        # Check required fields
        required_fields = ["resourceType", "status", "intent", "code", "subject", "requester"]
        for field in required_fields:
            if field not in fhir_request:
                errors.append(f"Missing required field: {field}")
        
        # Check code structure
        if "code" in fhir_request:
            if "coding" not in fhir_request["code"]:
                errors.append("Missing code.coding")
            elif not fhir_request["code"]["coding"]:
                errors.append("Empty code.coding array")
        
        # Check reason codes
        if "reasonCode" not in fhir_request or not fhir_request["reasonCode"]:
            warnings.append("No diagnosis codes (reasonCode) provided")
        
        # Check supporting info
        if "supportingInfo" not in fhir_request or not fhir_request["supportingInfo"]:
            warnings.append("No supporting information provided")
        
        is_valid = len(errors) == 0
        
        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings
        }