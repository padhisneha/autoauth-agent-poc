"""
Quick validation test to ensure all imports work correctly
"""
import sys

def test_imports():
    """Test that all modules can be imported"""
    
    print("Testing imports...")
    
    try:
        print("  ✓ Testing config...")
        from config import settings
        
        print("  ✓ Testing models...")
        from models import (
            PriorAuthorizationRequest,
            PriorAuthorizationResponse,
            ClinicalEvidence,
            PolicyAnalysis
        )
        
        print("  ✓ Testing agents...")
        from agents import (
            ClinicalReaderAgent,
            PolicyAgent,
            SubmissionAgent,
            AppealAgent
        )
        
        print("  ✓ Testing orchestrator...")
        from orchestrator import PAWorkflowOrchestrator
        
        print("  ✓ Testing mock data...")
        from data.mock_data.patient_notes import (
            MOCK_PATIENT_NOTE_MRI,
            MOCK_PATIENT_NOTE_SLEEP_STUDY
        )
        from data.mock_data.payer_policies import get_policy_for_procedure
        
        print("\n✅ All imports successful!")
        return True
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_basic_functionality():
    """Test basic functionality without API calls"""
    
    print("\nTesting basic functionality...")
    
    try:
        from models import PatientInfo, ProviderInfo
        
        # Test model creation
        patient = PatientInfo(
            patient_id="TEST-001",
            name="Test Patient",
            date_of_birth="01/01/2000",
            gender="Male",
            insurance_plan="TestInsurance",
            member_id="TEST-12345"
        )
        print("  ✓ Patient model created")
        
        provider = ProviderInfo(
            provider_id="TEST-DOC",
            name="Dr. Test",
            npi="1234567890",
            specialty="Test Specialty",
            facility="Test Facility",
            phone="555-0000"
        )
        print("  ✓ Provider model created")
        
        # Test policy retrieval
        from data.mock_data.payer_policies import get_policy_for_procedure
        policy = get_policy_for_procedure("72148", "UnitedHealth")
        assert len(policy) > 100, "Policy should have content"
        print("  ✓ Policy retrieval works")
        
        print("\n✅ Basic functionality tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Functionality test failed: {e}")
        return False


def main():
    """Run all validation tests"""
    
    print("="*60)
    print("AutoAuth Agent - Validation Test")
    print("="*60 + "\n")
    
    # Test imports
    imports_ok = test_imports()
    
    if not imports_ok:
        print("\n⚠️  Fix import errors before proceeding")
        sys.exit(1)
    
    # Test basic functionality
    functionality_ok = test_basic_functionality()
    
    if not functionality_ok:
        print("\n⚠️  Basic functionality issues detected")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("✅ All validation tests passed!")
    print("="*60)
    print("\nNext steps:")
    print("1. Set up your .env file with ANTHROPIC_API_KEY")
    print("2. Run: python demo.py mri")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()