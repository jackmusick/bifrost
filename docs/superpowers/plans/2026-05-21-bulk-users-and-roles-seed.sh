#!/bin/bash
# Block 6 seed for phase-b-c-preview demo.
# Creates: 4 orgs, 4 roles, 4 apps, 4 agents, 4 forms, ~12 users.
# Assigns role-consumer relationships matching the plan's targets.
set -euo pipefail

source /tmp/bifrost-cli-226/.env
API="$BIFROST_API_URL"
TOKEN="$BIFROST_ACCESS_TOKEN"

H_AUTH="Authorization: Bearer $TOKEN"
H_JSON="Content-Type: application/json"

req() {
    local method=$1
    local path=$2
    local body=${3:-}
    if [ -n "$body" ]; then
        curl -s -X "$method" "$API$path" -H "$H_AUTH" -H "$H_JSON" -d "$body"
    else
        curl -s -X "$method" "$API$path" -H "$H_AUTH"
    fi
}

create_org() {
    local name=$1
    local domain=$2
    req POST /api/organizations "{\"name\":\"$name\",\"domain\":\"$domain\"}" | jq -r '.id'
}

create_role() {
    local name=$1
    local desc=$2
    req POST /api/roles "{\"name\":\"$name\",\"description\":\"$desc\"}" | jq -r '.id'
}

create_user() {
    local email=$1
    local name=$2
    local org=$3
    local body
    if [ "$org" = "null" ]; then
        body="{\"email\":\"$email\",\"name\":\"$name\",\"is_superuser\":false,\"invite\":false}"
    else
        body="{\"email\":\"$email\",\"name\":\"$name\",\"organization_id\":\"$org\",\"is_superuser\":false,\"invite\":false}"
    fi
    req POST /api/users "$body" | jq -r '.id'
}

create_app() {
    local name=$1
    local slug=$2
    req POST /api/applications "{\"name\":\"$name\",\"slug\":\"$slug\"}" | jq -r '.id'
}

create_agent() {
    local name=$1
    local desc=$2
    req POST /api/agents "{\"name\":\"$name\",\"description\":\"$desc\",\"system_prompt\":\"You are $name.\",\"channels\":[\"chat\"],\"access_level\":\"authenticated\"}" | jq -r '.id'
}

create_form() {
    local name=$1
    local desc=$2
    req POST /api/forms "{\"name\":\"$name\",\"description\":\"$desc\",\"workflow_id\":null,\"form_schema\":{\"fields\":[]},\"access_level\":\"role_based\"}" | jq -r '.id'
}

assign_role_users() {
    local role=$1; shift
    local ids_json
    ids_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
    req POST "/api/roles/$role/users" "{\"user_ids\":$ids_json}" >/dev/null
}

assign_role_forms() {
    local role=$1; shift
    local ids_json
    ids_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
    req POST "/api/roles/$role/forms" "{\"form_ids\":$ids_json}" >/dev/null
}

assign_role_agents() {
    local role=$1; shift
    local ids_json
    ids_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
    req POST "/api/roles/$role/agents" "{\"agent_ids\":$ids_json}" >/dev/null
}

assign_role_apps() {
    local role=$1; shift
    local ids_json
    ids_json=$(printf '%s\n' "$@" | jq -R . | jq -s .)
    req POST "/api/roles/$role/apps" "{\"app_ids\":$ids_json}" >/dev/null
}

assign_role_knowledge() {
    local role=$1
    local namespace=$2
    req POST "/api/roles/$role/knowledge" "{\"entries\":[{\"namespace\":\"$namespace\",\"organization_id\":null}]}" >/dev/null
}

echo "=== orgs ==="
ACME=$(create_org "Acme Corp" "acme-bulkdemo.gobifrost.dev")
NORTH=$(create_org "Northwind Traders MSP" "northwind-bulkdemo.gobifrost.dev")
VR=$(create_org "Van Rooy Properties — Long Org Name Case" "vanrooy-bulkdemo.gobifrost.dev")
GLOBEX=$(create_org "Globex" "globex-bulkdemo.gobifrost.dev")
echo "Acme=$ACME, Northwind=$NORTH, VR=$VR, Globex=$GLOBEX"

echo "=== roles ==="
AUDITOR=$(create_role "Auditor" "Read-only auditor access")
OPERATOR=$(create_role "Operator" "Day-to-day operator")
SUPPORT=$(create_role "Support" "Support tier role")
READONLY=$(create_role "ReadOnly" "Pure read-only access")
echo "Auditor=$AUDITOR Operator=$OPERATOR Support=$SUPPORT ReadOnly=$READONLY"

echo "=== apps ==="
A1=$(create_app "Help Center" "help-center-bulkdemo")
A2=$(create_app "Customer Portal" "customer-portal-bulkdemo")
A3=$(create_app "Internal Wiki" "internal-wiki-bulkdemo")
A4=$(create_app "Status Dashboard" "status-dashboard-bulkdemo")

echo "=== agents ==="
AG1=$(create_agent "Tier-1 Triage" "Front-line triage agent")
AG2=$(create_agent "Renewals Bot" "Helps with renewals")
AG3=$(create_agent "Onboarding Assistant" "Onboarding helper")
AG4=$(create_agent "Reporting Helper" "Pulls reports on demand")

echo "=== forms ==="
F1=$(create_form "Customer Intake" "New customer intake")
F2=$(create_form "Bug Report" "Internal bug report")
F3=$(create_form "Onboarding Checklist" "Onboarding step list")
F4=$(create_form "Renewal Survey" "Annual renewal questionnaire")

echo "=== users ==="
USERS=()
USERS+=( "$(create_user "alice.acme-bulkdemo@example.com" "Alice Acme" "$ACME")" )
USERS+=( "$(create_user "bob.acme-bulkdemo@example.com" "Bob Acme" "$ACME")" )
USERS+=( "$(create_user "carol.acme-bulkdemo@example.com" "Carol Acme" "$ACME")" )
USERS+=( "$(create_user "dave.northwind-bulkdemo@example.com" "Dave Northwind" "$NORTH")" )
USERS+=( "$(create_user "eve.northwind-bulkdemo@example.com" "Eve Northwind" "$NORTH")" )
USERS+=( "$(create_user "frank.northwind-bulkdemo@example.com" "Frank Northwind" "$NORTH")" )
# Long email + long org row, per plan
USERS+=( "$(create_user "a-truly-very-long-email-address-for-the-overflow-case@vanrooy-bulkdemo.gobifrost.dev" "Greta Van Rooy" "$VR")" )
USERS+=( "$(create_user "henry.vanrooy-bulkdemo@example.com" "Henry Van Rooy" "$VR")" )
USERS+=( "$(create_user "ivy.globex-bulkdemo@example.com" "Ivy Globex" "$GLOBEX")" )
USERS+=( "$(create_user "jack.globex-bulkdemo@example.com" "Jack Globex" "$GLOBEX")" )
USERS+=( "$(create_user "karen.globex-bulkdemo@example.com" "Karen Globex" "$GLOBEX")" )
USERS+=( "$(create_user "lou.globex-bulkdemo@example.com" "Lou Globex" "$GLOBEX")" )

# Auditor: 4 users, 2 forms, 1 agent, 0 apps, 0 workflows, 0 knowledge
echo "=== assignments: Auditor ==="
assign_role_users "$AUDITOR" "${USERS[0]}" "${USERS[1]}" "${USERS[6]}" "${USERS[8]}"
assign_role_forms "$AUDITOR" "$F1" "$F2"
assign_role_agents "$AUDITOR" "$AG1"

# Operator: 6 users, 1 form, 3 agents, 2 apps, 0 knowledge
echo "=== assignments: Operator ==="
assign_role_users "$OPERATOR" "${USERS[1]}" "${USERS[2]}" "${USERS[3]}" "${USERS[4]}" "${USERS[5]}" "${USERS[9]}"
assign_role_forms "$OPERATOR" "$F3"
assign_role_agents "$OPERATOR" "$AG1" "$AG2" "$AG3"
assign_role_apps "$OPERATOR" "$A1" "$A2"
assign_role_knowledge "$OPERATOR" "operator-docs"

# Support: 2 users, 3 forms, 0 agents, 1 app, 0 knowledge
echo "=== assignments: Support ==="
assign_role_users "$SUPPORT" "${USERS[7]}" "${USERS[10]}"
assign_role_forms "$SUPPORT" "$F1" "$F2" "$F4"
assign_role_apps "$SUPPORT" "$A1"

# ReadOnly: 8 users, 0 forms, 0 agents, 0 apps, 2 knowledge
echo "=== assignments: ReadOnly ==="
assign_role_users "$READONLY" "${USERS[0]}" "${USERS[2]}" "${USERS[3]}" "${USERS[5]}" "${USERS[6]}" "${USERS[8]}" "${USERS[10]}" "${USERS[11]}"
assign_role_knowledge "$READONLY" "public-docs"
assign_role_knowledge "$READONLY" "release-notes"

echo "=== done ==="
echo "Roles:"
req GET /api/roles | jq -r '.[] | select(.name | test("Auditor|Operator|Support|ReadOnly")) | "\(.name): \(.consumer_counts)"'
