"""
Clinical Reader Agent - Extracts clinical evidence from unstructured patient notes
"""
from __future__ import annotations

import logging
from typing import Any

from models import ClinicalEvidence
from llm_client import UniversalLLMClient, LLMError
from utils import safe_json_parse, JSONParseError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ClinicalExtractionError(Exception):
    """Raised when clinical evidence cannot be extracted from patient notes."""


class ClinicalValidationError(Exception):
    """Raised when extracted evidence fails structural validation."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ClinicalReaderAgent:
    """
    Analyses patient clinical notes and extracts structured clinical evidence
    for prior authorisation.
    """

    # Fields that must be lists (never None) in the LLM response
    _REQUIRED_LIST_FIELDS = (
        "diagnosis_codes",
        "procedure_codes",
        "supporting_evidence",
        "symptoms",
        "prior_treatments",
        "contraindications",
        "severity_indicators",
    )

    def __init__(self) -> None:
        self.client = UniversalLLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_clinical_evidence(
        self,
        patient_notes: str,
        procedure_code: str,
    ) -> ClinicalEvidence:
        """
        Extract structured clinical evidence from unstructured patient notes.

        Args:
            patient_notes:  Raw clinical notes from the EHR.
            procedure_code: CPT code for the requested procedure.

        Returns:
            A populated ``ClinicalEvidence`` object.

        Raises:
            ValueError:              *patient_notes* or *procedure_code* is empty.
            ClinicalExtractionError: LLM call failed after retries.
            ClinicalValidationError: LLM returned data that doesn't fit the model.
        """
        if not patient_notes or not patient_notes.strip():
            raise ValueError("patient_notes must not be empty")
        if not procedure_code or not procedure_code.strip():
            raise ValueError("procedure_code must not be empty")

        prompt = self._build_extraction_prompt(patient_notes, procedure_code)

        # --- LLM call -------------------------------------------------------
        try:
            response_text = self.client.generate(prompt)
        except LLMError as exc:
            logger.error(
                "[ClinicalReader] LLM call failed for procedure %s: %s",
                procedure_code,
                exc,
            )
            raise ClinicalExtractionError(
                f"LLM call failed while extracting clinical evidence "
                f"for procedure '{procedure_code}': {exc}"
            ) from exc

        # --- JSON parsing ---------------------------------------------------
        try:
            evidence_dict = safe_json_parse(response_text, context="ClinicalReader")
        except JSONParseError as exc:
            logger.error(
                "[ClinicalReader] JSON parse error for procedure %s. Raw response: %.500s",
                procedure_code,
                response_text,
            )
            raise ClinicalExtractionError(
                f"Could not parse JSON from LLM response for procedure "
                f"'{procedure_code}': {exc}"
            ) from exc

        # --- Structural normalisation ----------------------------------------
        evidence_dict = self._normalise_response(evidence_dict)

        # --- Model validation ------------------------------------------------
        try:
            return ClinicalEvidence(**evidence_dict)
        except Exception as exc:
            logger.error(
                "[ClinicalReader] Model validation failed: %s | data: %s",
                exc,
                evidence_dict,
            )
            raise ClinicalValidationError(
                f"Extracted data does not match ClinicalEvidence schema: {exc}"
            ) from exc

    def validate_completeness(self, evidence: ClinicalEvidence) -> dict[str, Any]:
        """
        Validate that extracted evidence is complete enough for PA submission.

        Returns a dict with keys:
            is_complete (bool), missing_elements (list[str]), completeness_score (int)
        """
        issues: list[str] = []

        if not evidence.diagnosis_codes:
            issues.append("Missing diagnosis codes")
        if not evidence.procedure_codes:
            issues.append("Missing procedure codes")
        if not evidence.supporting_evidence:
            issues.append("Missing supporting clinical evidence")
        if not evidence.prior_treatments and not evidence.severity_indicators:
            issues.append(
                "Missing prior treatments or red flags justifying immediate imaging"
            )
        if len(evidence.symptoms) < 2:
            issues.append("Limited symptom documentation (fewer than 2 symptoms listed)")

        return {
            "is_complete": len(issues) == 0,
            "missing_elements": issues,
            "completeness_score": max(0, 100 - len(issues) * 15),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalise_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Ensure list fields are always lists (the LLM occasionally returns
        null or a bare string).  Also coerce ``relevant_dates`` to a dict.
        """
        for field in self._REQUIRED_LIST_FIELDS:
            value = raw.get(field)
            if value is None:
                raw[field] = []
            elif isinstance(value, str):
                # Single string returned instead of a list
                raw[field] = [value] if value.strip() else []
            elif not isinstance(value, list):
                logger.warning(
                    "[ClinicalReader] Unexpected type for field '%s': %s — coercing to list",
                    field,
                    type(value).__name__,
                )
                raw[field] = list(value) if hasattr(value, "__iter__") else []

        dates = raw.get("relevant_dates")
        if not isinstance(dates, dict):
            raw["relevant_dates"] = {}

        return raw

    def _build_extraction_prompt(self, patient_notes: str, procedure_code: str) -> str:
        return f"""You are a clinical documentation specialist extracting structured data \
from patient notes for prior authorization.

PATIENT CLINICAL NOTES:
{patient_notes}

REQUESTED PROCEDURE CODE: {procedure_code}

Your task is to extract ALL relevant clinical information that would support a prior \
authorization request. Be thorough and precise.

Extract the following information and return ONLY a valid JSON object \
(no markdown, no explanations):

{{
  "diagnosis_codes": ["list of ICD-10 codes mentioned or implied"],
  "procedure_codes": ["list of CPT codes for requested procedures"],
  "supporting_evidence": [
    "specific clinical findings that justify the procedure",
    "objective test results",
    "physical examination findings",
    "symptom severity indicators"
  ],
  "symptoms": [
    "chief complaints",
    "associated symptoms",
    "symptom duration and severity"
  ],
  "prior_treatments": [
    "conservative treatments attempted",
    "duration of each treatment",
    "outcome/response to treatment"
  ],
  "contraindications": ["any contraindications to current or alternative treatments"],
  "relevant_dates": {{
    "symptom_onset": "date when symptoms began",
    "treatment_dates": "dates of prior treatments"
  }},
  "severity_indicators": [
    "red flags or concerning features",
    "functional impairments",
    "objective severity measures"
  ]
}}

IMPORTANT GUIDELINES:
1. Use standard ICD-10 codes (e.g. M54.16 for lumbar radiculopathy).
2. Include specific dates when mentioned.
3. List treatments in chronological order.
4. Quote specific measurements when available (pain scores, ROM, strength grades).
5. Identify red flags that might expedite authorisation.
6. Be precise and factual — only extract what is explicitly stated or clearly implied.
7. If information is not present in notes, use empty lists [] not null.
8. Return ONLY the JSON object, no other text.
9. Do NOT include any markdown formatting like ```json.
10. Ensure all strings are properly escaped (no unescaped quotes or newlines).

Extract the information now:"""
