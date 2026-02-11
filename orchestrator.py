"""
Workflow Orchestrator - Coordinates all agents using LangGraph
"""
from typing import TypedDict, Annotated, Literal
import operator
from langgraph.graph import StateGraph, END
import time
from datetime import datetime

from models import (
    PriorAuthorizationRequest,
    PriorAuthorizationResponse,
    ClinicalEvidence,
    PolicyAnalysis,
    PAStatus,
    ApprovalLikelihood,
    AppealLetter
)
from agents import ClinicalReaderAgent, PolicyAgent, SubmissionAgent, AppealAgent


class PAWorkflowState(TypedDict):
    """State object for the PA workflow"""
    # Input
    request: PriorAuthorizationRequest
    
    # Processing artifacts
    clinical_evidence: ClinicalEvidence | None
    policy_analysis: PolicyAnalysis | None
    fhir_request: dict | None
    appeal_letter: AppealLetter | None
    
    # Metadata
    start_time: float
    status: PAStatus
    errors: Annotated[list[str], operator.add]
    needs_human_review: bool
    review_reason: str | None


class PAWorkflowOrchestrator:
    """
    Orchestrates the entire prior authorization workflow using LangGraph
    """
    
    def __init__(self):
        self.clinical_reader = ClinicalReaderAgent()
        self.policy_agent = PolicyAgent()
        self.submission_agent = SubmissionAgent()
        self.appeal_agent = AppealAgent()
        
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow"""
        
        # Create the graph
        workflow = StateGraph(PAWorkflowState)
        
        # Add nodes for each agent
        workflow.add_node("extract_clinical", self._extract_clinical_evidence)
        workflow.add_node("check_policy", self._check_policy_compliance)
        workflow.add_node("create_submission", self._create_submission)
        workflow.add_node("generate_appeal", self._generate_appeal)
        workflow.add_node("human_review", self._flag_for_human_review)
        
        # Define the workflow edges
        workflow.set_entry_point("extract_clinical")
        
        # After extraction, always check policy
        workflow.add_edge("extract_clinical", "check_policy")
        
        # After policy check, decide next step
        workflow.add_conditional_edges(
            "check_policy",
            self._route_after_policy_check,
            {
                "submit": "create_submission",
                "review": "human_review",
                "appeal": "generate_appeal"
            }
        )
        
        # After submission, end
        workflow.add_edge("create_submission", END)
        
        # After human review flag, end
        workflow.add_edge("human_review", END)
        
        # After appeal generation, end
        workflow.add_edge("generate_appeal", END)
        
        return workflow.compile()
    
    def _extract_clinical_evidence(self, state: PAWorkflowState) -> PAWorkflowState:
        """Node: Extract clinical evidence from patient notes"""
        print("[WORKFLOW] Step 1: Extracting clinical evidence...")
        
        try:
            request = state["request"]
            
            # Use first procedure code if multiple
            procedure_code = request.requested_service
            
            clinical_evidence = self.clinical_reader.extract_clinical_evidence(
                patient_notes=request.patient_notes,
                procedure_code=procedure_code
            )
            
            state["clinical_evidence"] = clinical_evidence
            
            # Validate completeness
            validation = self.clinical_reader.validate_completeness(clinical_evidence)
            if not validation["is_complete"]:
                state["errors"].append(f"Incomplete clinical documentation: {', '.join(validation['missing_elements'])}")
                print(f"  ⚠️  Warning: {validation['missing_elements']}")
            else:
                print(f"  ✓ Clinical evidence extracted successfully")
            
        except Exception as e:
            state["errors"].append(f"Clinical extraction failed: {str(e)}")
            state["needs_human_review"] = True
            state["review_reason"] = "Failed to extract clinical evidence"
            print(f"  ✗ Error: {e}")
        
        return state
    
    def _check_policy_compliance(self, state: PAWorkflowState) -> PAWorkflowState:
        """Node: Check policy compliance"""
        print("[WORKFLOW] Step 2: Checking policy compliance...")
        
        try:
            clinical_evidence = state["clinical_evidence"]
            request = state["request"]
            
            policy_analysis = self.policy_agent.evaluate_against_policy(
                clinical_evidence=clinical_evidence,
                insurance_plan=request.patient_info.insurance_plan
            )
            
            state["policy_analysis"] = policy_analysis
            
            # Check for red flags
            red_flag_check = self.policy_agent.check_red_flags(clinical_evidence)
            if red_flag_check["has_red_flags"]:
                print(f"  🚩 Red flags detected: {red_flag_check['red_flags']}")
            
            print(f"  ✓ Policy analysis complete: {policy_analysis.approval_likelihood.value.upper()} likelihood")
            
        except Exception as e:
            state["errors"].append(f"Policy analysis failed: {str(e)}")
            state["needs_human_review"] = True
            state["review_reason"] = "Failed to analyze policy compliance"
            print(f"  ✗ Error: {e}")
        
        return state
    
    def _route_after_policy_check(self, state: PAWorkflowState) -> Literal["submit", "review", "appeal"]:
        """Decision: Route based on policy analysis results"""
        
        # If errors occurred, go to human review
        if state.get("needs_human_review"):
            return "review"
        
        policy_analysis = state.get("policy_analysis")
        
        if not policy_analysis:
            return "review"
        
        # High likelihood -> proceed to submission
        if policy_analysis.approval_likelihood == ApprovalLikelihood.HIGH:
            print("[WORKFLOW] Routing: HIGH approval likelihood → Proceeding to submission")
            return "submit"
        
        # Low likelihood -> generate appeal preparation
        elif policy_analysis.approval_likelihood == ApprovalLikelihood.LOW:
            print("[WORKFLOW] Routing: LOW approval likelihood → Preparing appeal")
            return "appeal"
        
        # Medium likelihood -> human review
        else:
            print("[WORKFLOW] Routing: MEDIUM approval likelihood → Flagging for human review")
            return "review"
    
    def _create_submission(self, state: PAWorkflowState) -> PAWorkflowState:
        """Node: Create and submit authorization request"""
        print("[WORKFLOW] Step 3: Creating submission...")
        
        try:
            request = state["request"]
            clinical_evidence = state["clinical_evidence"]
            policy_analysis = state["policy_analysis"]
            
            # Create FHIR ServiceRequest
            fhir_request = self.submission_agent.create_fhir_service_request(
                patient_info=request.patient_info,
                provider_info=request.provider_info,
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis
            )
            
            state["fhir_request"] = fhir_request
            
            # Validate FHIR request
            validation = self.submission_agent.validate_fhir_request(fhir_request)
            if not validation["is_valid"]:
                state["errors"].extend(validation["errors"])
                print(f"  ⚠️  FHIR validation errors: {validation['errors']}")
            
            # Submit (mock for POC)
            submission_result = self.submission_agent.submit_authorization_request(fhir_request)
            
            state["status"] = PAStatus.PENDING
            print(f"  ✓ Submission created: {submission_result['submission_id']}")
            
        except Exception as e:
            state["errors"].append(f"Submission creation failed: {str(e)}")
            state["needs_human_review"] = True
            state["review_reason"] = "Failed to create submission"
            print(f"  ✗ Error: {e}")
        
        return state
    
    def _generate_appeal(self, state: PAWorkflowState) -> PAWorkflowState:
        """Node: Generate appeal letter for likely denial"""
        print("[WORKFLOW] Step 3: Generating appeal preparation...")
        
        try:
            request = state["request"]
            clinical_evidence = state["clinical_evidence"]
            policy_analysis = state["policy_analysis"]
            
            # Assess appeal strength
            appeal_strength = self.appeal_agent.assess_appeal_strength(
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis,
                denial_reason="Anticipated denial based on policy analysis"
            )
            
            print(f"  📊 Appeal strength: {appeal_strength['rating']} ({appeal_strength['strength_score']}/100)")
            
            # Generate appeal letter
            appeal_letter = self.appeal_agent.generate_appeal_letter(
                denial_reason="Based on preliminary analysis, approval likelihood is LOW. Preparing preemptive appeal.",
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis,
                patient_name=request.patient_info.name,
                provider_name=request.provider_info.name,
                insurance_plan=request.patient_info.insurance_plan
            )
            
            state["appeal_letter"] = appeal_letter
            state["status"] = PAStatus.NEEDS_REVIEW
            state["needs_human_review"] = True
            state["review_reason"] = f"Low approval likelihood. Appeal prepared. {appeal_strength['recommendation']}"
            
            print(f"  ✓ Appeal letter generated with {len(appeal_letter.rebuttal_points)} rebuttal points")
            
        except Exception as e:
            state["errors"].append(f"Appeal generation failed: {str(e)}")
            print(f"  ✗ Error: {e}")
        
        return state
    
    def _flag_for_human_review(self, state: PAWorkflowState) -> PAWorkflowState:
        """Node: Flag case for human review"""
        print("[WORKFLOW] Step 3: Flagging for human review...")
        
        state["status"] = PAStatus.NEEDS_REVIEW
        state["needs_human_review"] = True
        
        if not state.get("review_reason"):
            state["review_reason"] = "Medium approval likelihood - requires clinical judgment"
        
        print(f"  👤 Human review required: {state['review_reason']}")
        
        return state
    
    def process_authorization_request(
        self,
        request: PriorAuthorizationRequest
    ) -> PriorAuthorizationResponse:
        """
        Process a complete prior authorization request through the workflow
        
        Args:
            request: PriorAuthorizationRequest with all required information
            
        Returns:
            PriorAuthorizationResponse with processing results
        """
        
        print(f"\n{'='*80}")
        print(f"PROCESSING PRIOR AUTHORIZATION REQUEST: {request.request_id}")
        print(f"Patient: {request.patient_info.name}")
        print(f"Procedure: {request.requested_service}")
        print(f"{'='*80}\n")
        
        start_time = time.time()
        
        # Initialize state
        initial_state: PAWorkflowState = {
            "request": request,
            "clinical_evidence": None,
            "policy_analysis": None,
            "fhir_request": None,
            "appeal_letter": None,
            "start_time": start_time,
            "status": PAStatus.PENDING,
            "errors": [],
            "needs_human_review": False,
            "review_reason": None
        }
        
        # Run the workflow
        try:
            final_state = self.workflow.invoke(initial_state)
        except Exception as e:
            print(f"\n✗ Workflow execution failed: {e}")
            final_state = initial_state
            final_state["errors"].append(f"Workflow execution error: {str(e)}")
            final_state["status"] = PAStatus.NEEDS_REVIEW
            final_state["needs_human_review"] = True
            final_state["review_reason"] = "Workflow execution error"
        
        processing_time = time.time() - start_time
        
        # Build response
        response = PriorAuthorizationResponse(
            request_id=request.request_id,
            status=final_state["status"],
            clinical_evidence=final_state.get("clinical_evidence"),
            policy_analysis=final_state.get("policy_analysis"),
            fhir_request=final_state.get("fhir_request"),
            appeal_letter=final_state.get("appeal_letter"),
            processing_time_seconds=processing_time,
            needs_human_review=final_state["needs_human_review"],
            review_reason=final_state.get("review_reason"),
            errors=final_state["errors"],
            completed_at=datetime.now()
        )
        
        print(f"\n{'='*80}")
        print(f"PROCESSING COMPLETE")
        print(f"Status: {response.status.value.upper()}")
        print(f"Processing Time: {processing_time:.2f} seconds")
        if response.needs_human_review:
            print(f"⚠️  Human Review Required: {response.review_reason}")
        if response.errors:
            print(f"❌ Errors: {len(response.errors)}")
        print(f"{'='*80}\n")
        
        return response