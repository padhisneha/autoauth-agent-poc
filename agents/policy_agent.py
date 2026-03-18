"""
Policy Agent - Evaluates clinical evidence against payer coverage policies
"""
from __future__ import annotations

import logging
from typing import Any

from models import ClinicalEvidence, PolicyAnalysis, ApprovalLikelihood
from llm_client import UniversalLLMClient, LLMError
from utils import safe_json_parse, JSONParseError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class PolicyAnalysisError(Exception):
    """Raised when policy analysis cannot be completed."""


class PolicyNotFoundError(PolicyAnalysisError):
    """No policy document exists for the requested procedure / plan combination."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PolicyAgent:
    """
    Retrieves payer policies and determines whether clinical evidence meets
    coverage criteria.
    """

    def __init__(self) -> None:
        self.client = UniversalLLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_against_policy(
        self,
        clinical_evidence: ClinicalEvidence,
        insurance_plan: str = "UnitedHealth",
    ) -> PolicyAnalysis:
        """
        Evaluate clinical evidence against payer policy criteria.

        Args:
            clinical_evidence: Extracted clinical evidence.
            insurance_plan:    Name of the insurance plan.

        Returns:
            ``PolicyAnalysis`` with approval likelihood and reasoning.

        Raises:
            ValueError:          *clinical_evidence* is None or has no procedure codes.
            PolicyNotFoundError: No policy found for the procedure/plan combination.
            PolicyAnalysisError: LLM call or JSON parse failed.
        """
        if clinical_evidence is None:
            raise ValueError("clinical_evidence must not be None")

        # Resolve procedure code
        if not clinical_evidence.procedure_codes:
            logger.warning(
                "[PolicyAgent] No procedure codes in clinical evidence — "
                "falling back to MEDIUM likelihood."
            )
            return self._unknown_policy_response(
                insurance_plan,
                reason="No procedure codes present in clinical evidence.",
            )

        procedure_code = clinical_evidence.procedure_codes[0]

        # Fetch policy document
        try:
            from data.mock_data.payer_policies import get_policy_for_procedure

            policy_text = get_policy_for_procedure(procedure_code, insurance_plan)
        except Exception as exc:
            logger.error(
                "[PolicyAgent] Failed to retrieve policy for %s / %s: %s",
                procedure_code,
                insurance_plan,
                exc,
            )
            raise PolicyAnalysisError(
                f"Could not retrieve policy document for procedure '{procedure_code}' "
                f"under plan '{insurance_plan}': {exc}"
            ) from exc

        if "Policy not found" in policy_text:
            raise PolicyNotFoundError(
                f"No policy document found for procedure '{procedure_code}' "
                f"under plan '{insurance_plan}'."
            )

        # LLM analysis
        prompt = self._build_policy_analysis_prompt(
            clinical_evidence, policy_text, insurance_plan
        )

        try:
            response_text = self.client.generate(prompt)
        except LLMError as exc:
            logger.error(
                "[PolicyAgent] LLM call failed for %s / %s: %s",
                procedure_code,
                insurance_plan,
                exc,
            )
            raise PolicyAnalysisError(
                f"LLM call failed during policy analysis for "
                f"procedure '{procedure_code}': {exc}"
            ) from exc

        # JSON parsing
        try:
            analysis_dict = safe_json_parse(response_text, context="PolicyAgent")
        except JSONParseError as exc:
            logger.error(
                "[PolicyAgent] JSON parse error. Raw response: %.500s", response_text
            )
            raise PolicyAnalysisError(
                f"Could not parse JSON from LLM policy analysis response: {exc}"
            ) from exc

        # Normalise and validate
        analysis_dict = self._normalise_response(analysis_dict, insurance_plan)

        try:
            return PolicyAnalysis(**analysis_dict)
        except Exception as exc:
            logger.error(
                "[PolicyAgent] Model validation failed: %s | data: %s",
                exc,
                analysis_dict,
            )
            raise PolicyAnalysisError(
                f"LLM response does not match PolicyAnalysis schema: {exc}"
            ) from exc

    def check_red_flags(self, evidence: ClinicalEvidence) -> dict[str, Any]:
        """
        Check for neurological or serious red flags that might expedite approval.

        Returns:
            ``{"has_red_flags": bool, "red_flags": list[str],
               "expedited_review_recommended": bool}``
        """
        if evidence is None:
            return {"has_red_flags": False, "red_flags": [], "expedited_review_recommended": False}

        red_flags: list[str] = []

        neurological_keywords = {
            "progressive", "weakness", "numbness", "bladder", "bowel",
            "saddle anesthesia", "cauda equina", "cord compression",
        }
        serious_keywords = {"fever", "cancer", "infection", "weight loss", "night pain"}

        for indicator in evidence.severity_indicators:
            lower = indicator.lower()
            if any(kw in lower for kw in neurological_keywords):
                red_flags.append(f"Neurological concern: {indicator}")

        for symptom in evidence.symptoms:
            lower = symptom.lower()
            if any(kw in lower for kw in serious_keywords):
                red_flags.append(f"Serious concern: {symptom}")

        return {
            "has_red_flags": bool(red_flags),
            "red_flags": red_flags,
            "expedited_review_recommended": len(red_flags) > 1,
        }

    def suggest_improvements(self, analysis: PolicyAnalysis) -> list[str]:
        """Return actionable suggestions for strengthening the authorisation request."""
        suggestions: list[str] = []

        if analysis.approval_likelihood == ApprovalLikelihood.LOW:
            suggestions.append("Consider obtaining additional clinical documentation.")
            suggestions.append(
                "Ensure all conservative treatments are documented with dates and outcomes."
            )

        for criterion in analysis.missing_criteria:
            lower = criterion.lower()
            if "conservative" in lower:
                suggestions.append(
                    "Document all conservative treatments attempted, "
                    "including duration and response."
                )
            elif "imaging" in lower:
                suggestions.append(
                    "Obtain and document preliminary imaging results (X-rays)."
                )
            elif "duration" in lower:
                suggestions.append("Clarify symptom duration and timeline.")

        if analysis.required_documentation:
            suggestions.append("Gather the following documentation before resubmission:")
            suggestions.extend(f"  - {doc}" for doc in analysis.required_documentation)

        return suggestions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unknown_policy_response(plan: str, reason: str = "") -> PolicyAnalysis:
        """Return a safe MEDIUM-likelihood fallback when no policy is available."""
        return PolicyAnalysis(
            approval_likelihood=ApprovalLikelihood.MEDIUM,
            met_criteria=["Procedure code provided"],
            missing_criteria=["Policy guidelines not available"],
            required_documentation=[],
            policy_reference=f"{plan} - Policy Not Available",
            reasoning=(
                reason or
                "Unable to locate specific policy for this procedure. "
                "Manual review recommended."
            ),
        )

    @staticmethod
    def _normalise_response(raw: dict[str, Any], insurance_plan: str) -> dict[str, Any]:
        """Coerce list fields and ensure required keys are present."""
        list_fields = ("met_criteria", "missing_criteria", "required_documentation")
        for field in list_fields:
            val = raw.get(field)
            if val is None:
                raw[field] = []
            elif isinstance(val, str):
                raw[field] = [val] if val.strip() else []
            elif not isinstance(val, list):
                raw[field] = []

        # Ensure approval_likelihood is a known value
        likelihood_raw = str(raw.get("approval_likelihood", "medium")).lower()
        valid = {e.value for e in ApprovalLikelihood}
        if likelihood_raw not in valid:
            logger.warning(
                "[PolicyAgent] Unknown approval_likelihood '%s' — defaulting to 'medium'",
                likelihood_raw,
            )
            raw["approval_likelihood"] = "medium"
        else:
            raw["approval_likelihood"] = likelihood_raw

        raw.setdefault("policy_reference", insurance_plan)
        raw.setdefault("reasoning", "No reasoning provided by model.")

        return raw

    def _build_policy_analysis_prompt(
        self,
        evidence: ClinicalEvidence,
        policy_text: str,
        insurance_plan: str,
    ) -> str:
        evidence_summary = (
            f"\nCLINICAL EVIDENCE:\n"
            f"- Diagnosis Codes: {', '.join(evidence.diagnosis_codes)}\n"
            f"- Procedure Codes: {', '.join(evidence.procedure_codes)}\n"
            f"- Supporting Evidence: {evidence.supporting_evidence}\n"
            f"- Symptoms: {evidence.symptoms}\n"
            f"- Prior Treatments: {evidence.prior_treatments}\n"
            f"- Severity Indicators: {evidence.severity_indicators}\n"
        )

        return f"""You are a prior authorisation specialist evaluating whether clinical evidence \
meets payer policy criteria.

INSURANCE PLAN: {insurance_plan}

PAYER POLICY DOCUMENT:
{policy_text}

{evidence_summary}

Your task is to systematically evaluate whether the clinical evidence meets the policy \
requirements for approval.

Return ONLY a valid JSON object (no markdown, no explanations):

{{
  "approval_likelihood": "high|medium|low",
  "met_criteria": [
    "specific criterion from policy that IS satisfied — cite specific evidence"
  ],
  "missing_criteria": [
    "specific criterion that is NOT met — explain what is missing"
  ],
  "required_documentation": [
    "additional documents or information needed"
  ],
  "policy_reference": "{insurance_plan} Policy [policy number if available]",
  "reasoning": "Detailed single-paragraph explanation of the determination."
}}

CRITICAL FORMATTING RULES:
1. Return ONLY the JSON object — no other text before or after.
2. Do NOT use markdown code blocks (no ```json).
3. Ensure all strings are on single lines (no literal newlines in string values).
4. Use proper JSON escaping for quotes and special characters.
5. Keep the reasoning field as a single paragraph (no newlines).

APPROVAL LIKELIHOOD GUIDELINES:
- high:   All major criteria met, strong supporting evidence, minimal gaps.
- medium: Most criteria met but some gaps, or borderline documentation.
- low:    Missing major criteria, insufficient conservative treatment, or contradictory evidence.

Analyse now:"""
