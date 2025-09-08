#!/usr/bin/env bash
set -euo pipefail

# --- config ---
ROOT_DIR="${1:-./courses_folder}"             # path to your courses root
BASE_URL="${BASE_URL:-http://loom-gateway:8000/v1}"  # or http://<host>:8080/v1
JOBS="${JOBS:-4}"                              # parallel uploads
LOG_DIR="${LOG_DIR:-./ingest_logs}"
STATE_FILE="${STATE_FILE:-./.ingested_sha.txt}"  # to skip re-uploads (optional)

mkdir -p "$LOG_DIR"
touch "$STATE_FILE"

# sanitize folder name -> course_id
sanitize() {
  # keep letters, numbers, underscore; replace spaces/dashes with underscore; strip others
  local s="$1"
  s="${s// /_}"
  s="${s//-/_}"
  s="$(echo "$s" | tr -cd 'A-Za-z0-9_')"
  echo "$s"
}

# compute file sha256
fsha() {
  sha256sum "$1" | awk '{print $1}'
}

ingest_one() {
  local course_dir="$1"
  local pdf="$2"
  local course_id; course_id="$(basename "$course_dir")"
  course_id="$(sanitize "$course_id")"

  local sha; sha="$(fsha "$pdf")"
  if grep -q "^$sha$" "$STATE_FILE"; then
    echo "[skip] $pdf (already ingested by checksum)"
    return 0
  fi

  echo "[ingest] course=$course_id file=$pdf"
  # Use explicit content-type in case filenames have spaces
  http_code=$(curl -s -o "$LOG_DIR/$(basename "$pdf").json" -w "%{http_code}" \
    -F "course_id=$course_id" \
    -F "file=@$pdf;type=application/pdf" \
    "$BASE_URL/ingest" || true)

  if [[ "$http_code" == "200" ]]; then
    echo "$sha" >> "$STATE_FILE"
    echo "  -> ok"
  else
    echo "  -> failed (HTTP $http_code) — see $LOG_DIR/$(basename "$pdf").json"
  fi
}

export -f ingest_one sanitize fsha
export BASE_URL LOG_DIR STATE_FILE

# find each course directory (immediate children of ROOT_DIR)
mapfile -t courses < <(find "$ROOT_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [[ ${#courses[@]} -eq 0 ]]; then
  echo "No course folders under $ROOT_DIR"
  exit 1
fi

# build a list of "course_dir|pdf_path" pairs
pairs_file="$(mktemp)"
for cdir in "${courses[@]}"; do
  while IFS= read -r -d '' pdf; do
    echo "$cdir|$pdf" >> "$pairs_file"
  done < <(find "$cdir" -type f \( -iname '*.pdf' \) -print0)
done

total=$(wc -l < "$pairs_file" || echo 0)
echo "Found $total PDFs under $(realpath "$ROOT_DIR")"

# run in parallel
cat "$pairs_file" | xargs -n1 -P "${JOBS}" -I{} bash -lc 'course="${1%%|*}"; pdf="${1#*|}"; ingest_one "$course" "$pdf"' _ {}

rm -f "$pairs_file"
echo "Bulk ingest complete. Logs: $LOG_DIR"
