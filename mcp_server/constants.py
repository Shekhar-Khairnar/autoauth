"""Hardcoded demo constants. Deterministic IDs so the seed script can recreate
them idempotently and the tools can reference them without lookups."""

PATIENT_ID = "mr-johnson-123"
PAYER_NAME = "MockHealth Plan"

# CPT 72148 = MRI lumbar spine without contrast - the canonical demo procedure.
CPT_MRI_LUMBAR = "72148"

# Resource IDs created by seed_fhir/seed_patient.py
CONDITION_ID = "cond-lbp-001"
MED_IBUPROFEN_ID = "medreq-ibuprofen-001"
MED_GABAPENTIN_ID = "medreq-gabapentin-001"
ENCOUNTER_PT_ID = "enc-pt-456"
OBSERVATION_REDFLAGS_ID = "obs-redflags-001"

QUESTIONNAIRE_ID = "q-mri-lumbar-v1"

# FHIR resource types we pull for the synthesize tool's reasoning bundle.
CHART_RESOURCE_TYPES = ("Condition", "MedicationRequest", "Encounter", "Observation")
