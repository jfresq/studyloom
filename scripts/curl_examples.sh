#!/usr/bin/env bash
set -euo pipefail
COURSE_ID=${1:-"CS101"}
MODEL=${2:-"gpt-4o-mini"}
read -r -d '' BODY <<'JSON'
{
  "model": "%MODEL%",
  "messages": [
    {"role":"user","content":"[course:%COURSE%] What are the grading components?"}
  ],
  "loom": {"course_id":"%COURSE%"}
}
JSON
BODY=${BODY//%COURSE%/$COURSE_ID}
BODY=${BODY//%MODEL%/$MODEL}
echo "$BODY" | curl -s -X POST http://localhost:8080/v1/chat/completions   -H "Content-Type: application/json"   -d @- | jq -r