"""
Demo script for AutoAuth Agent system
"""
import sys
from datetime import datetime

from models import PriorAuthorizationRequest, PatientInfo, ProviderInfo
from orchestrator import PAWorkflowOrchestrator
from data.mock_data.patient_notes import (
    MOCK_PATIENT_NOTE_MRI,
    MOCK_PATIENT_NOTE_SLEEP_STUDY,
    MOCK_PATIENT_NOTE_PHYSICAL_THERAPY
)


def create_sample_request(case: str = "mri") -> PriorAuthorizationRequest:
    """Create a sample PA request for testing"""
    
    if case == "mri":
        patient_info = PatientInfo(
            patient_id="PT-12345",
            name="John Doe",
            date_of_birth="05/15/1975",
            gender="Male",
            insurance_plan="UnitedHealth",
            member_id="UH-987654321"
        )
        
        provider_info = ProviderInfo(
            provider_id="PR-98765",
            name="Dr. Sarah Johnson",
            npi="1234567890",
            specialty="Family Medicine",
            facility="City Medical Center",
            phone="(555) 123-4567"
        )
        
        return PriorAuthorizationRequest(
            request_id=f"PA-MRI-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            patient_info=patient_info,
            provider_info=provider_info,
            patient_notes=MOCK_PATIENT_NOTE_MRI,
            requested_service="72148",  # MRI lumbar spine
            created_at=datetime.now()
        )
    
    elif case == "sleep":
        patient_info = PatientInfo(
            patient_id="PT-87654",
            name="Jane Smith",
            date_of_birth="03/22/1982",
            gender="Female",
            insurance_plan="Aetna",
            member_id="AET-123456789"
        )
        
        provider_info = ProviderInfo(
            provider_id="PR-54321",
            name="Dr. Michael Chen",
            npi="9876543210",
            specialty="Sleep Medicine",
            facility="Sleep Disorders Center",
            phone="(555) 987-6543"
        )
        
        return PriorAuthorizationRequest(
            request_id=f"PA-SLEEP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            patient_info=patient_info,
            provider_info=provider_info,
            patient_notes=MOCK_PATIENT_NOTE_SLEEP_STUDY,
            requested_service="95810",  # Sleep study
            created_at=datetime.now()
        )
    
    elif case == "pt":
        patient_info = PatientInfo(
            patient_id="PT-45678",
            name="Robert Williams",
            date_of_birth="08/10/1988",
            gender="Male",
            insurance_plan="Cigna",
            member_id="CIG-567890123"
        )
        
        provider_info = ProviderInfo(
            provider_id="PR-11111",
            name="Dr. Lisa Martinez",
            npi="5555555555",
            specialty="Orthopedic Surgery",
            facility="Orthopedic Specialists",
            phone="(555) 444-3333"
        )
        
        return PriorAuthorizationRequest(
            request_id=f"PA-PT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            patient_info=patient_info,
            provider_info=provider_info,
            patient_notes=MOCK_PATIENT_NOTE_PHYSICAL_THERAPY,
            requested_service="97110",  # Physical therapy
            created_at=datetime.now()
        )
    
    else:
        raise ValueError(f"Unknown case: {case}")


def print_results(response):
    """Pretty print the results"""
    
    print("\n" + "="*80)
    print("PRIOR AUTHORIZATION RESULTS")
    print("="*80)
    
    print(f"\nRequest ID: {response.request_id}")
    print(f"Status: {response.status.value.upper()}")
    print(f"Processing Time: {response.processing_time_seconds:.2f} seconds")
    
    if response.clinical_evidence:
        print("\n--- CLINICAL EVIDENCE ---")
        print(f"Diagnoses: {', '.join(response.clinical_evidence.diagnosis_codes)}")
        print(f"Procedures: {', '.join(response.clinical_evidence.procedure_codes)}")
        print(f"Supporting Evidence: {len(response.clinical_evidence.supporting_evidence)} points")
        print(f"Prior Treatments: {len(response.clinical_evidence.prior_treatments)} documented")
    
    if response.policy_analysis:
        print("\n--- POLICY ANALYSIS ---")
        print(f"Approval Likelihood: {response.policy_analysis.approval_likelihood.value.upper()}")
        print(f"Met Criteria: {len(response.policy_analysis.met_criteria)}")
        if response.policy_analysis.met_criteria:
            for criterion in response.policy_analysis.met_criteria[:3]:
                print(f"  ✓ {criterion}")
        
        if response.policy_analysis.missing_criteria:
            print(f"Missing Criteria: {len(response.policy_analysis.missing_criteria)}")
            for criterion in response.policy_analysis.missing_criteria[:3]:
                print(f"  ✗ {criterion}")
    
    if response.fhir_request:
        print("\n--- FHIR SUBMISSION ---")
        print(f"Resource Type: {response.fhir_request['resourceType']}")
        print(f"Status: {response.fhir_request['status']}")
        print(f"Priority: {response.fhir_request.get('priority', 'N/A')}")
    
    if response.appeal_letter:
        print("\n--- APPEAL PREPARATION ---")
        print(f"Rebuttal Points: {len(response.appeal_letter.rebuttal_points)}")
        print(f"Additional Evidence Suggested: {len(response.appeal_letter.additional_evidence)}")
        print(f"Attachments: {len(response.appeal_letter.attachments)}")
    
    if response.needs_human_review:
        print("\n⚠️  HUMAN REVIEW REQUIRED")
        print(f"Reason: {response.review_reason}")
    
    if response.errors:
        print("\n❌ ERRORS")
        for error in response.errors:
            print(f"  • {error}")
    
    print("\n" + "="*80 + "\n")


def main():
    """Run the demo"""
    
    # Check for API key
    try:
        from config import settings
        if not settings.anthropic_api_key or settings.anthropic_api_key == "your_api_key_here":
            print("❌ Error: Please set ANTHROPIC_API_KEY in .env file")
            print("\nSteps:")
            print("1. Copy .env.example to .env")
            print("2. Add your Anthropic API key")
            print("3. Run this script again")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        sys.exit(1)
    
    # Get case from command line or use default
    case = sys.argv[1] if len(sys.argv) > 1 else "mri"
    
    if case not in ["mri", "sleep", "pt"]:
        print(f"Unknown case: {case}")
        print("Usage: python demo.py [mri|sleep|pt]")
        sys.exit(1)
    
    print(f"\n🏥 AutoAuth Agent - Demo")
    print(f"Running test case: {case.upper()}\n")
    
    # Create orchestrator
    orchestrator = PAWorkflowOrchestrator()
    
    # Create sample request
    request = create_sample_request(case)
    
    # Process the request
    response = orchestrator.process_authorization_request(request)
    
    # Print results
    print_results(response)
    
    # Save results to file
    output_dir = "data/output"
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/pa_result_{response.request_id}.json"
    
    import json
    with open(output_file, 'w') as f:
        # Convert response to dict for JSON serialization
        result_dict = {
            "request_id": response.request_id,
            "status": response.status.value,
            "processing_time": response.processing_time_seconds,
            "needs_human_review": response.needs_human_review,
            "review_reason": response.review_reason,
            "clinical_evidence": response.clinical_evidence.model_dump() if response.clinical_evidence else None,
            "policy_analysis": response.policy_analysis.model_dump() if response.policy_analysis else None,
            "has_fhir_request": response.fhir_request is not None,
            "has_appeal_letter": response.appeal_letter is not None,
            "errors": response.errors
        }
        json.dump(result_dict, f, indent=2)
    
    print(f"📄 Full results saved to: {output_file}\n")


if __name__ == "__main__":
    main()