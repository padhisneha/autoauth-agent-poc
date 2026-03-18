"""
Workflow Orchestrator - Coordinates all agents using LangGraph
"""
from __future__ import annotations

import logging
import operator
import time
from datetime import datetime
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, StateGraph

from models import (
    AppealLetter,
    ApprovalLikelihood,
    ClinicalEvidence,
    PAStatus,
    PolicyAnalysis,
    PriorAuthorizationRequest,
    PriorAuthorizationResponse,
)
from agents import ClinicalReaderAgent, PolicyAgent, SubmissionAgent, AppealAgent
from agents.clinical_reader import ClinicalExtractionError, ClinicalValidationError
from agents.policy_agent import PolicyAnalysisError, PolicyNotFoundError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workflow state
# ---------------------------------------------------------------------------


class PAWorkflowState(TypedDict):
    """State object passed between LangGraph nodes."""

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
    # Annotated with operator.add so LangGraph merges lists from parallel nodes correctly.
    # IMPORTANT: nodes must RETURN new errors via the state dict, never mutate in-place.
    errors: Annotated[list[str], operator.add]
    needs_human_review: bool
    review_reason: str | None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class PAWorkflowOrchestrator:
    """
    Orchestrates the entire prior authorization workflow using LangGraph.

    Node contract
    -------------
    Every node receives a *copy* of the state and returns a (possibly partial)
    dict.  LangGraph merges the returned dict back into the state.  Because
    ``errors`` uses ``operator.add`` as its reducer, nodes must *never* mutate
    ``state["errors"]`` in place; they must return ``{"errors": [...new...]}``
    instead.
    """

    def __init__(self) -> None:
        self.clinical_reader = ClinicalReaderAgent()
        self.policy_agent = PolicyAgent()
        self.submission_agent = SubmissionAgent()
        self.appeal_agent = AppealAgent()

        self.workflow = self._build_workflow()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_workflow(self) -> StateGraph:
        wf = StateGraph(PAWorkflowState)

        wf.add_node("extract_clinical", self._extract_clinical_evidence)
        wf.add_node("check_policy", self._check_policy_compliance)
        wf.add_node("create_submission", self._create_submission)
        wf.add_node("generate_appeal", self._generate_appeal)
        wf.add_node("human_review", self._flag_for_human_review)

        wf.set_entry_point("extract_clinical")
        wf.add_edge("extract_clinical", "check_policy")
        wf.add_conditional_edges(
            "check_policy",
            self._route_after_policy_check,
            {"submit": "create_submission", "review": "human_review", "appeal": "generate_appeal"},
        )
        wf.add_edge("create_submission", END)
        wf.add_edge("human_review", END)
        wf.add_edge("generate_appeal", END)

        return wf.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _extract_clinical_evidence(self, state: PAWorkflowState) -> dict:
        """Node 1 — extract clinical evidence from patient notes."""
        logger.info("[WORKFLOW] Step 1: Extracting clinical evidence…")

        request: PriorAuthorizationRequest = state["request"]

        try:
            clinical_evidence = self.clinical_reader.extract_clinical_evidence(
                patient_notes=request.patient_notes,
                procedure_code=request.requested_service,
            )
        except (ClinicalExtractionError, ClinicalValidationError) as exc:
            logger.error("[WORKFLOW] Clinical extraction failed: %s", exc)
            return {
                "errors": [f"Clinical extraction failed: {exc}"],
                "needs_human_review": True,
                "review_reason": "Failed to extract clinical evidence — manual review required.",
            }
        except Exception as exc:
            logger.exception("[WORKFLOW] Unexpected error in clinical extraction")
            return {
                "errors": [f"Unexpected clinical extraction error: {exc}"],
                "needs_human_review": True,
                "review_reason": "Unexpected error during clinical extraction.",
            }

        validation = self.clinical_reader.validate_completeness(clinical_evidence)
        new_errors: list[str] = []

        if not validation["is_complete"]:
            missing = ", ".join(validation["missing_elements"])
            new_errors.append(f"Incomplete clinical documentation: {missing}")
            logger.warning("[WORKFLOW] Incomplete documentation: %s", missing)
        else:
            logger.info("[WORKFLOW] ✓ Clinical evidence extracted successfully")

        return {"clinical_evidence": clinical_evidence, "errors": new_errors}

    def _check_policy_compliance(self, state: PAWorkflowState) -> dict:
        """Node 2 — check policy compliance."""
        logger.info("[WORKFLOW] Step 2: Checking policy compliance…")

        # Guard: if extraction already failed, skip this node
        if state.get("needs_human_review") and state.get("clinical_evidence") is None:
            logger.warning("[WORKFLOW] Skipping policy check — no clinical evidence available.")
            return {}

        clinical_evidence: ClinicalEvidence | None = state.get("clinical_evidence")
        if clinical_evidence is None:
            return {
                "errors": ["Policy check skipped: clinical_evidence is None"],
                "needs_human_review": True,
                "review_reason": "No clinical evidence available for policy evaluation.",
            }

        request: PriorAuthorizationRequest = state["request"]

        try:
            policy_analysis = self.policy_agent.evaluate_against_policy(
                clinical_evidence=clinical_evidence,
                insurance_plan=request.patient_info.insurance_plan,
            )
        except PolicyNotFoundError as exc:
            logger.warning("[WORKFLOW] Policy not found: %s", exc)
            # Not fatal — route to human review with a clear reason
            return {
                "errors": [f"Policy not found: {exc}"],
                "needs_human_review": True,
                "review_reason": str(exc),
            }
        except PolicyAnalysisError as exc:
            logger.error("[WORKFLOW] Policy analysis failed: %s", exc)
            return {
                "errors": [f"Policy analysis failed: {exc}"],
                "needs_human_review": True,
                "review_reason": "Failed to analyse policy compliance — manual review required.",
            }
        except Exception as exc:
            logger.exception("[WORKFLOW] Unexpected error in policy check")
            return {
                "errors": [f"Unexpected policy analysis error: {exc}"],
                "needs_human_review": True,
                "review_reason": "Unexpected error during policy analysis.",
            }

        # Check red flags (informational — never blocks the workflow)
        try:
            red_flag_check = self.policy_agent.check_red_flags(clinical_evidence)
            if red_flag_check["has_red_flags"]:
                logger.warning(
                    "[WORKFLOW] Red flags detected: %s", red_flag_check["red_flags"]
                )
        except Exception as exc:
            logger.warning("[WORKFLOW] Red-flag check raised: %s", exc)

        logger.info(
            "[WORKFLOW] ✓ Policy analysis complete: %s likelihood",
            policy_analysis.approval_likelihood.value.upper(),
        )

        return {"policy_analysis": policy_analysis}

    def _route_after_policy_check(
        self, state: PAWorkflowState
    ) -> Literal["submit", "review", "appeal"]:
        """Decision — route based on policy analysis results."""
        if state.get("needs_human_review"):
            return "review"

        policy_analysis: PolicyAnalysis | None = state.get("policy_analysis")
        if policy_analysis is None:
            return "review"

        if policy_analysis.approval_likelihood == ApprovalLikelihood.HIGH:
            logger.info("[WORKFLOW] Routing → submission (HIGH likelihood)")
            return "submit"
        if policy_analysis.approval_likelihood == ApprovalLikelihood.LOW:
            logger.info("[WORKFLOW] Routing → appeal (LOW likelihood)")
            return "appeal"

        logger.info("[WORKFLOW] Routing → human review (MEDIUM likelihood)")
        return "review"

    def _create_submission(self, state: PAWorkflowState) -> dict:
        """Node 3a — create and submit the authorization request."""
        logger.info("[WORKFLOW] Step 3: Creating submission…")

        request = state["request"]
        clinical_evidence = state.get("clinical_evidence")
        policy_analysis = state.get("policy_analysis")

        # Both must be present to build a submission
        if clinical_evidence is None or policy_analysis is None:
            return {
                "errors": ["Cannot create submission: missing clinical or policy data"],
                "needs_human_review": True,
                "review_reason": "Submission skipped due to missing upstream data.",
            }

        try:
            fhir_request = self.submission_agent.create_fhir_service_request(
                patient_info=request.patient_info,
                provider_info=request.provider_info,
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis,
            )
        except Exception as exc:
            logger.error("[WORKFLOW] FHIR resource creation failed: %s", exc)
            return {
                "errors": [f"Submission creation failed: {exc}"],
                "needs_human_review": True,
                "review_reason": "Failed to create FHIR submission resource.",
            }

        validation = self.submission_agent.validate_fhir_request(fhir_request)
        new_errors: list[str] = []
        if not validation["is_valid"]:
            new_errors.extend(validation["errors"])
            logger.warning("[WORKFLOW] FHIR validation errors: %s", validation["errors"])
        if validation.get("warnings"):
            for w in validation["warnings"]:
                logger.warning("[WORKFLOW] FHIR warning: %s", w)

        try:
            submission_result = self.submission_agent.submit_authorization_request(fhir_request)
            logger.info("[WORKFLOW] ✓ Submitted: %s", submission_result["submission_id"])
        except Exception as exc:
            logger.error("[WORKFLOW] Submission call failed: %s", exc)
            new_errors.append(f"Submission call failed: {exc}")
            return {
                "fhir_request": fhir_request,
                "errors": new_errors,
                "needs_human_review": True,
                "review_reason": "Authorization request could not be submitted to payer.",
            }

        return {"fhir_request": fhir_request, "status": PAStatus.PENDING, "errors": new_errors}

    def _generate_appeal(self, state: PAWorkflowState) -> dict:
        """Node 3b — generate an appeal letter for a likely denial."""
        logger.info("[WORKFLOW] Step 3: Generating appeal preparation…")

        request = state["request"]
        clinical_evidence = state.get("clinical_evidence")
        policy_analysis = state.get("policy_analysis")

        if clinical_evidence is None or policy_analysis is None:
            return {
                "errors": ["Cannot generate appeal: missing clinical or policy data"],
                "status": PAStatus.NEEDS_REVIEW,
                "needs_human_review": True,
                "review_reason": "Appeal skipped due to missing upstream data.",
            }

        # Assess appeal strength (informational — non-fatal if it fails)
        try:
            appeal_strength = self.appeal_agent.assess_appeal_strength(
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis,
                denial_reason="Anticipated denial based on policy analysis",
            )
            logger.info(
                "[WORKFLOW] Appeal strength: %s (%s/100)",
                appeal_strength["rating"],
                appeal_strength["strength_score"],
            )
        except Exception as exc:
            logger.warning("[WORKFLOW] Could not assess appeal strength: %s", exc)
            appeal_strength = {"rating": "UNKNOWN", "strength_score": 0, "recommendation": ""}

        try:
            appeal_letter = self.appeal_agent.generate_appeal_letter(
                denial_reason=(
                    "Based on preliminary analysis, approval likelihood is LOW. "
                    "Preparing preemptive appeal."
                ),
                clinical_evidence=clinical_evidence,
                policy_analysis=policy_analysis,
                patient_name=request.patient_info.name,
                provider_name=request.provider_info.name,
                insurance_plan=request.patient_info.insurance_plan,
            )
        except Exception as exc:
            logger.error("[WORKFLOW] Appeal letter generation failed: %s", exc)
            return {
                "errors": [f"Appeal generation failed: {exc}"],
                "status": PAStatus.NEEDS_REVIEW,
                "needs_human_review": True,
                "review_reason": "Failed to generate appeal letter — manual review required.",
            }

        review_reason = (
            f"Low approval likelihood. Appeal prepared. "
            f"{appeal_strength.get('recommendation', '')}"
        )

        logger.info(
            "[WORKFLOW] ✓ Appeal letter generated (%d rebuttal points)",
            len(appeal_letter.rebuttal_points),
        )

        return {
            "appeal_letter": appeal_letter,
            "status": PAStatus.NEEDS_REVIEW,
            "needs_human_review": True,
            "review_reason": review_reason,
        }

    def _flag_for_human_review(self, state: PAWorkflowState) -> dict:
        """Node 3c — flag the case for human review."""
        logger.info("[WORKFLOW] Step 3: Flagging for human review…")

        review_reason = state.get("review_reason") or (
            "Medium approval likelihood — requires clinical judgment."
        )
        logger.info("[WORKFLOW] 👤 Human review required: %s", review_reason)

        return {
            "status": PAStatus.NEEDS_REVIEW,
            "needs_human_review": True,
            "review_reason": review_reason,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process_authorization_request(
        self, request: PriorAuthorizationRequest
    ) -> PriorAuthorizationResponse:
        """
        Process a complete prior authorization request through the LangGraph workflow.

        Args:
            request: Fully populated ``PriorAuthorizationRequest``.

        Returns:
            ``PriorAuthorizationResponse`` with all processing results.
        """
        if request is None:
            raise ValueError("request must not be None")

        logger.info(
            "=== Processing PA request %s | Patient: %s | Procedure: %s ===",
            request.request_id,
            request.patient_info.name,
            request.requested_service,
        )

        start_time = time.time()

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
            "review_reason": None,
        }

        try:
            final_state = self.workflow.invoke(initial_state)
        except Exception as exc:
            logger.exception("Workflow execution raised an unhandled exception")
            final_state = dict(initial_state)
            final_state["errors"] = initial_state["errors"] + [
                f"Workflow execution error: {exc}"
            ]
            final_state["status"] = PAStatus.NEEDS_REVIEW
            final_state["needs_human_review"] = True
            final_state["review_reason"] = "Unhandled workflow execution error."

        processing_time = time.time() - start_time

        response = PriorAuthorizationResponse(
            request_id=request.request_id,
            status=final_state.get("status", PAStatus.NEEDS_REVIEW),
            clinical_evidence=final_state.get("clinical_evidence"),
            policy_analysis=final_state.get("policy_analysis"),
            fhir_request=final_state.get("fhir_request"),
            appeal_letter=final_state.get("appeal_letter"),
            processing_time_seconds=processing_time,
            needs_human_review=final_state.get("needs_human_review", True),
            review_reason=final_state.get("review_reason"),
            errors=final_state.get("errors", []),
            completed_at=datetime.now(),
        )

        logger.info(
            "=== Completed %s | Status: %s | %.2fs | Errors: %d ===",
            request.request_id,
            response.status.value.upper(),
            processing_time,
            len(response.errors),
        )

        return response
