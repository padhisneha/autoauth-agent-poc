"""
Data models for AutoAuth Agent system
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum


class ApprovalLikelihood(str, Enum):
    """Likelihood of PA approval"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PAStatus(str, Enum):
    """Prior Authorization status"""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    APPEALED = "appealed"
    NEEDS_REVIEW = "needs_review"


class PatientInfo(BaseModel):
    """Patient demographic information"""
    patient_id: str
    name: str
    date_of_birth: str
    gender: str
    insurance_plan: str
    member_id: str


class ProviderInfo(BaseModel):
    """Healthcare provider information"""
    provider_id: str
    name: str
    npi: str
    specialty: str
    facility: str
    phone: str


class ClinicalEvidence(BaseModel):
    """Extracted clinical evidence from patient notes"""
    diagnosis_codes: List[str] = Field(description="ICD-10 diagnosis codes")
    procedure_codes: List[str] = Field(description="CPT procedure codes")
    supporting_evidence: List[str] = Field(description="Clinical justification points")
    symptoms: List[str] = Field(description="Patient symptoms")
    prior_treatments: List[str] = Field(description="Treatments already attempted")
    contraindications: List[str] = Field(default_factory=list, description="Any contraindications")
    relevant_dates: Dict[str, Union[str, List[str]]] = Field(
        default_factory=dict,
        description="Important dates"
    )
    severity_indicators: List[str] = Field(default_factory=list, description="Severity markers")


class PolicyAnalysis(BaseModel):
    """Results from policy checking"""
    approval_likelihood: ApprovalLikelihood
    met_criteria: List[str] = Field(description="Criteria that are satisfied")
    missing_criteria: List[str] = Field(default_factory=list, description="Unmet criteria")
    required_documentation: List[str] = Field(default_factory=list, description="Additional docs needed")
    policy_reference: str = Field(description="Policy document reference")
    reasoning: str = Field(description="Detailed reasoning for determination")


class FHIRServiceRequest(BaseModel):
    """Simplified FHIR ServiceRequest representation"""
    resource_type: str = "ServiceRequest"
    id: Optional[str] = None
    status: str = "draft"
    intent: str = "order"
    code: Dict[str, Any]  # CodeableConcept
    subject: Dict[str, str]  # Reference to Patient
    requester: Dict[str, str]  # Reference to Practitioner
    reasonCode: List[Dict[str, Any]]  # CodeableConcept
    supportingInfo: List[str] = Field(default_factory=list)


class AppealLetter(BaseModel):
    """Generated appeal letter content"""
    denial_reason: str
    rebuttal_points: List[str]
    additional_evidence: List[str]
    letter_content: str
    attachments: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


class PriorAuthorizationRequest(BaseModel):
    """Complete PA request"""
    request_id: str
    patient_info: PatientInfo
    provider_info: ProviderInfo
    patient_notes: str
    requested_service: str
    created_at: datetime = Field(default_factory=datetime.now)


class PriorAuthorizationResponse(BaseModel):
    """PA processing response"""
    request_id: str
    status: PAStatus
    clinical_evidence: Optional[ClinicalEvidence] = None
    policy_analysis: Optional[PolicyAnalysis] = None
    fhir_request: Optional[Dict[str, Any]] = None
    appeal_letter: Optional[AppealLetter] = None
    processing_time_seconds: float
    needs_human_review: bool = False
    review_reason: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.now)