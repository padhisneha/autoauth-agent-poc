"""
Submission Agent - Generates FHIR resources and authorization forms
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from models import (
    ClinicalEvidence,
    PolicyAnalysis,
    PatientInfo,
    ProviderInfo,
)
from llm_client import UniversalLLMClient, LLMError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SubmissionError(Exception):
    """Raised when the authorization request cannot be built or submitted."""


class FHIRValidationError(SubmissionError):
    """Raised when a FHIR resource fails structural validation."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class SubmissionAgent:
    """
    Builds FHIR ServiceRequest resources and submits prior authorization requests.

    FHIR library imports are deferred to method call time so that an absent
    ``fhir.resources`` package does not crash the entire agents package at
    import time.
    """

    def __init__(self) -> None:
        self.client = UniversalLLMClient()

    # ------------------------------------------------------------------
    # FHIR resource creation
    # ------------------------------------------------------------------

    def create_fhir_service_request(
        self,
        patient_info: PatientInfo,
        provider_info: ProviderInfo,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis,
    ) -> dict[str, Any]:
        """
        Create a FHIR ServiceRequest resource dict for prior authorization.

        Raises:
            ValueError:      Any required argument is None.
            SubmissionError: Resource could not be assembled.
        """
        # Guard required inputs
        if patient_info is None:
            raise ValueError("patient_info must not be None")
        if provider_info is None:
            raise ValueError("provider_info must not be None")
        if clinical_evidence is None:
            raise ValueError("clinical_evidence must not be None")
        if policy_analysis is None:
            raise ValueError("policy_analysis must not be None")

        try:
            procedure_code = (
                clinical_evidence.procedure_codes[0]
                if clinical_evidence.procedure_codes
                else "UNKNOWN"
            )
            if procedure_code == "UNKNOWN":
                logger.warning(
                    "[SubmissionAgent] No procedure codes on clinical_evidence; "
                    "using 'UNKNOWN' as CPT code."
                )

            reason_codes = [
                {
                    "coding": [{
                        "system": "http://hl7.org/fhir/sid/icd-10",
                        "code": dx,
                        "display": f"Diagnosis: {dx}",
                    }]
                }
                for dx in clinical_evidence.diagnosis_codes
            ]

            service_request: dict[str, Any] = {
                "resourceType": "ServiceRequest",
                "id": f"pa-request-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "status": "active",
                "intent": "order",
                "priority": (
                    "urgent"
                    if policy_analysis.approval_likelihood.value == "high"
                    else "routine"
                ),
                "code": {
                    "coding": [{
                        "system": "http://www.ama-assn.org/go/cpt",
                        "code": procedure_code,
                        "display": f"CPT {procedure_code}",
                    }],
                    "text": f"Prior Authorization Request for {procedure_code}",
                },
                "subject": {
                    "reference": f"Patient/{patient_info.patient_id}",
                    "display": patient_info.name,
                },
                "encounter": {
                    "reference": (
                        f"Encounter/{patient_info.patient_id}"
                        f"-{datetime.now().strftime('%Y%m%d')}"
                    )
                },
                "authoredOn": datetime.now().isoformat(),
                "requester": {
                    "reference": f"Practitioner/{provider_info.provider_id}",
                    "display": provider_info.name,
                    "identifier": {
                        "system": "http://hl7.org/fhir/sid/us-npi",
                        "value": provider_info.npi,
                    },
                },
                "reasonCode": reason_codes,
                "reasonReference": [],
                "insurance": [{
                    "reference": f"Coverage/{patient_info.member_id}",
                    "display": patient_info.insurance_plan,
                }],
                "supportingInfo": self._build_supporting_info(
                    clinical_evidence, policy_analysis
                ),
                "note": [{
                    "text": self._generate_clinical_summary(
                        clinical_evidence, policy_analysis
                    )
                }],
            }

            return service_request

        except (ValueError, SubmissionError):
            raise
        except Exception as exc:
            logger.error("[SubmissionAgent] Failed to build FHIR resource: %s", exc)
            raise SubmissionError(
                f"Unexpected error building FHIR ServiceRequest: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # FHIR validation
    # ------------------------------------------------------------------

    def validate_fhir_request(self, fhir_request: dict[str, Any]) -> dict[str, Any]:
        """
        Validate a FHIR ServiceRequest dict for required fields and structure.

        Returns:
            ``{"is_valid": bool, "errors": list[str], "warnings": list[str]}``
        """
        if not isinstance(fhir_request, dict):
            return {
                "is_valid": False,
                "errors": [
                    f"fhir_request must be a dict, got {type(fhir_request).__name__}"
                ],
                "warnings": [],
            }

        errors: list[str] = []
        warnings: list[str] = []

        required_fields = ["resourceType", "status", "intent", "code", "subject", "requester"]
        for field in required_fields:
            if field not in fhir_request:
                errors.append(f"Missing required field: '{field}'")

        code = fhir_request.get("code")
        if isinstance(code, dict):
            if "coding" not in code:
                errors.append("Missing 'code.coding'")
            elif not isinstance(code["coding"], list) or len(code["coding"]) == 0:
                errors.append("'code.coding' must be a non-empty list")
        elif "code" in fhir_request:
            errors.append("'code' must be a dict (CodeableConcept)")

        if not fhir_request.get("reasonCode"):
            warnings.append(
                "No diagnosis codes (reasonCode) provided — "
                "payer may reject without ICD-10 codes."
            )
        if not fhir_request.get("supportingInfo"):
            warnings.append(
                "No supportingInfo provided — consider adding clinical documentation references."
            )

        return {"is_valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    # ------------------------------------------------------------------
    # Submission (mock)
    # ------------------------------------------------------------------

    def submit_authorization_request(
        self,
        fhir_request: dict[str, Any],
        payer_endpoint: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Submit an authorization request to the payer FHIR endpoint.

        In this POC the submission is simulated; replace with a real HTTP POST
        in production.

        Raises:
            ValueError:      *fhir_request* is empty or not a dict.
            SubmissionError: Simulated or real submission failure.
        """
        if not isinstance(fhir_request, dict) or not fhir_request:
            raise ValueError("fhir_request must be a non-empty dict")

        from config import settings  # local import avoids circular dep

        endpoint = payer_endpoint or settings.fhir_base_url

        # --- Real submission would go here ---
        # try:
        #     import httpx
        #     resp = httpx.post(endpoint, json=fhir_request, timeout=30)
        #     resp.raise_for_status()
        # except httpx.HTTPStatusError as exc:
        #     raise SubmissionError(f"Payer endpoint returned {exc.response.status_code}") from exc
        # except httpx.RequestError as exc:
        #     raise SubmissionError(f"Network error submitting to {endpoint}: {exc}") from exc

        submission_id = f"SUB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(
            "[SubmissionAgent] Request %s submitted to %s (simulated)",
            submission_id,
            endpoint,
        )

        return {
            "submitted": True,
            "submission_id": submission_id,
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "status": "pending_review",
            "estimated_response_time": "2-5 business days",
        }

    # ------------------------------------------------------------------
    # LLM-generated form
    # ------------------------------------------------------------------

    def generate_authorization_form(
        self,
        patient_info: PatientInfo,
        provider_info: ProviderInfo,
        clinical_evidence: ClinicalEvidence,
        policy_analysis: PolicyAnalysis,
    ) -> str:
        """
        Generate a human-readable authorization form using the LLM.

        Raises:
            SubmissionError: LLM call failed.
        """
        prompt = (
            f"Generate a professional Prior Authorization Request Form with the "
            f"following information:\n\n"
            f"PATIENT INFORMATION:\n"
            f"- Name: {patient_info.name}\n"
            f"- Patient ID: {patient_info.patient_id}\n"
            f"- Date of Birth: {patient_info.date_of_birth}\n"
            f"- Gender: {patient_info.gender}\n"
            f"- Insurance: {patient_info.insurance_plan}\n"
            f"- Member ID: {patient_info.member_id}\n\n"
            f"PROVIDER INFORMATION:\n"
            f"- Provider: {provider_info.name}\n"
            f"- NPI: {provider_info.npi}\n"
            f"- Specialty: {provider_info.specialty}\n"
            f"- Facility: {provider_info.facility}\n"
            f"- Phone: {provider_info.phone}\n\n"
            f"REQUESTED SERVICE:\n"
            f"- Procedure Codes: {', '.join(clinical_evidence.procedure_codes)}\n"
            f"- Diagnosis Codes: {', '.join(clinical_evidence.diagnosis_codes)}\n\n"
            f"CLINICAL JUSTIFICATION:\n"
            + "\n".join(f"- {e}" for e in clinical_evidence.supporting_evidence) + "\n\n"
            f"POLICY ANALYSIS:\n"
            f"- Approval Likelihood: {policy_analysis.approval_likelihood.value.upper()}\n"
            f"- Criteria Met: {len(policy_analysis.met_criteria)}\n\n"
            f"Generate a professional, formatted Prior Authorization Request Form."
        )

        try:
            return self.client.generate(prompt, max_tokens=2048)
        except LLMError as exc:
            logger.error("[SubmissionAgent] LLM call failed for form generation: %s", exc)
            raise SubmissionError(
                f"Failed to generate authorization form: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_supporting_info(
        self,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis,
    ) -> list[dict[str, Any]]:
        info: list[dict[str, Any]] = []

        if evidence.prior_treatments:
            info.append({
                "reference": "DocumentReference/conservative-treatment-history",
                "display": (
                    "Conservative treatments: "
                    + ", ".join(evidence.prior_treatments[:3])
                ),
            })

        if evidence.severity_indicators:
            info.append({
                "reference": "DocumentReference/severity-indicators",
                "display": (
                    "Clinical indicators: "
                    + ", ".join(evidence.severity_indicators[:2])
                ),
            })

        info.append({
            "reference": "DocumentReference/policy-analysis",
            "display": (
                f"Policy Analysis: {analysis.approval_likelihood.value} likelihood"
            ),
        })

        return info

    def _generate_clinical_summary(
        self,
        evidence: ClinicalEvidence,
        analysis: PolicyAnalysis,
    ) -> str:
        parts: list[str] = []

        if evidence.diagnosis_codes:
            parts.append(f"DIAGNOSES: {', '.join(evidence.diagnosis_codes)}")
        if evidence.symptoms:
            parts.append(f"SYMPTOMS: {'; '.join(evidence.symptoms[:3])}")
        if evidence.prior_treatments:
            parts.append(f"CONSERVATIVE TREATMENT: {'; '.join(evidence.prior_treatments[:3])}")
        if evidence.severity_indicators:
            parts.append(f"CLINICAL INDICATORS: {'; '.join(evidence.severity_indicators[:2])}")
        if evidence.supporting_evidence:
            parts.append(f"CLINICAL FINDINGS: {'; '.join(evidence.supporting_evidence[:3])}")

        parts.append(
            f"POLICY ANALYSIS: {analysis.approval_likelihood.value.upper()} "
            f"likelihood of approval"
        )
        parts.append(f"MET CRITERIA: {len(analysis.met_criteria)} criteria satisfied")

        if analysis.missing_criteria:
            parts.append(
                f"MISSING CRITERIA: {len(analysis.missing_criteria)} criteria need attention"
            )

        return "\n\n".join(parts)
