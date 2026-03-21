// ─── PDF.JS SETUP ────────────────────────────────────────────
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

// ─── STATE ───────────────────────────────────────────────────
const state = {
  notes:  { file: null, text: '', pages: 0, ready: false },
  policy: { file: null, text: '', pages: 0, ready: false },
};
let isRunning = false;

// ─── DRAG & DROP ─────────────────────────────────────────────
function handleDragOver(e, zoneId) {
  e.preventDefault();
  document.getElementById(zoneId).classList.add('dragover');
}

function handleDragLeave(zoneId) {
  document.getElementById(zoneId).classList.remove('dragover');
}

function handleDrop(e, type) {
  e.preventDefault();
  handleDragLeave(type + 'Zone');
  const f = e.dataTransfer.files[0];
  if (f?.type === 'application/pdf') processFile(f, type);
}

function handleFileSelect(e, type) {
  const f = e.target.files[0];
  if (f) processFile(f, type);
}

// ─── PDF TEXT EXTRACTION ──────────────────────────────────────
async function processFile(file, type) {
  state[type] = { file, text: '', pages: 0, ready: false };
  document.getElementById(type + 'FileName').textContent = file.name;
  document.getElementById(type + 'Loaded').classList.add('visible');
  setStatus(type, 'loading', '⏳ Extracting text from PDF...');

  try {
    const buf = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    let text  = '';

    for (let i = 1; i <= pdf.numPages; i++) {
      const page    = await pdf.getPage(i);
      const content = await page.getTextContent();

      // Preserve line structure using Y-position changes
      let lastY    = null;
      let pageText = '';
      for (const item of content.items) {
        const y = item.transform ? item.transform[5] : null;
        if (lastY !== null && y !== null && Math.abs(y - lastY) > 2) pageText += '\n';
        pageText += item.str + (item.hasEOL ? '\n' : ' ');
        lastY = y;
      }
      text += pageText + '\n\n';
    }
    text = text.replace(/ {3,}/g, ' ').replace(/\n{4,}/g, '\n\n').trim();

    state[type].text  = text;
    state[type].pages = pdf.numPages;
    state[type].ready = true;

    document.getElementById(type + 'Pages').textContent =
      `${pdf.numPages} page${pdf.numPages !== 1 ? 's' : ''}`;
    setStatus(type, 'done', `✓ ${text.length.toLocaleString()} characters extracted`);
    showPreview(type, file.name, text, pdf.numPages);
    document.getElementById('emptyState').style.display = 'none';

  } catch (err) {
    setStatus(type, 'error', `✗ ${err.message}`);
  }

  updateReadiness();
}

// ─── UI HELPERS ───────────────────────────────────────────────
function setStatus(type, cls, msg) {
  const el       = document.getElementById(type + 'Status');
  el.className   = `extract-status visible ${cls}`;
  el.textContent = msg;
}

function removeFile(type) {
  state[type] = { file: null, text: '', pages: 0, ready: false };
  document.getElementById(type + 'Loaded').classList.remove('visible');
  document.getElementById(type + 'Status').className = 'extract-status';
  document.getElementById(type + 'Input').value = '';
  document.getElementById(type + 'Preview').classList.remove('visible');
  updateReadiness();
  if (!state.notes.ready && !state.policy.ready) {
    document.getElementById('emptyState').style.display = 'flex';
  }
}

function showPreview(type, name, text, pages) {
  document.getElementById(type + 'PreviewName').textContent  = name;
  document.getElementById(type + 'PreviewPages').textContent =
    `${pages} page${pages !== 1 ? 's' : ''}`;
  document.getElementById(type + 'PreviewBody').textContent  =
    text.substring(0, 1500) + (text.length > 1500 ? '\n\n… (preview truncated)' : '');
  document.getElementById(type + 'Preview').classList.add('visible');
}

function updateReadiness() {
  const n = state.notes.ready;
  const p = state.policy.ready;
  document.getElementById('dot-notes').className  = 'ready-dot' + (n      ? ' on' : '');
  document.getElementById('dot-policy').className = 'ready-dot' + (p      ? ' on' : '');
  document.getElementById('dot-ready').className  = 'ready-dot' + (n && p ? ' on' : '');
  document.getElementById('runBtn').disabled = !(n && p) || isRunning;
}

function resetAll() {
  ['notes', 'policy'].forEach(removeFile);
  document.getElementById('workflowSection').classList.remove('visible');
  document.getElementById('agentSteps').innerHTML = '';
  document.getElementById('statusBanner').className = 'status-banner';
  document.getElementById('humanReviewNotice').classList.remove('visible');
  document.getElementById('processingTime').style.display = 'none';
  document.getElementById('resetBtn').style.display = 'none';
  document.getElementById('emptyState').style.display = 'flex';
}

// ─── MAIN RUN — calls Python backend ─────────────────────────
async function runAuthorization() {
  if (isRunning || !state.notes.ready || !state.policy.ready) return;
  isRunning = true;

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.innerHTML = `<div style="width:16px;height:16px;border:2px solid white;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0"></div> Processing...`;

  document.getElementById('workflowSection').classList.add('visible');
  document.getElementById('agentSteps').innerHTML = '';
  document.getElementById('statusBanner').className = 'status-banner';
  document.getElementById('humanReviewNotice').classList.remove('visible');
  document.getElementById('processingTime').style.display = 'none';
  document.getElementById('resetBtn').style.display = 'none';

  // Show live step indicators while waiting for backend
  const s1 = addStep('s1', '🔬', 'teal',   'Agent 1 — Clinical Reader', 'Extracting clinical evidence...');
  const s2 = addStep('s2', '📋', 'blue',   'Agent 2 — Policy Checker',  'Evaluating policy criteria...');
  const s3 = addStep('s3', '📤', 'purple', 'Agent 3 — Routing',         'Determining next step...');

  const t0 = Date.now();

  try {
    // Single call to Python — all agent logic runs there
    const res = await fetch('/api/run', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notes_text:  state.notes.text,
        policy_text: state.policy.text,
      }),
    });

    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error(e.error || `Server error ${res.status}`);
    }

    const result = await res.json();

    // Render step results from what the Python agents returned
    const evidence = result.clinical_evidence;
    const policy   = result.policy_analysis;
    const status   = result.status;

    // Step 1 — Clinical evidence
    updateStep(s1, 'done', '✓ Clinical evidence extracted');
    if (evidence) renderClinicalBody(s1, evidence);

    // Step 2 — Policy analysis
    updateStep(s2, 'done', '✓ Policy analysis complete');
    if (policy) renderPolicyBody(s2, policy);

    // Step 3 — Routing outcome
    const lh = policy?.approval_likelihood || 'medium';
    if (status === 'pending' || lh === 'high') {
      updateStep(s3, 'done', '✓ FHIR request created & submitted');
      s3.querySelector('[id$="-st"]').parentElement.querySelector('.step-icon').textContent = '📤';
      if (result.fhir_request) renderFHIRBody(s3, result.fhir_request);
    } else if (result.appeal_letter || lh === 'low') {
      s3.querySelector('.step-title').textContent = 'Agent 3 — Appeal Generator';
      updateStep(s3, 'done', '✓ Appeal letter generated');
      s3.querySelector('.step-icon').textContent = '⚖️';
      if (result.appeal_letter) renderAppealBody(s3, result.appeal_letter);
    } else {
      s3.querySelector('.step-title').textContent = 'Agent 3 — Human Review';
      updateStep(s3, 'done', '✓ Flagged for human review');
      s3.querySelector('.step-icon').textContent = '👤';
      if (policy) renderHumanReviewBody(s3, policy);
    }

    // Processing time
    const elapsed = result.processing_time
      ? result.processing_time.toFixed(2)
      : ((Date.now() - t0) / 1000).toFixed(2);
    const pt = document.getElementById('processingTime');
    pt.textContent   = `⏱ ${elapsed}s`;
    pt.style.display = 'inline-block';

    // Status banner
    const bannerClass = (status === 'pending') ? 'pending' : 'needs_review';
    const bannerTitle = lh === 'high' ? '📨 Submission Created'
                      : lh === 'low'  ? '⚖️ Appeal Prepared'
                      :                 '👤 Human Review Required';
    const bannerSub   = lh === 'high' ? 'FHIR ServiceRequest submitted to payer. Awaiting insurer decision.'
                      : lh === 'low'  ? 'Low approval likelihood. Appeal letter generated and ready for submission.'
                      :                 'Medium approval likelihood. Clinical judgment required before proceeding.';

    const banner = document.getElementById('statusBanner');
    banner.className = `status-banner visible ${bannerClass}`;
    document.getElementById('bannerTitle').textContent    = bannerTitle;
    document.getElementById('bannerSubtitle').textContent = bannerSub;
    document.getElementById('bannerReqId').textContent    = result.request_id;
    document.getElementById('bannerProcTime').textContent = `Processed in ${elapsed}s`;

    if (result.needs_human_review) {
      document.getElementById('humanReviewNotice').classList.add('visible');
      document.getElementById('humanReviewText').textContent =
        result.review_reason || 'Human review required before submission.';
    }

    if (result.errors?.length) {
      document.getElementById('agentSteps').insertAdjacentHTML('beforeend',
        `<div style="background:var(--red-light);border:1px solid #fecaca;border-radius:var(--radius-sm);padding:14px 18px;font-size:13px;color:var(--red)">
          ⚠️ <strong>Warnings:</strong> ${result.errors.join(' | ')}
        </div>`);
    }

  } catch (err) {
    [s1, s2, s3].forEach(s => updateStep(s, 'error', '✗ Failed'));
    document.getElementById('agentSteps').insertAdjacentHTML('beforeend',
      `<div style="background:var(--red-light);border:1px solid #fecaca;border-radius:var(--radius-sm);padding:14px 18px;font-size:13px;color:var(--red)">
        ❌ <strong>Error:</strong> ${err.message}
      </div>`);
  }

  isRunning = false;
  btn.disabled = false;
  btn.innerHTML = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Authorization`;
  document.getElementById('resetBtn').style.display = 'flex';
}

// ─── STEP CARD HELPERS ────────────────────────────────────────
function addStep(id, icon, color, title, statusText) {
  const el     = document.createElement('div');
  el.className = 'step-card';
  el.id        = id;
  el.innerHTML = `
    <div class="step-header" onclick="document.getElementById('${id}').classList.toggle('collapsed')">
      <div class="step-icon ${color}">${icon}</div>
      <div class="step-title-area">
        <div class="step-label">Workflow Step</div>
        <div class="step-title">${title}</div>
      </div>
      <div class="step-status loading" id="${id}-st">
        <div class="spinner"></div> ${statusText}
      </div>
      <div class="step-chevron">▾</div>
    </div>
    <div class="step-body" id="${id}-body">
      <div style="display:flex;align-items:center;gap:8px;color:var(--text-muted);font-size:13px">
        <div style="width:14px;height:14px;border:2px solid var(--teal);border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0"></div>
        Processing...
      </div>
    </div>`;
  document.getElementById('agentSteps').appendChild(el);
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('visible')));
  return el;
}

function updateStep(stepEl, cls, text) {
  const st     = stepEl.querySelector('[id$="-st"]');
  st.className   = `step-status ${cls}`;
  st.textContent = text;
}

// ─── RENDER BODIES ─────────────────────────────────────────────
function renderClinicalBody(el, e) {
  const dxTags   = (e.diagnosis_codes     || []).map(d => `<span class="tag dx">${d}</span>`).join('') || '<span style="color:var(--text-light);font-size:12px">None found</span>';
  const cptTags  = (e.procedure_codes     || []).map(c => `<span class="tag cpt">${c}</span>`).join('') || '<span style="color:var(--text-light);font-size:12px">None found</span>';
  const symptoms = (e.symptoms            || []).slice(0, 5).map(s => `<li>${s}</li>`).join('') || '<li style="color:var(--text-light)">None</li>';
  const treats   = (e.prior_treatments    || []).slice(0, 4).map(t => `<li>${t}</li>`).join('') || '<li style="color:var(--text-light)">None</li>';
  const evidence = (e.supporting_evidence || []).slice(0, 4).map(x => `<li>${x}</li>`).join('') || '<li style="color:var(--text-light)">None</li>';
  const severity = (e.severity_indicators || []).slice(0, 3).map(s => `<li>${s}</li>`).join('') || '<li style="color:var(--text-light)">None</li>';

  el.querySelector('[id$="-body"]').innerHTML = `
    <div class="evidence-grid">
      <div class="evidence-group"><h4>Diagnosis Codes (ICD-10)</h4><div class="tag-list">${dxTags}</div></div>
      <div class="evidence-group"><h4>Procedure Codes (CPT)</h4><div class="tag-list">${cptTags}</div></div>
      <div class="evidence-group"><h4>Symptoms</h4><ul class="bullet-list">${symptoms}</ul></div>
      <div class="evidence-group"><h4>Prior Treatments</h4><ul class="bullet-list">${treats}</ul></div>
      <div class="evidence-group"><h4>Clinical Evidence</h4><ul class="bullet-list">${evidence}</ul></div>
      <div class="evidence-group"><h4>Severity Indicators</h4><ul class="bullet-list">${severity}</ul></div>
    </div>`;
}

function renderPolicyBody(el, p) {
  const lh           = p.approval_likelihood || 'medium';
  const metItems     = (p.met_criteria     || []).map(c => `<div class="criteria-item met">✓ ${c}</div>`).join('') || '<div style="color:var(--text-light);font-size:12px">None identified</div>';
  const missingItems = (p.missing_criteria || []).map(c => `<div class="criteria-item missing">✗ ${c}</div>`).join('') || '<div style="color:var(--text-light);font-size:12px">All criteria met</div>';

  el.querySelector('[id$="-body"]').innerHTML = `
    <div class="likelihood-bar ${lh}">
      <div>
        <div class="likelihood-label">Approval Likelihood</div>
        <div class="likelihood-value">${lh.charAt(0).toUpperCase() + lh.slice(1)}</div>
      </div>
      <div style="margin-left:auto;font-size:12px;color:var(--text-muted)">${p.policy_reference || ''}</div>
    </div>
    <div class="criteria-grid">
      <div class="criteria-box met"><h4>✓ Met Criteria (${(p.met_criteria || []).length})</h4>${metItems}</div>
      <div class="criteria-box missing"><h4>✗ Missing (${(p.missing_criteria || []).length})</h4>${missingItems}</div>
    </div>
    <div class="reasoning-box"><strong>Policy Reasoning</strong>${p.reasoning || 'No reasoning provided.'}</div>`;
}

function renderFHIRBody(el, fhir) {
  el.querySelector('[id$="-body"]').innerHTML = `
    <p style="font-size:12px;color:var(--text-muted);margin-bottom:10px">FHIR R4 ServiceRequest ready for payer submission</p>
    <div class="fhir-block">${syntaxHighlightJSON(JSON.stringify(fhir, null, 2))}</div>`;
}

function renderAppealBody(el, a) {
  const rebuttalItems = (a.rebuttal_points     || []).map(r => `<div class="rebuttal-item">⚖️ ${r}</div>`).join('');
  const addlEvidence  = (a.additional_evidence || []).map(e => `<li>${e}</li>`).join('');
  const attachments   = (a.attachments         || []).map(x => `<li>${x}</li>`).join('');

  el.querySelector('[id$="-body"]').innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--text-light);margin-bottom:8px">Rebuttal Points</div>
      ${rebuttalItems}
    </div>
    ${addlEvidence ? `
    <div style="margin-bottom:16px">
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--text-light);margin-bottom:8px">Suggested Additional Evidence</div>
      <ul class="bullet-list">${addlEvidence}</ul>
    </div>` : ''}
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--text-light);margin-bottom:8px">Generated Appeal Letter</div>
    <div class="appeal-letter-box">${a.letter_content || 'Letter content unavailable.'}</div>
    ${attachments ? `
    <div style="margin-top:12px">
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--text-light);margin-bottom:6px">Recommended Attachments</div>
      <ul class="bullet-list">${attachments}</ul>
    </div>` : ''}`;
}

function renderHumanReviewBody(el, p) {
  const gaps = (p.missing_criteria || []).length
    ? `<div style="margin-top:12px">
         <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#92400e;margin-bottom:6px">Gaps to Address</div>
         <ul class="bullet-list">${(p.missing_criteria || []).map(c => `<li style="color:#78350f">${c}</li>`).join('')}</ul>
       </div>`
    : '';

  el.querySelector('[id$="-body"]').innerHTML = `
    <div style="background:var(--amber-light);border:1px solid #fde68a;border-radius:var(--radius-sm);padding:16px">
      <div style="font-weight:600;color:#92400e;margin-bottom:8px">⚠️ Clinical Review Required</div>
      <p style="font-size:13px;color:#78350f;line-height:1.6">
        This case has medium approval likelihood and requires clinician review before submission.
      </p>
      ${gaps}
    </div>`;
}

// ─── UTILS ────────────────────────────────────────────────────
function syntaxHighlightJSON(json) {
  return json
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        let cls = 'fhir-num';
        if (/^"/.test(match)) cls = /:$/.test(match) ? 'fhir-key' : 'fhir-str';
        else if (/true|false/.test(match)) cls = 'fhir-bool';
        return `<span class="${cls}">${match}</span>`;
      }
    );
}
