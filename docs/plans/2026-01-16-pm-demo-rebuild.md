# Project Management Demo Rebuild Plan

**Date:** 2026-01-16
**Status:** Ready for implementation

## Overview

Rebuild the Project Management Demo app to showcase Bifrost's full capabilities as an integration platform. The app serves as a demonstration vehicle showing how a familiar PM workflow becomes connected to an entire business through Bifrost.

### Target Audience
1. **Sales demos to prospects** - Visual polish, "wow factor"
2. **Internal capability showcase** - Forms, workflows, tables, agents, knowledge working together
3. **Partner/developer onboarding** - Patterns they can copy (secondary)

### Core Narrative
"See how a project management workflow becomes connected to your entire business through Bifrost"

The demo is NOT about replacing Monday.com - it's about showing what happens when your PM tool is actually integrated with your CRM, billing, email, and knowledge systems.

---

## Key Demo Features

### Automation Triggers (Status Changes → External Actions)

| Trigger | Action |
|---------|--------|
| Project → "In Progress" | Sends kickoff email to customer contact |
| Project → "Completed" | Syncs billing to QuickBooks + sends completion notice |
| Comment created | Syncs as note to CRM |
| Any mutation (project/task/comment) | Indexed to knowledge store |

### AI Features

| Feature | Description |
|---------|-------------|
| "Ask about this project" | Queries knowledge store, returns AI-summarized context |
| "Generate status update" | AI drafts email to customer contact based on project activity |

### Visibility

- All simulated integrations logged to activity feed (not just toasts)
- Activity feeds show both user comments and system events (emails sent, status changes, CRM syncs)
- Execution history available as backup proof

---

## Technical Architecture

### Data Flow
```
User Action → Workflow → Simulated Integration → System Comment → Knowledge Index
                                    ↓
                            Activity Feed (visible proof)
```

### Existing Infrastructure
- **App:** "Project Management Demo" (pm-demo) - 13 pages, layouts defined, components stripped
- **Tables:** customers-demo, projects-demo, tasks-demo, comments-demo
- **Forms:** Change Order Request
- **Workflows:** 60+ including full CRUD, simulations, data providers

### Creative UI Approach
- Use `repeat-for` + `html` components for custom-looking feeds and lists
- Activity feeds with icons distinguishing event types (💬 comment, 📧 email, 🔄 status change)
- Project lists on customer detail as styled cards, not plain tables
- Dashboard "needs attention" as actionable grouped items

---

## Workflows to Build/Update

### New Workflows

| Workflow | Type | Purpose |
|----------|------|---------|
| `Send Kickoff Email (Demo)` | workflow | Simulate kickoff email, log to activity |
| `Complete Project (Demo)` | workflow | Simulate QuickBooks sync + completion email |
| `Sync Comment to CRM (Demo)` | workflow | Simulate CRM note, log system comment |
| `Index Project to Knowledge` | workflow | Index project data to knowledge store |
| `Index Task to Knowledge` | workflow | Index task data to knowledge store |
| `Index Comment to Knowledge` | workflow | Index comment to knowledge store |
| `Ask About Project (Demo)` | tool | Query knowledge, return AI summary |
| `Generate Status Update Email (Demo)` | tool | Query knowledge, draft email, return for review |

### Workflows to Update

| Workflow | Changes Needed |
|----------|----------------|
| `Demo: Dashboard Stats` | Add needs-attention data (tasks due today, projects awaiting kickoff, recent activity) |
| `Create Project (Demo)` | Call knowledge indexing on complete |
| `Update Project (Demo)` | Call knowledge indexing on complete |
| `Create Task (Demo)` | Call knowledge indexing on complete |
| `Update Task (Demo)` | Call knowledge indexing on complete |
| `Add Comment (Demo)` | Call CRM sync + knowledge indexing on complete |

---

## Page Designs

### Dashboard (`/`)
- Welcome header with user name
- 4 stat cards (active projects, tasks in progress, due this week, completed this month) - clickable to filtered lists
- "Needs Attention" section - tasks due today grouped by project, projects awaiting kickoff
- "Recent Activity" feed - last 5-10 events across all entities
- Quick actions: New Project, New Task, Ask AI

### Customer List (`/customers`)
- Header with title + "New Customer" button
- Searchable data table with company, industry, project count, status

### Customer Detail (`/customers/:id`)
- Back link + customer name header with Edit button
- Two-column: Contact info card | Account summary card (with simulated QuickBooks data)
- Projects list (repeat-for + html) - status dot, name, status badge, due date, task count
- Recent activity feed for this customer's projects

### Customer New/Edit (`/customers/new`, `/customers/:id/edit`)
- Standard form fields: name, industry, status, contact name, email, phone

### Projects List (`/projects`)
- Header with title + "New Project" button
- Searchable/filterable data table with name, customer, status, task count, due date

### Project Detail (`/projects/:id`)
- Back link + project name header with Edit button
- Customer name subtitle
- Status card with dropdown + action buttons (Send Kickoff, Complete Project - conditional visibility)
- Details card (due date, budget, logged time)
- AI section: text input + "Ask" button, response area below
- Tasks list (repeat-for + html) - checkbox, name, status badge, priority, assignee
- "Generate Status Update" button
- Activity feed (comments + system events)

### Project New/Edit (`/projects/new`, `/projects/:id/edit`)
- Form fields: name, customer (dropdown), status, due date, budget, description

### Tasks List (`/tasks`)
- Header with title + "New Task" button
- Searchable/filterable data table with name, project, status, priority, assignee, due date

### Task Detail (`/tasks/:id`)
- Back link + task name header with Edit button
- Project + customer subtitle
- Two-column: Status card with dropdown | Details card (priority, assignee, due date, created)
- Description section
- Comments feed (repeat-for + html) - user comments with avatar/name/time, system events with icon
- Add comment input + button

### Task New/Edit (`/tasks/new`, `/tasks/:id/edit`)
- Form fields: name, project (dropdown), status, priority, assignee, due date, description

---

## Implementation Phases

### Phase 1: Foundation - Workflows & Knowledge Indexing
- [ ] Build new workflows (kickoff email, complete project, CRM sync, knowledge indexing, AI features)
- [ ] Update existing workflows to call indexing
- [ ] Test with `execute_workflow` to verify knowledge indexing works
- [ ] Update demo data seeder if needed

**Review checkpoint:** Workflows run successfully, knowledge queries return indexed data

### Phase 2: Dashboard
- [ ] Update dashboard stats workflow with needs-attention data
- [ ] Build dashboard page components
- [ ] Wire up stat card click-through navigation
- [ ] Build needs-attention section with repeat-for
- [ ] Build recent activity feed with repeat-for + html

**Review checkpoint:** Dashboard renders with real data, all interactions work

### Phase 3: Customer Pages
- [ ] Customers list - header + existing table
- [ ] Customer detail - info cards, projects list, activity feed
- [ ] Customer new - form fields
- [ ] Customer edit - form fields with existing data

**Review checkpoint:** Full customer CRUD, activity shows on detail page

### Phase 4: Project Pages
- [ ] Projects list - header + table with status filter
- [ ] Project detail - status actions, AI features, tasks list, activity feed
- [ ] Project new - form with customer dropdown
- [ ] Project edit - form with existing data
- [ ] Wire up status change → workflow triggers
- [ ] Wire up AI ask + generate status update

**Review checkpoint:** Status changes trigger workflows and log to activity, AI features work

### Phase 5: Task Pages
- [ ] Tasks list - header + table with filters
- [ ] Task detail - status dropdown, description, comments feed
- [ ] Task new - form with project dropdown
- [ ] Task edit - form with existing data
- [ ] Wire up comment creation → CRM sync + knowledge indexing

**Review checkpoint:** Full task CRUD, comments create system events, feeds render correctly

### Phase 6: Polish & Demo Flow
- [ ] End-to-end test of demo narrative
- [ ] Fix rough edges
- [ ] Generate fresh demo data
- [ ] Verify all activity feeds show integration events

**Review checkpoint:** Complete demo walkthrough works smoothly

---

## Out of Scope (For Now)

- Scheduled/automatic triggers (overdue task notifications) - scheduler needs migration
- Multi-tenant resource migration - leave in provider tenant for demo
- Scope selection for newly indexed workflows - future feature

---

## Success Criteria

1. Someone watching the demo thinks "I could imagine using this for my small business"
2. The integration story is clear - status changes trigger external actions, everything is logged
3. AI features demonstrate knowledge indexing value
4. Activity feeds provide visible proof of automations
5. App looks like a custom application, not a limited builder output
