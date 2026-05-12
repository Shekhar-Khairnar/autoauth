#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec python -m seed_fhir.seed_patient
