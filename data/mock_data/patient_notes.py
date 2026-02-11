"""
Mock patient clinical notes for testing
"""

MOCK_PATIENT_NOTE_MRI = """
PATIENT: John Doe
MRN: 12345678
DOB: 05/15/1975
DATE OF VISIT: 01/15/2025

CHIEF COMPLAINT:
Chronic lower back pain radiating to left leg for 6 months

HISTORY OF PRESENT ILLNESS:
48-year-old male presents with persistent lower back pain that began approximately 6 months ago. 
Patient reports pain radiates down left leg to foot. Pain rated 7/10 at worst, 4/10 at best. 
Pain worsens with prolonged sitting, bending, and lifting. Patient reports numbness and tingling 
in left foot intermittently. Pain disrupts sleep 3-4 nights per week.

PAST MEDICAL HISTORY:
- Hypertension (controlled with medication)
- Type 2 Diabetes (HbA1c 7.2%)

MEDICATIONS:
- Lisinopril 10mg daily
- Metformin 1000mg BID
- Ibuprofen 600mg TID PRN

CONSERVATIVE TREATMENT HISTORY:
1. Physical therapy: 12 sessions over 8 weeks (09/2024 - 11/2024) - minimal improvement
2. NSAIDs: Ibuprofen 600mg TID for 3 months - temporary relief only
3. Muscle relaxants: Cyclobenzaprine 10mg - minimal benefit
4. Home exercise program: 6 weeks - no significant improvement
5. Activity modification: Ongoing - limited effectiveness

PHYSICAL EXAMINATION:
- Positive straight leg raise test on left at 45 degrees
- Decreased sensation in L5 distribution
- 4/5 strength in left great toe dorsiflexion
- Tenderness to palpation L4-L5, L5-S1
- Limited lumbar flexion and extension
- No saddle anesthesia, bowel/bladder function intact

ASSESSMENT:
1. Lumbar radiculopathy, left lower extremity (ICD-10: M54.16)
2. Sciatica, left side (ICD-10: M54.32)
3. Low back pain (ICD-10: M54.5)

RED FLAGS PRESENT:
- Progressive neurological symptoms (numbness, weakness)
- Failed conservative therapy for >6 weeks
- Functional impairment affecting daily activities and work

PLAN:
Prior authorization requested for MRI lumbar spine without contrast (CPT: 72148) to evaluate 
for disc herniation, spinal stenosis, or other structural pathology. Clinical presentation 
suggests nerve root compression requiring imaging for definitive diagnosis and treatment planning.

Patient education provided regarding MRI procedure. Discussed potential findings and next steps 
including possible specialist referral depending on results.

MEDICAL NECESSITY JUSTIFICATION:
1. Chronic symptoms >6 months duration
2. Radicular symptoms with objective neurological findings
3. Failed adequate trial of conservative therapy (PT, NSAIDs, activity modification)
4. Progressive symptoms requiring definitive diagnosis
5. Imaging necessary to guide further treatment decisions

___________________________
Dr. Sarah Johnson, MD
NPI: 1234567890
Family Medicine
Phone: (555) 123-4567
"""

MOCK_PATIENT_NOTE_SLEEP_STUDY = """
PATIENT: Jane Smith
MRN: 87654321
DOB: 03/22/1982
DATE OF VISIT: 01/20/2025

CHIEF COMPLAINT:
Excessive daytime sleepiness and witnessed apneas during sleep

HISTORY OF PRESENT ILLNESS:
42-year-old female referred by spouse due to loud snoring and observed breathing pauses during 
sleep occurring nightly for past 18 months. Patient reports severe daytime sleepiness (Epworth 
Sleepiness Scale: 18/24), morning headaches 5-6 days per week, difficulty concentrating at work, 
and falling asleep during meetings. Patient denies recent weight gain but BMI is 34.2.

SLEEP SYMPTOMS:
- Loud, disruptive snoring every night
- Witnessed apneas by spouse (10+ events per night observed)
- Gasping or choking sensations awakening patient 2-3x/night
- Non-restorative sleep despite 7-8 hours in bed
- Excessive daytime sleepiness (ESS: 18)
- Morning headaches
- Dry mouth upon awakening
- Difficulty concentrating, memory problems

PAST MEDICAL HISTORY:
- Hypertension (diagnosed 2 years ago)
- Obesity (BMI 34.2)
- Gastroesophageal reflux disease
- Depression (stable on SSRI)

MEDICATIONS:
- Amlodipine 10mg daily
- Omeprazole 20mg daily
- Sertraline 100mg daily

SOCIAL HISTORY:
- Works as accountant - reports falling asleep at desk
- Non-smoker
- Alcohol: 1-2 drinks per week
- Concerned about driving safety due to sleepiness

REVIEW OF SYSTEMS:
- Cardiac: No chest pain, palpitations. Hypertension present.
- Respiratory: No dyspnea at rest. Snoring as above.
- Neurological: Morning headaches, difficulty concentrating

PHYSICAL EXAMINATION:
- Vitals: BP 142/88, HR 78, RR 16, O2 sat 96% on RA
- BMI: 34.2 kg/m²
- Neck circumference: 42 cm (significantly elevated)
- Mallampati Score: Class III (crowded oropharynx)
- Enlarged tonsils (Grade 2)
- Nasal: Mildly deviated septum
- Cardiovascular: Regular rate and rhythm, no murmurs

STOP-BANG SCORE: 7/8 (High risk for OSA)
- Snoring: Yes
- Tired: Yes
- Observed apneas: Yes
- Pressure (HTN): Yes
- BMI >35: No (34.2)
- Age >50: No (42)
- Neck >40cm: Yes (42cm)
- Gender male: No

ASSESSMENT:
1. Suspected Obstructive Sleep Apnea, Severe (ICD-10: G47.33)
2. Excessive daytime sleepiness (ICD-10: G47.10)
3. Hypertension, likely secondary to OSA (ICD-10: I10)
4. Obesity (ICD-10: E66.9)

PLAN:
Prior authorization requested for attended polysomnography (CPT: 95810) to diagnose and 
determine severity of suspected obstructive sleep apnea. High clinical suspicion based on:
- STOP-BANG score of 7/8
- ESS score of 18 (severe daytime sleepiness)
- Witnessed apneas with gasping
- Multiple comorbidities (HTN, obesity)
- Safety concerns (occupational, driving)

MEDICAL NECESSITY:
Patient meets clinical criteria for polysomnography with high pre-test probability of 
moderate-to-severe OSA. Diagnosis essential for initiating appropriate therapy (likely CPAP) 
to prevent cardiovascular complications and improve quality of life and safety.

___________________________
Dr. Michael Chen, MD
NPI: 9876543210
Sleep Medicine
Phone: (555) 987-6543
"""

MOCK_PATIENT_NOTE_PHYSICAL_THERAPY = """
PATIENT: Robert Williams
MRN: 45678912
DOB: 08/10/1988
DATE OF VISIT: 01/18/2025

CHIEF COMPLAINT:
Right shoulder pain and decreased range of motion for 4 months following sports injury

HISTORY OF PRESENT ILLNESS:
36-year-old male recreational athlete presents with persistent right shoulder pain following 
basketball injury 4 months ago. Patient reports sudden onset pain after reaching overhead for 
rebound. Initial pain was severe (9/10) but has decreased to 5-6/10 with rest. Pain worsens 
with overhead activities, reaching across body, and lifting objects. Patient reports difficulty 
with daily activities including dressing, reaching for objects on high shelves, and sleeping 
on right side.

PAIN CHARACTERISTICS:
- Location: Anterolateral right shoulder
- Quality: Sharp with movement, aching at rest
- Intensity: 5-6/10 average, 8/10 with overhead activities
- Aggravating factors: Overhead reaching, lifting, sleeping on right side
- Relieving factors: Rest, ice, NSAIDs

FUNCTIONAL LIMITATIONS:
- Unable to participate in basketball or tennis
- Difficulty with overhead work activities (patient is electrician)
- Impaired grooming activities (washing hair, shaving)
- Sleep disruption due to pain when lying on right side
- Decreased ability to lift tools at work (>10 lbs causes pain)

PAST MEDICAL HISTORY:
- No significant medical history
- No previous shoulder injuries

MEDICATIONS:
- Ibuprofen 600mg TID PRN
- Acetaminophen 1000mg PRN

CONSERVATIVE TREATMENT TO DATE:
1. Rest and activity modification: 4 months - ongoing pain
2. Ice therapy: 3-4x daily - temporary relief
3. NSAIDs: Ibuprofen 600mg TID for 6 weeks - minimal improvement
4. Home exercises (provided by PCP): 3 weeks - no improvement
5. Shoulder brace/sling: Used for 2 weeks initially

PHYSICAL EXAMINATION:
- Inspection: No visible deformity, mild atrophy of supraspinatus
- Palpation: Tenderness over anterior shoulder and rotator cuff
- ROM: 
  * Forward flexion: 110° (limited, painful)
  * Abduction: 90° (limited, painful arc 60-120°)
  * External rotation: 30° (limited)
  * Internal rotation: To L5 only (limited)
- Strength: 
  * Supraspinatus (empty can test): 4-/5, painful
  * Infraspinatus: 4/5
  * Subscapularis: 4/5
- Special Tests:
  * Neer's impingement sign: Positive
  * Hawkins-Kennedy test: Positive
  * Painful arc: Positive 60-120°
  * Drop arm test: Negative
  * Apprehension test: Negative

ASSESSMENT:
1. Rotator cuff tendinopathy/impingement, right shoulder (ICD-10: M75.41)
2. Shoulder pain, right (ICD-10: M25.511)
3. Decreased range of motion, right shoulder (ICD-10: M25.511)

IMAGING:
X-ray right shoulder (01/10/2025): No fracture or dislocation. Mild subacromial spurring.

PLAN:
Prior authorization requested for Physical Therapy, 3x/week for 6 weeks (CPT: 97110, 97112, 
97140) for structured rehabilitation program focused on:
- Rotator cuff strengthening
- Scapular stabilization
- Range of motion restoration
- Pain management modalities
- Functional activity training

MEDICAL NECESSITY JUSTIFICATION:
1. Persistent symptoms >4 months despite home exercise program
2. Functional limitations affecting work and activities of daily living
3. Positive clinical examination findings consistent with rotator cuff pathology
4. Failed conservative management with rest, ice, NSAIDs, and home exercises
5. Supervised PT necessary to progress strengthening and prevent chronic dysfunction
6. Patient motivated and appropriate candidate for structured rehabilitation
7. Without treatment, risk of chronic pain and frozen shoulder

Patient educated regarding PT program expectations and home exercise compliance. 
Work restrictions: Avoid overhead lifting >10 lbs until reassessment.

___________________________
Dr. Lisa Martinez, DO
NPI: 5555555555
Orthopedic Surgery
Phone: (555) 444-3333
"""