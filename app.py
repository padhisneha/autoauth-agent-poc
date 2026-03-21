"""
AutoAuth — Flask backend
Serves the frontend and runs the PA workflow through the existing Python agents.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime

from orchestrator import PAWorkflowOrchestrator
from models import PriorAuthorizationRequest, PatientInfo, ProviderInfo

app = Flask(__name__)
CORS(app)

# Initialise once at startup — loads all agents
orchestrator = PAWorkflowOrchestrator()


# ─── ROUTES ───────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/run', methods=['POST'])
def run_authorization():
    """
    Receives PDF-extracted text from the frontend, builds a
    PriorAuthorizationRequest, and runs it through the full
    LangGraph orchestrator (ClinicalReader → Policy → Submission/Appeal/Review).
    Returns the structured result for the frontend to render.
    """
    data = request.json

    notes_text  = data.get('notes_text',  '')
    policy_text = data.get('policy_text', '')

    # Build PatientInfo and ProviderInfo from whatever the frontend sends.
    # Fields are optional — the agents read the real values from notes_text.
    patient_info = PatientInfo(
        patient_id     = data.get('patient_id',     'PT-UNKNOWN'),
        name           = data.get('patient_name',   'Unknown Patient'),
        date_of_birth  = data.get('dob',            'Unknown'),
        gender         = data.get('gender',         'Unknown'),
        insurance_plan = data.get('insurance_plan', 'Unknown'),
        member_id      = data.get('member_id',      'Unknown'),
    )

    provider_info = ProviderInfo(
        provider_id = data.get('provider_id',   'PR-UNKNOWN'),
        name        = data.get('provider_name', 'Unknown Provider'),
        npi         = data.get('npi',           '0000000000'),
        specialty   = data.get('specialty',     'Unknown'),
        facility    = data.get('facility',      'Unknown'),
        phone       = data.get('phone',         'Unknown'),
    )

    pa_request = PriorAuthorizationRequest(
        request_id        = f"PA-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        patient_info      = patient_info,
        provider_info     = provider_info,
        patient_notes     = notes_text,
        requested_service = data.get('requested_service', 'Unknown'),
        created_at        = datetime.now(),
    )

    # Attach policy text so PolicyAgent can use the uploaded PDF
    # instead of the hardcoded mock policies
    pa_request.__dict__['_policy_text'] = policy_text

    try:
        response = orchestrator.process_authorization_request(pa_request)

        # Serialise to JSON-safe dict
        result = {
            'request_id':         response.request_id,
            'status':             response.status.value,
            'processing_time':    response.processing_time_seconds,
            'needs_human_review': response.needs_human_review,
            'review_reason':      response.review_reason,
            'errors':             response.errors,
            'clinical_evidence':  response.clinical_evidence.model_dump() if response.clinical_evidence else None,
            'policy_analysis':    _serialise_policy(response.policy_analysis),
            'fhir_request':       response.fhir_request                   if response.fhir_request      else None,
            'appeal_letter':      response.appeal_letter.model_dump()     if response.appeal_letter     else None,
        }
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _serialise_policy(policy_analysis):
    """Convert PolicyAnalysis model to JSON-safe dict, resolving any enums."""
    if not policy_analysis:
        return None
    d = policy_analysis.model_dump()
    lh = d.get('approval_likelihood')
    if hasattr(lh, 'value'):
        d['approval_likelihood'] = lh.value
    return d


# ─── ENTRY POINT ──────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
