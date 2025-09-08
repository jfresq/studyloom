#!/usr/bin/env bash
set -euo pipefail
COURSE_ID=${1:-"CS101"}
PDF="sample.pdf"
if [ ! -f "$PDF" ]; then
  cat > sample.txt <<EOF
Syllabus — CS101 Intro to Data Science
Office Hours: Tue/Thu 2-3pm
Academic Honesty: Do your own work. Cite sources. No unauthorized collaboration.
Grading: Homework 40%, Midterm 30%, Final 30%.
Week 1: Python basics.
Week 2: Pandas & Numpy.
EOF
  if command -v pandoc >/dev/null 2>&1; then
    pandoc sample.txt -o sample.pdf
  else
    printf '%s
' "%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 86>>stream
BT/F1 12 Tf 72 720 Td(Studyloom sample syllabus: CS101 Intro to Data Science)Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R/Size 6>>
%%EOF" > sample.pdf
  fi
  rm -f sample.txt || true
fi
echo "Ingesting $PDF into course $COURSE_ID..."
curl -s -F "course_id=$COURSE_ID" -F "file=@$PDF" http://localhost:8080/v1/ingest | jq -r
