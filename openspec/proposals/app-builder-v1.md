# App Builder v1 - Implementation Plan

**Status:** Draft
**Author:** Claude
**Date:** 2026-01-01

## Overview

Extend the Bifrost platform from a forms/workflow engine to a low-code app builder capable of building CRUD applications with data storage, multi-page navigation, and workflow-driven automation.

### Target Use Case

A customer wants to build a small CRM to track customers, contacts, sales leads, and site surveys. They need to:
- Fill out forms onsite and upload pictures
- Run AI analysis on submission to generate proposals
- View site surveys in a list, open files, preview proposals
- Send proposals with one click

### Design Principles

1. **Extend, don't replace** - Build on existing form builder, components, and workflows
2. **JSON-portable** - App definitions stored as JSON for dual-write and versioning
3. **SDK-first** - Data operations available to workflows via `tables` SDK module
4. **Scope consistency** - Follow existing `organization_id: UUID | None` pattern
5. **Unified components** - Form fields and app components share the same system
6. **Multi-tenant capable** - Global apps with org-scoped data

### Key Decisions

| Decision | Choice |
|----------|--------|
| Form integration | **Hybrid** - Unified components, forms are named groupings |
| Permissions | App, page, and component-level |
| Multi-org apps | Global apps query org-scoped data automatically |
| Version history | Last 10 versions |
| JSONB vs partition keys | JSONB only (sufficient for automation platform) |

---

## Phase 1: Data Foundation (Tables & Documents)

### 1.1 Database Schema

```sql
-- Tables (metadata)
CREATE TABLE tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    organization_id UUID REFERENCES organizations(id),  -- NULL = global
    application_id UUID REFERENCES applications(id),    -- NULL = standalone
    schema JSONB,  -- Optional field hints for UI/validation
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255),

    UNIQUE(organization_id, name)  -- Unique name within org (or globally if NULL)
);

CREATE INDEX ix_tables_org ON tables(organization_id);
CREATE INDEX ix_tables_app ON tables(application_id);

-- Documents (rows)
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255),
    updated_by VARCHAR(255)
);

CREATE INDEX ix_documents_table ON documents(table_id);
CREATE INDEX ix_documents_data ON documents USING GIN(data);
```

### 1.2 ORM Models

**File:** `api/src/models/orm/tables.py`

```python
class Table(Base):
    __tablename__ = "tables"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id"), default=None
    )
    schema: Mapped[dict | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    created_by: Mapped[str]

    __table_args__ = (
        Index("ix_tables_org_name", "organization_id", "name", unique=True),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    table_id: Mapped[UUID] = mapped_column(
        ForeignKey("tables.id", ondelete="CASCADE")
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    created_by: Mapped[str | None]
    updated_by: Mapped[str | None]
```

### 1.3 Contract Models

**File:** `api/src/models/contracts/tables.py`

```python
class TableCreate(BaseModel):
    name: str = Field(max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    schema: dict[str, Any] | None = None

class TablePublic(BaseModel):
    id: UUID
    name: str
    organization_id: UUID | None
    application_id: UUID | None
    schema: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

class DocumentCreate(BaseModel):
    data: dict[str, Any]

class DocumentUpdate(BaseModel):
    data: dict[str, Any]  # Partial update, merged with existing

class DocumentPublic(BaseModel):
    id: UUID
    table_id: UUID
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime

class DocumentQuery(BaseModel):
    where: dict[str, Any] | None = None
    order_by: str | None = None
    order_dir: Literal["asc", "desc"] = "asc"
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)

class DocumentList(BaseModel):
    documents: list[DocumentPublic]
    total: int
    limit: int
    offset: int
```

### 1.4 API Endpoints

**File:** `api/src/routers/tables.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/tables` | Create table |
| GET | `/api/tables` | List tables (filtered by org) |
| GET | `/api/tables/{name}` | Get table metadata |
| DELETE | `/api/tables/{name}` | Delete table and all documents |
| POST | `/api/tables/{name}/documents` | Insert document |
| GET | `/api/tables/{name}/documents/{id}` | Get document |
| PATCH | `/api/tables/{name}/documents/{id}` | Update document (partial) |
| DELETE | `/api/tables/{name}/documents/{id}` | Delete document |
| POST | `/api/tables/{name}/documents/query` | Query documents |
| GET | `/api/tables/{name}/documents/count` | Count documents |

### 1.5 SDK Module

**File:** `api/bifrost/tables.py`

```python
class tables:
    """Table and document operations for workflows."""

    @staticmethod
    async def create_table(name: str, schema: dict | None = None, scope: str | None = None) -> TableInfo

    @staticmethod
    async def list_tables(scope: str | None = None) -> list[TableInfo]

    @staticmethod
    async def delete_table(name: str, scope: str | None = None) -> bool

    @staticmethod
    async def insert(table: str, data: dict, scope: str | None = None) -> DocumentData

    @staticmethod
    async def get(table: str, id: str, scope: str | None = None) -> DocumentData | None

    @staticmethod
    async def update(table: str, id: str, data: dict, scope: str | None = None) -> DocumentData

    @staticmethod
    async def delete(table: str, id: str, scope: str | None = None) -> bool

    @staticmethod
    async def query(
        table: str,
        where: dict | None = None,
        order_by: str | None = None,
        order_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
        scope: str | None = None,
    ) -> DocumentList

    @staticmethod
    async def count(table: str, where: dict | None = None, scope: str | None = None) -> int
```

### 1.6 Deliverables

- [ ] Alembic migration for `tables` and `documents`
- [ ] ORM models in `src/models/orm/tables.py`
- [ ] Contract models in `src/models/contracts/tables.py`
- [ ] Router in `src/routers/tables.py`
- [ ] SDK CLI endpoints in `src/routers/cli_tables.py`
- [ ] SDK module `bifrost/tables.py`
- [ ] SDK models in `bifrost/models.py`
- [ ] Unit tests for table operations
- [ ] Integration tests for SDK

---

## Phase 2: Application Container

### 2.1 Database Schema

```sql
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,  -- URL-friendly identifier
    organization_id UUID REFERENCES organizations(id),  -- NULL = global/platform app

    -- Versioning
    live_definition JSONB,      -- Published version users see
    draft_definition JSONB,     -- Editor version
    live_version INT DEFAULT 0,
    draft_version INT DEFAULT 1,
    published_at TIMESTAMP,

    -- Metadata
    description TEXT,
    icon VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(255),

    UNIQUE(organization_id, slug)
);

CREATE INDEX ix_applications_org ON applications(organization_id);
CREATE INDEX ix_applications_slug ON applications(organization_id, slug);
```

### 2.2 Application Definition Schema (JSON)

```typescript
interface ApplicationDefinition {
  version: 1;  // Schema version for migrations

  settings: {
    theme?: {
      primaryColor?: string;
      logo?: string;
    };
    defaultPage: string;  // Route to load on app open
  };

  navigation: {
    navbar?: {
      title: string;
      logo?: string;  // File reference
      items: NavItem[];
    };
    sidebar?: {
      sections: SidebarSection[];
      collapsible?: boolean;
      defaultCollapsed?: boolean;
    };
  };

  pages: Page[];

  // References to platform entities this app uses
  tables: { id: string; alias: string }[];
  workflows: { id: string; alias: string }[];
  forms: { id: string; alias: string }[];
}

interface NavItem {
  label: string;
  page?: string;      // Internal page route
  url?: string;       // External URL
  icon?: string;
}

interface SidebarSection {
  title?: string;
  items: NavItem[];
}

interface Page {
  id: string;
  route: string;           // "/surveys", "/surveys/:id"
  title: string;
  layout: LayoutContainer;

  // Optional page-level configuration
  guard?: {
    condition: string;     // "{{ user.role }} == 'admin'"
    redirect: string;
  };
}
```

### 2.3 Contract Models

**File:** `api/src/models/contracts/applications.py`

```python
class ApplicationCreate(BaseModel):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=255, pattern=r"^[a-z][a-z0-9-]*$")
    description: str | None = None
    icon: str | None = None

class ApplicationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    draft_definition: dict[str, Any] | None = None

class ApplicationPublic(BaseModel):
    id: UUID
    name: str
    slug: str
    organization_id: UUID | None
    description: str | None
    icon: str | None
    live_version: int
    draft_version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

class ApplicationDefinition(BaseModel):
    """Full app definition for rendering."""
    id: UUID
    name: str
    slug: str
    definition: dict[str, Any]  # The JSON definition
    version: int
```

### 2.4 API Endpoints

**File:** `api/src/routers/applications.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/applications` | Create application |
| GET | `/api/applications` | List applications |
| GET | `/api/applications/{slug}` | Get application metadata |
| PATCH | `/api/applications/{slug}` | Update application |
| DELETE | `/api/applications/{slug}` | Delete application |
| GET | `/api/applications/{slug}/definition` | Get live definition (for runtime) |
| GET | `/api/applications/{slug}/draft` | Get draft definition (for editor) |
| PUT | `/api/applications/{slug}/draft` | Save draft definition |
| POST | `/api/applications/{slug}/publish` | Publish draft to live |
| POST | `/api/applications/{slug}/rollback` | Rollback to previous version |

### 2.5 Deliverables

- [ ] Alembic migration for `applications`
- [ ] ORM models
- [ ] Contract models
- [ ] Router with CRUD + publish/rollback
- [ ] Unit tests
- [ ] Integration tests

---

## Phase 3: Layout System

### 3.1 Layout Schema

```typescript
type LayoutContainer = {
  type: "row" | "column" | "grid";
  id?: string;  // For targeting in editor

  // Spacing
  gap?: number;      // 4, 8, 12, 16, 20, 24, 32
  padding?: number;

  // Alignment
  align?: "start" | "center" | "end" | "stretch";
  justify?: "start" | "center" | "end" | "between" | "around";

  // Grid-specific
  columns?: number | "auto";

  // Children
  children: (LayoutContainer | Component)[];
};

type Component = {
  type: ComponentType;
  id?: string;

  // Sizing
  width?: "auto" | "full" | "1/2" | "1/3" | "1/4" | "2/3" | "3/4" | number;
  minWidth?: number;
  maxWidth?: number;

  // Component-specific props
  props: Record<string, any>;

  // Data binding
  dataSource?: DataSource;

  // Visibility (component-level permissions via expression)
  visible?: string;  // Expression: "{{ user.role == 'admin' }}" or "{{ selectedItem != null }}"
};

type ComponentType =
  // Form field components (unified - usable in forms AND apps)
  | "text-input" | "number-input" | "textarea" | "select" | "multi-select"
  | "checkbox" | "radio-group" | "date-picker" | "time-picker" | "datetime-picker"
  | "file-upload" | "rich-text" | "html-block"
  // Form grouping
  | "form-embed" | "form-group"
  // Display components
  | "table" | "card" | "stat-card" | "heading" | "text" | "divider" | "spacer"
  | "image" | "file-viewer" | "badge" | "progress"
  // Interactive components
  | "button" | "button-group" | "tabs" | "modal" | "dropdown-menu"
  // Layout components
  | "row" | "column" | "grid";

type DataSource = {
  type: "table" | "workflow" | "variable" | "static";

  // For table
  table?: string;
  query?: DocumentQuery;

  // For workflow
  workflowId?: string;

  // For variable (from page params, launch workflow, etc.)
  variable?: string;

  // For static
  value?: any;
};
```

### 3.2 Deliverables

- [ ] TypeScript types for frontend (auto-generated from Pydantic)
- [ ] Layout renderer component (recursive)
- [ ] Component registry with all supported types
- [ ] Data binding resolution system
- [ ] Expression evaluation ({{ }}) for dynamic values

---

## Phase 4: Forms Integration (Hybrid Model)

### 4.1 Design Philosophy

Forms and apps share a **unified component system**. A Form is simply:
- A named collection of field components
- A submit workflow
- Optional standalone rendering settings

This allows:
1. **Standalone forms** - Work exactly as today (render page, show execution details)
2. **Embedded forms** - Reference existing form in an app, show progress inline
3. **Inline fields** - Use field components directly in app pages

### 4.2 Form Definition (Updated)

```typescript
interface FormDefinition {
  id: string;
  name: string;
  organization_id: string | null;  // NULL = global

  // The form content - uses same components as apps
  fields: Component[];  // text-input, select, file-upload, etc.

  // What happens on submit
  submitWorkflow: string;  // Workflow ID

  // Standalone rendering (when form is accessed directly, not embedded)
  standalone: {
    title?: string;
    description?: string;
    successMessage?: string;
    showExecutionDetails: boolean;  // true = redirect to execution page (current behavior)
    redirectUrl?: string;           // Alternative: redirect somewhere else
  };
}
```

### 4.3 Form Components for Apps

#### FormEmbed - Reference an existing form

```typescript
interface FormEmbedProps {
  formId: string;                    // Reference to existing form

  mode: "inline" | "modal" | "page"; // How to display

  // Inline progress display (instead of redirecting to execution page)
  showProgress: boolean;
  progressStyle?: "bar" | "steps" | "minimal";

  // What happens when workflow completes
  onComplete?: {
    type: "set-variable";
    name: string;                    // Store result in this variable
  } | {
    type: "navigate";
    page: string;
  } | {
    type: "refresh-table";
    table: string;
  };

  // Pre-fill form fields from variables
  prefill?: Record<string, string>; // { "customer_id": "{{ params.id }}" }
}
```

#### FormGroup - Inline field collection

```typescript
interface FormGroupProps {
  name: string;  // Identifier for field collection

  // Children are field components (text-input, select, etc.)
  // Button with submitForm: true collects values from this group
}

// Example usage in app definition:
{
  "type": "form-group",
  "props": { "name": "quick-add" },
  "children": [
    {
      "type": "text-input",
      "props": { "name": "title", "label": "Title", "required": true }
    },
    {
      "type": "select",
      "props": {
        "name": "priority",
        "label": "Priority",
        "options": [
          { "value": "low", "label": "Low" },
          { "value": "high", "label": "High" }
        ]
      }
    },
    {
      "type": "button",
      "props": {
        "label": "Add Item",
        "submitForm": "quick-add",  // Collects fields from this form-group
        "onClick": {
          "type": "workflow",
          "workflowId": "create-item",
          "showProgress": true,
          "onComplete": { "type": "refresh-table", "table": "items" }
        }
      }
    }
  ]
}
```

### 4.4 Unified Field Components

All field components work identically in:
- Standalone forms
- Embedded forms
- Inline form-groups in apps

| Component | Props |
|-----------|-------|
| `text-input` | name, label, placeholder, required, pattern, minLength, maxLength |
| `number-input` | name, label, min, max, step, required |
| `textarea` | name, label, rows, maxLength, required |
| `select` | name, label, options, required, placeholder |
| `multi-select` | name, label, options, required, maxItems |
| `checkbox` | name, label, required |
| `radio-group` | name, label, options, required |
| `date-picker` | name, label, required, minDate, maxDate |
| `file-upload` | name, label, required, accept, maxSize, multiple |
| `rich-text` | name, label, required |

### 4.5 Inline Progress Display

When `showProgress: true`, instead of redirecting to execution page:

```
┌─────────────────────────────────────────┐
│ Site Survey Form                        │
├─────────────────────────────────────────┤
│ Customer: [Acme Corp        ]           │
│ Location: [123 Main St      ]           │
│ Photos:   [3 files selected ]           │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ ● Processing survey...              │ │
│ │ ████████████░░░░░░░░ 60%            │ │
│ │                                     │ │
│ │ ✓ Uploading photos                  │ │
│ │ ✓ Analyzing site conditions         │ │
│ │ ● Generating proposal...            │ │
│ │ ○ Finalizing                        │ │
│ └─────────────────────────────────────┘ │
│                                         │
│              [Cancel]                   │
└─────────────────────────────────────────┘

// On complete:
┌─────────────────────────────────────────┐
│ ✓ Survey submitted successfully!        │
│                                         │
│ Proposal generated: proposal_v1.pdf     │
│ [View Proposal] [Submit Another]        │
└─────────────────────────────────────────┘
```

### 4.6 Migration Path

1. **Phase 1**: Extract field components to shared library
2. **Phase 2**: Forms internally use shared components (no user-facing change)
3. **Phase 3**: Add `form-embed` and `form-group` to app builder
4. **Phase 4**: Form builder becomes "simplified app builder" view (optional)

### 4.7 Deliverables

- [ ] Extract field components to shared component library
- [ ] FormEmbed component for apps
- [ ] FormGroup component for inline fields
- [ ] Inline progress display component
- [ ] Field value collection and submission logic
- [ ] Integration tests for form embedding

---

## Phase 5: Display & Interactive Components

### 5.1 Table Component

```typescript
interface TableComponentProps {
  // Data
  dataSource: DataSource;  // Usually type: "table"

  // Columns
  columns: TableColumn[];

  // Features
  selectable?: boolean;
  searchable?: boolean;
  filterable?: boolean;
  sortable?: boolean;
  paginated?: boolean;
  pageSize?: number;

  // Actions
  rowActions?: TableAction[];
  bulkActions?: TableAction[];
  headerActions?: TableAction[];  // e.g., "Add New" button

  // Row click behavior
  onRowClick?: {
    type: "navigate" | "select" | "modal";
    page?: string;      // "/surveys/{{ row.id }}"
    formId?: string;    // For modal
  };

  // Empty state
  emptyMessage?: string;
  emptyAction?: TableAction;
}

interface TableColumn {
  key: string;           // Path into data: "data.name" or just "name"
  header: string;
  type?: "text" | "number" | "date" | "badge" | "actions";
  width?: number | "auto";
  sortable?: boolean;

  // For badge type
  badgeColors?: Record<string, string>;  // { "pending": "yellow", "approved": "green" }

  // For actions type
  actions?: TableAction[];
}

interface TableAction {
  label: string;
  icon?: string;
  variant?: "default" | "primary" | "destructive" | "ghost";

  // What happens
  onClick: ActionHandler;

  // Confirmation dialog
  confirm?: {
    title: string;
    message: string;  // "Delete {{ row.data.name }}?"
    confirmLabel?: string;
    cancelLabel?: string;
  };

  // Conditional visibility
  visible?: string;  // "{{ row.data.status }} != 'completed'"
}

type ActionHandler =
  | { type: "workflow"; workflowId: string; input?: Record<string, string> }
  | { type: "navigate"; page: string; params?: Record<string, string> }
  | { type: "modal"; formId: string; prefill?: Record<string, string> }
  | { type: "delete" }  // Built-in delete for table rows
  | { type: "set-variable"; name: string; value: string };
```

### 4.2 Button Component

```typescript
interface ButtonComponentProps {
  label: string;
  icon?: string;
  variant?: "default" | "primary" | "secondary" | "destructive" | "outline" | "ghost";
  size?: "sm" | "md" | "lg";
  fullWidth?: boolean;

  // Action
  onClick: ActionHandler;

  // Loading state (while workflow executes)
  loadingText?: string;

  // Disabled state
  disabled?: string;  // Expression

  // Confirmation
  confirm?: ConfirmConfig;
}
```

### 4.3 Card Component

```typescript
interface CardComponentProps {
  title?: string;
  description?: string;
  headerActions?: ActionHandler[];

  // Content is child layout
  children: LayoutContainer;

  // Styling
  padding?: number;
  shadow?: "none" | "sm" | "md" | "lg";
}
```

### 4.4 Stat Card Component

```typescript
interface StatCardComponentProps {
  title: string;
  value: string;           // "{{ tables.expenses | count }}" or static
  description?: string;
  icon?: string;
  trend?: {
    value: string;         // "+12%"
    direction: "up" | "down" | "neutral";
  };
  onClick?: ActionHandler;
}
```

### 4.5 File Viewer Component

```typescript
interface FileViewerComponentProps {
  // File reference
  fileId?: string;        // Direct file ID
  filePath?: string;      // "{{ row.data.proposal_file }}"

  // Display mode
  mode: "inline" | "modal" | "download-link";

  // For images
  maxHeight?: number;
  objectFit?: "contain" | "cover";
}
```

### 4.6 Deliverables

- [ ] Table component with all features
- [ ] Button component with action handlers
- [ ] Card component
- [ ] Stat card component
- [ ] File viewer component
- [ ] Heading, divider, spacer components
- [ ] Image component
- [ ] Tabs component
- [ ] Modal component (for inline forms)

---

## Phase 6: Navigation & Routing

### 6.1 App Shell

The app shell provides consistent chrome (navbar, sidebar) around page content.

```typescript
interface AppShell {
  navbar?: {
    title: string;
    logo?: string;
    items: NavItem[];
    userMenu?: boolean;  // Show user dropdown
  };

  sidebar?: {
    sections: SidebarSection[];
    collapsible?: boolean;
    defaultCollapsed?: boolean;
    width?: number;
  };

  // Main content area renders current page
}
```

### 6.2 Routing

- Use React Router for client-side routing
- Routes derived from page definitions
- Support route params: `/surveys/:id` → `{{ params.id }}`
- Support query params: `/surveys?status=pending` → `{{ query.status }}`

### 6.3 Page Context

Each page has access to:

```typescript
interface PageContext {
  // Route parameters
  params: Record<string, string>;

  // Query parameters
  query: Record<string, string>;

  // Current user
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
  };

  // Organization
  organization: {
    id: string;
    name: string;
  };

  // Page-level variables (from launch workflows, user interactions)
  variables: Record<string, any>;

  // Functions
  navigate: (page: string, params?: Record<string, string>) => void;
  setVariable: (name: string, value: any) => void;
  executeWorkflow: (id: string, input: Record<string, any>) => Promise<any>;
  refreshTable: (alias: string) => void;
}
```

### 6.4 Deliverables

- [ ] App shell component with navbar/sidebar
- [ ] React Router integration
- [ ] Route generation from page definitions
- [ ] Page context provider
- [ ] Navigation components (NavItem, SidebarSection)

---

## Phase 7: Permissions System

### 7.1 Three-Level Permissions

Permissions are evaluated at three levels, with each level able to restrict access further.

```typescript
interface ApplicationPermissions {
  // App-level: who can access the app at all
  access: {
    public: boolean;           // Anyone in org can access
    roles?: string[];          // Specific roles: ["admin", "manager"]
    users?: string[];          // Specific user IDs
  };

  // Page-level: override/restrict for specific pages
  pages?: {
    [pageRoute: string]: {
      roles?: string[];        // Required roles for this page
      users?: string[];        // Specific users allowed
      hidden?: boolean;        // Hide from navigation but accessible via URL
    };
  };
}

// Component-level: visibility expression
// Evaluated at runtime, can reference user context
{
  "type": "button",
  "props": { "label": "Delete", "variant": "destructive" },
  "visible": "{{ user.role == 'admin' }}"
}
```

### 7.2 Permission Evaluation Flow

```
User requests /apps/crm/settings
        │
        ▼
┌──────────────────────────┐
│ 1. App-level check       │
│    Is user in app.access?│
└──────────┬───────────────┘
           │ Yes
           ▼
┌──────────────────────────┐
│ 2. Page-level check      │
│    Is user allowed on    │
│    /settings page?       │
└──────────┬───────────────┘
           │ Yes
           ▼
┌──────────────────────────┐
│ 3. Render page           │
│    Component visibility  │
│    evaluated per-element │
└──────────────────────────┘
```

### 7.3 Expression Context for Permissions

```typescript
// Available in visibility expressions:
interface PermissionContext {
  user: {
    id: string;
    email: string;
    name: string;
    role: string;           // User's role in current org
    roles: string[];        // All roles (if multiple)
  };
  organization: {
    id: string;
    name: string;
  };
  params: Record<string, string>;  // Route params
  variables: Record<string, any>;  // Page variables
}

// Example expressions:
"{{ user.role == 'admin' }}"
"{{ user.roles | includes: 'manager' }}"
"{{ user.id == variables.record.created_by }}"  // Owner-only
"{{ organization.id == 'specific-org-id' }}"
```

### 7.4 Deliverables

- [ ] Permission schema in application definition
- [ ] App-level access check middleware
- [ ] Page-level permission guard component
- [ ] Component visibility expression evaluator
- [ ] Permission denied page/redirect
- [ ] Navigation filtering (hide pages user can't access)

---

## Phase 8: Action System

### 8.1 Workflow Execution

When a button or table action executes a workflow:

1. Show loading state on trigger element
2. Call `/api/workflows/{id}/execute` with input data
3. Wait for completion (poll or WebSocket)
4. Handle result:
   - Success: Update variables, refresh tables, show toast
   - Error: Show error toast

```typescript
interface WorkflowActionResult {
  success: boolean;
  output?: Record<string, any>;  // Workflow return value
  error?: string;
}

// In page context
const result = await executeWorkflow("generate-proposal", {
  survey_id: selectedSurvey.id,
});

if (result.success) {
  setVariable("proposal", result.output);
  refreshTable("surveys");
}
```

### 8.2 Variable System

Variables are reactive and can be:
- Set by launch workflows on page load
- Set by workflow results
- Set by user interactions (table selection, form input)
- Used in expressions throughout the page

```typescript
// Expression evaluation
"{{ variables.selectedSurvey.data.customer_name }}"
"{{ params.id }}"
"{{ tables.surveys | where: status == 'pending' | count }}"
```

### 6.3 Deliverables

- [ ] Workflow execution hook with loading/error states
- [ ] Variable store (Zustand or Context)
- [ ] Expression parser and evaluator
- [ ] Table refresh mechanism
- [ ] Toast notifications for action results

---

## Phase 7: App Editor

### 7.1 Editor Features

- Visual page builder (drag-and-drop)
- Component property panel
- Page management (add, rename, delete, reorder)
- Navigation editor (navbar, sidebar items)
- Table/workflow/form picker (reference platform entities)
- Preview mode
- Publish flow

### 7.2 Editor Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Toolbar: [Save Draft] [Preview] [Publish]                   │
├─────────────┬───────────────────────────────┬───────────────┤
│ Pages       │ Canvas                        │ Properties    │
│             │                               │               │
│ - Dashboard │  ┌─────────────────────────┐  │ Component:    │
│ - Surveys   │  │ [Selected Component]    │  │ Table         │
│   - List    │  │                         │  │               │
│   - Detail  │  │                         │  │ Data Source:  │
│ - Settings  │  │                         │  │ [surveys ▼]   │
│             │  └─────────────────────────┘  │               │
│ [+ Page]    │                               │ Columns: ...  │
│             │  Component Palette:           │               │
│             │  [Table] [Form] [Button] ...  │ Actions: ...  │
└─────────────┴───────────────────────────────┴───────────────┘
```

### 7.3 Deliverables

- [ ] Editor shell with panels
- [ ] Page tree navigator
- [ ] Drag-and-drop canvas
- [ ] Component palette
- [ ] Property editor (dynamic based on component type)
- [ ] Navigation editor
- [ ] Preview mode
- [ ] Draft save (auto-save)
- [ ] Publish confirmation flow

---

## Phase 8: Embedding & Access

### 8.1 Embedding Options

```html
<!-- iframe embed -->
<iframe
  src="https://platform.bifrost.io/apps/crm?token=..."
  width="100%"
  height="600"
/>

<!-- Or via JavaScript SDK (future) -->
<div id="bifrost-app"></div>
<script src="https://platform.bifrost.io/embed.js"></script>
<script>
  Bifrost.mount('#bifrost-app', {
    app: 'crm',
    token: '...',
    theme: { primaryColor: '#007bff' }
  });
</script>
```

### 8.2 Access Control

- Apps inherit organization permissions
- Optional page-level guards
- Role-based visibility for components

### 8.3 Deliverables

- [ ] Standalone app renderer route (`/apps/:slug`)
- [ ] Embed route (`/embed/:slug`)
- [ ] Token-based authentication for embeds
- [ ] Theme customization for embeds

---

## Implementation Order

### Sprint 1: Data Foundation
1. Tables/Documents database + ORM
2. Tables/Documents API endpoints
3. Tables SDK module
4. Tests

### Sprint 2: Application Container
1. Applications database + ORM
2. Applications API (CRUD + publish)
3. Application definition schema validation
4. Tests

### Sprint 3: Runtime Basics
1. App shell (navbar, sidebar)
2. Page routing
3. Layout renderer
4. Basic components (heading, card, button)

### Sprint 4: Table Component
1. Table component with columns
2. Row actions
3. Pagination, sorting, filtering
4. Bulk actions

### Sprint 5: Action System
1. Workflow execution from buttons/actions
2. Variable system
3. Expression evaluation
4. Table refresh

### Sprint 6: Editor MVP
1. Editor shell
2. Page management
3. Drag-and-drop canvas
4. Property panel
5. Preview + Publish

### Sprint 7: Polish & Embedding
1. File viewer component
2. Modal forms
3. Embedding support
4. Documentation

---

## CRM Example App Definition

```json
{
  "version": 1,
  "settings": {
    "defaultPage": "/surveys"
  },
  "navigation": {
    "sidebar": {
      "sections": [
        {
          "title": "CRM",
          "items": [
            { "label": "Dashboard", "page": "/", "icon": "home" },
            { "label": "Customers", "page": "/customers", "icon": "users" },
            { "label": "Contacts", "page": "/contacts", "icon": "contact" },
            { "label": "Leads", "page": "/leads", "icon": "target" },
            { "label": "Site Surveys", "page": "/surveys", "icon": "clipboard" }
          ]
        }
      ]
    }
  },
  "pages": [
    {
      "id": "surveys-list",
      "route": "/surveys",
      "title": "Site Surveys",
      "layout": {
        "type": "column",
        "gap": 16,
        "children": [
          {
            "type": "heading",
            "props": { "text": "Site Surveys", "level": 1 }
          },
          {
            "type": "table",
            "props": {
              "dataSource": { "type": "table", "table": "site_surveys" },
              "columns": [
                { "key": "data.customer_name", "header": "Customer" },
                { "key": "data.location", "header": "Location" },
                { "key": "data.status", "header": "Status", "type": "badge" },
                { "key": "created_at", "header": "Date", "type": "date" }
              ],
              "headerActions": [
                {
                  "label": "New Survey",
                  "icon": "plus",
                  "variant": "primary",
                  "onClick": { "type": "navigate", "page": "/surveys/new" }
                }
              ],
              "onRowClick": {
                "type": "navigate",
                "page": "/surveys/{{ row.id }}"
              }
            }
          }
        ]
      }
    },
    {
      "id": "survey-detail",
      "route": "/surveys/:id",
      "title": "Survey Details",
      "layout": {
        "type": "column",
        "gap": 16,
        "children": [
          {
            "type": "row",
            "justify": "between",
            "children": [
              {
                "type": "heading",
                "props": { "text": "{{ survey.data.customer_name }}", "level": 1 }
              },
              {
                "type": "button",
                "props": {
                  "label": "Generate Proposal",
                  "variant": "primary",
                  "onClick": {
                    "type": "workflow",
                    "workflowId": "generate-proposal",
                    "input": { "survey_id": "{{ params.id }}" }
                  }
                }
              }
            ]
          },
          {
            "type": "row",
            "gap": 16,
            "children": [
              {
                "type": "card",
                "width": "2/3",
                "props": { "title": "Survey Details" },
                "children": {
                  "type": "column",
                  "gap": 8,
                  "children": [
                    { "type": "text", "props": { "label": "Location", "value": "{{ survey.data.location }}" } },
                    { "type": "text", "props": { "label": "Notes", "value": "{{ survey.data.notes }}" } }
                  ]
                }
              },
              {
                "type": "card",
                "width": "1/3",
                "props": { "title": "Photos" },
                "children": {
                  "type": "file-viewer",
                  "props": {
                    "files": "{{ survey.data.photos }}",
                    "mode": "gallery"
                  }
                }
              }
            ]
          },
          {
            "type": "card",
            "props": { "title": "Proposal" },
            "visible": "{{ survey.data.proposal_file }}",
            "children": {
              "type": "column",
              "gap": 8,
              "children": [
                {
                  "type": "file-viewer",
                  "props": {
                    "fileId": "{{ survey.data.proposal_file }}",
                    "mode": "inline"
                  }
                },
                {
                  "type": "button",
                  "props": {
                    "label": "Send Proposal",
                    "variant": "primary",
                    "onClick": {
                      "type": "workflow",
                      "workflowId": "send-proposal",
                      "input": { "survey_id": "{{ params.id }}" }
                    },
                    "confirm": {
                      "title": "Send Proposal",
                      "message": "Send this proposal to {{ survey.data.customer_email }}?"
                    }
                  }
                }
              ]
            }
          }
        ]
      }
    }
  ],
  "tables": [
    { "id": "tbl_xxx", "alias": "site_surveys" },
    { "id": "tbl_yyy", "alias": "customers" }
  ],
  "workflows": [
    { "id": "wf_xxx", "alias": "generate-proposal" },
    { "id": "wf_yyy", "alias": "send-proposal" }
  ]
}
```

---

## Open Questions

1. **Form integration**: Do we embed existing forms as components, or unify form fields into the component system?
2. **Permissions UI**: How granular? Page-level, component-level, or just app-level?
3. **Offline/PWA**: Future consideration for field workers?
4. **Versioning history**: Store all versions or just last N?
5. **Multi-tenancy**: Can one app definition be deployed to multiple orgs?

---

## Success Criteria

- [ ] A non-developer can build the CRM use case in < 2 hours
- [ ] App loads in < 2 seconds
- [ ] Works on mobile devices
- [ ] Data operations feel instant (< 200ms perceived)
- [ ] Editor has undo/redo
- [ ] Apps are exportable/importable as JSON
