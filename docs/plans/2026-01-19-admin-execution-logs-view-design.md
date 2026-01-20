# Admin Execution Logs View - Design

## Overview

A new "Logs" view mode on the Execution History page, accessible via a toggle switch in the top-right action bar. Admin-only. Shows individual log entries across all executions in a searchable, filterable table with server-side pagination. Clicking a log row opens a responsive side drawer showing the full execution result.

**Primary Use Case:** Support triage - searching logs by message content to investigate user-reported issues.

## UI Layout

### Toggle Switch

- Placed in top-right action bar, left-aligned with other action buttons
- Simple toggle switch with "Logs" label
- Only visible to platform admins (`is_superuser`)
- Switching resets pagination but preserves compatible filters (org, date range)

### Logs Table Columns

| Order | Column | Description |
|-------|--------|-------------|
| 1 | Organization | Org name |
| 2 | Workflow | Workflow name |
| 3 | Level | Colored badge (INFO=blue, WARNING=yellow, ERROR=red, DEBUG=gray, CRITICAL=red bold) |
| 4 | Message | Flex column, word-wrapping enabled to show full text |
| 5 | Timestamp | Formatted datetime |

## Filtering & Search

All filters are server-side - no client-side filtering given data volume.

### Available Filters

- **Organization** - Dropdown, same as current execution view (admin can filter by any org)
- **Workflow** - Text input with autocomplete
- **Level** - Multi-select: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Date Range** - Same date picker as current view
- **Message Search** - Text input for full-text search on log message content

### Filter Behavior

- All filters applied server-side via database queries
- Changing any filter resets pagination to first page
- Filters preserved when opening/closing the execution drawer
- URL params store filter state for shareable/bookmarkable searches

### Pagination

- Cursor-based with continuation tokens (matches existing execution history pattern)
- Page stack maintained for back navigation
- Default page size: 50 logs (higher than execution view's 25 since rows are smaller)

## Execution Drawer

### Trigger

Clicking any log row opens a side drawer from the right.

### Drawer Content

- Full execution result view - same content as the existing execution detail page
- Includes: status, workflow name, timing, input parameters, result output, full logs list, AI usage (if applicable)
- Responsive width: ~50% on large screens, full-width on mobile/tablet

### Navigation

- Close button (X) in top-right of drawer
- Clicking outside drawer closes it
- ESC key closes drawer
- Main logs table remains visible and scrollable behind drawer (on larger screens)
- Pagination state and scroll position preserved when drawer closes
- Optional: "Open in new tab" link within drawer for full-page view

## Backend Implementation

### New API Endpoint

```
GET /api/executions/logs
```

**Authorization:** Admin-only (403 for non-superusers)

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `organization_id` | UUID | Filter by organization (optional) |
| `workflow_name` | string | Filter by workflow name, ILIKE match (optional) |
| `levels` | string | Comma-separated log levels, e.g., "ERROR,WARNING" (optional) |
| `message_search` | string | Text search on message content, ILIKE (optional) |
| `start_date` | datetime | Filter logs after this date (optional) |
| `end_date` | datetime | Filter logs before this date (optional) |
| `limit` | int | Page size, default 50, max 500 |
| `continuation_token` | string | Cursor for pagination (optional) |

### Response Schema

```json
{
  "logs": [
    {
      "id": 12345,
      "execution_id": "uuid-string",
      "organization_name": "Acme Corp",
      "workflow_name": "onboard-user",
      "level": "ERROR",
      "message": "Connection timeout after 30s",
      "timestamp": "2026-01-19T14:32:01Z"
    }
  ],
  "continuation_token": "abc123"
}
```

### Database Considerations

- Query joins `execution_logs` → `executions` → `organizations`
- May need composite index on `(level, timestamp)` for level+date filtering
- Consider PostgreSQL full-text search index on message column for search performance
- Evaluate query performance with production data volume before adding indexes

## Implementation Notes

### Frontend

- Reuse existing `ExecutionResult` component/page inside the drawer
- Use shadcn/ui Sheet component for the side drawer
- Leverage existing pagination infrastructure (page stack pattern)
- Add URL param support for filter state persistence

### State Management

- Logs view state separate from execution view state
- Toggle switch controls which view is active
- Both views can share compatible filters (org, date range)
