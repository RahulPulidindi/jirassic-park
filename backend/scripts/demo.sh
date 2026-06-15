#!/usr/bin/env bash
# A short end-to-end demo: drives a single SUP ticket through triage,
# escalation, fix, and resolution using REST. Mirrors scenario 1.
#
# Usage:
#   make run        # in another terminal first
#   make demo

set -euo pipefail

BASE="${BASE:-http://localhost:8080/api}"
ADMIN="${JP_ADMIN_TOKEN:-admin-token-jurassic}"
DEVON="token_devon_lee"
MARCUS="token_marcus_obrien"

step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
post() { curl -sS -X POST -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$3" "$BASE$2"; }
get()  { curl -sS    -H "Authorization: Bearer $1"                                              "$BASE$2"; }

step "Reset to seeded state"
post "$ADMIN" "/admin/reset" "{}" | jq .

step "File a new customer-reported bug in SUP"
SUP_ID=$(post "$DEVON" "/issues" '{"project_key":"SUP","issue_type":"Bug","summary":"Mobile app crash on launch (iOS 17)","priority":"High","labels":["customer-reported","ios"]}' | jq -r .id)
echo "Created $SUP_ID"

step "Assign and triage"
post "$DEVON" "/issues/$SUP_ID/assign" '{"assignee":"user_devon_lee"}' > /dev/null
post "$DEVON" "/issues/$SUP_ID/transitions" '{"to_status":"Triaged","comment":"Confirmed reproducible on iOS 17.2 cold start."}' | jq '{id, status, assignee:.owner}'

step "Open underlying PLAT defect and link them"
PLAT_ID=$(post "$MARCUS" "/issues" '{"project_key":"PLAT","issue_type":"Bug","summary":"Push notification handler crashes on cold start"}' | jq -r .id)
echo "Created $PLAT_ID"
post "$MARCUS" "/issues/$PLAT_ID/links" "{\"target\":\"$SUP_ID\",\"link_type\":\"causes\"}" | jq .

step "Platform team fixes PLAT bug"
post "$MARCUS" "/issues/$PLAT_ID/transitions" '{"to_status":"In Progress"}' > /dev/null
post "$MARCUS" "/issues/$PLAT_ID/transitions" '{"to_status":"Done","comment":"Patched in #4321; shipping in 4.2.1."}' | jq '{id, status, resolution}'

step "Support closes the ticket"
post "$DEVON" "/issues/$SUP_ID/transitions" '{"to_status":"Working"}' > /dev/null
post "$DEVON" "/issues/$SUP_ID/transitions" '{"to_status":"Resolved","comment":"Fix shipped in 4.2.1."}' | jq '{id, status}'

step "Final activity log for $SUP_ID"
get "$DEVON" "/issues/$SUP_ID/history" | jq '[.[] | {action, field, from_value, to_value, actor_id}]'

echo
echo "Done. Try also:"
echo "  curl -sH \"Authorization: Bearer $ADMIN\" '$BASE/search?jql=project%20%3D%20PLAT%20AND%20status%20%3D%20Done&limit=5' | jq"
