# Forms

Forms provide a user-friendly interface for executing workflows with guided data collection. They allow you to create custom input forms that collect data from users and pass it to your workflows, making complex automation accessible to non-technical users.

## Overview

Forms consist of:

- **Form Builder**: Drag-and-drop interface for creating forms
- **Form Execution**: User-facing interface for submitting forms
- **Context System**: Dynamic data available throughout the form
- **Field Types**: Various input components for different data types
- **Dynamic Visibility**: Show/hide fields based on conditions

## Creating a Form

### Basic Setup

1. Navigate to **Forms** in the sidebar
2. Click the **+** button to create a new form
3. Configure basic information:
    - **Name**: Display name for the form
    - **Description**: Optional description shown to users
    - **Linked Workflow**: The workflow that processes form submissions
    - **Launch Workflow** (optional): Workflow that runs when the form loads
    - **Default Launch Parameters** (optional): Default values for the launch workflow

### Scope

Forms can be created at two levels:

- **Global**: Available to all organizations (Platform Admins only)
- **Organization-specific**: Only available within a specific organization

The scope is automatically determined by your current organization selection when creating the form.

## Form Builder

### Field Palette

The left panel contains two sections:

#### Workflow Inputs

Fields derived from your linked workflow's parameters. These automatically:

- Match the workflow's parameter names
- Include data type information
- Show required status (marked with ⭐)
- Pre-populate data provider settings if configured

#### All Field Types

Standard field types available for any form:

- **Text Input**: Single-line text
- **Email**: Email address with validation
- **Number**: Numeric input
- **Dropdown**: Single selection from options
- **Checkbox**: Boolean yes/no
- **Text Area**: Multi-line text
- **Radio Buttons**: Single selection from visible options
- **Date & Time**: Date/time picker
- **Markdown**: Display formatted text (non-input)
- **HTML Content**: Display dynamic HTML with context access
- **File Upload**: Upload files with type restrictions

### Adding Fields

Three ways to add fields:

1. **Drag from Palette**: Drag a field type to the desired position
2. **Click Workflow Input**: Drag a workflow parameter to auto-populate settings
3. **Click + Button**: Opens field configuration dialog

### Field Configuration

Each field has the following settings:

#### Basic Settings

- **Field Type**: The type of input (text, email, number, etc.)
- **Field Name**: Internal identifier (must be unique, used in workflow)
- **Label**: Display text shown to users
- **Placeholder**: Helper text in empty inputs
- **Help Text**: Additional guidance below the field
- **Required**: Whether the field must be filled

#### Advanced Settings

**Default Value**: Pre-populated value when form loads

**Visibility Expression**: JavaScript expression to show/hide the field

- Example: `context.field.country === 'USA'`
- Has access to full form context
- Evaluated whenever any field value changes

**Allow as Query Parameter**:

- Enables passing this field's value via URL
- Example: `/execute/form-id?field_name=value`
- Useful for pre-filling forms from links

#### Field-Specific Options

**Dropdown/Radio Options**:

- **Static Options**: Manually defined label/value pairs
- **Data Provider**: Dynamic options from a data source
    - Select from available data providers
    - Options are loaded when the form opens

**File Upload**:

- **Allowed Types**: Restrict file types (e.g., `.pdf`, `.jpg`, `image/*`)
- **Multiple Files**: Allow uploading multiple files
- **Max Size**: Maximum file size in MB

**HTML Content**:

- Supports JSX templates with context access
- Use `{context.workflow.field_name}` to display dynamic data
- Styling with `className` (React-style)

## Form Context

The context object provides access to dynamic data throughout the form. It's available in:

- Visibility expressions
- HTML template fields
- Default values

### Context Structure

```javascript
{
  workflow: {
    // Results from launch workflow
    user_id: "user-123",
    user_email: "user@example.com",
    organization_id: "org-456",
    // ... any other data returned by launch workflow
  },
  query: {
    // URL query parameters (only allowed fields)
    preset_value: "foo",
    // ... other query params
  },
  field: {
    // Current form field values
    first_name: "John",
    last_name: "Doe",
    // ... other field values as user types
  }
}
```

### Viewing Context

Click the **Info** button (ℹ️) in the form builder to see a preview of the context structure based on:

- Your current user session
- Configured query parameters
- Test launch workflow results (if executed)

### Launch Workflow

Forms can execute a workflow when they load to populate the context:

1. Configure a **Launch Workflow** in form settings
2. Optionally set **Default Launch Parameters**
3. The workflow executes before the form is shown
4. Results are available in `context.workflow`

**Testing Launch Workflow**:

- Click the **Play** button (▶️) in the form builder
- Enter parameters if required
- View results in the context preview
- Use real data to test field visibility expressions

### Query Parameters

Enable fields to receive values from URL parameters:

1. Enable **Allow as Query Parameter** in field settings
2. The field name is automatically added to allowed parameters
3. Pass values via URL: `/execute/form-id?field_name=value`
4. Values are available in `context.query.field_name`

**Use Cases**:

- Pre-fill forms from email links
- Create custom form URLs for different scenarios
- Pass data between systems via URLs

## Dynamic Visibility

Control which fields are shown using JavaScript expressions.

### Writing Visibility Expressions

**Simple Comparisons**:

```javascript
context.field.country === "USA";
context.field.age >= 18;
context.field.subscribe === true;
```

**Checking Values**:

```javascript
// Field has a value
context.field.email !== null && context.field.email !== "";

// Field is empty
context.field.optional_field === null || context.field.optional_field === "";
```

**Multiple Conditions**:

```javascript
// Both conditions must be true
context.field.country === "USA" && context.field.state === "CA";

// Either condition can be true
context.field.role === "admin" || context.field.role === "manager";
```

**Using Workflow Data**:

```javascript
// Only show if launch workflow provided admin status
context.workflow.is_admin === true;

// Show based on organization from launch workflow
context.workflow.organization_id !== null;
```

**Using Query Parameters**:

```javascript
// Show field if specific query param is set
context.query.mode === "advanced";
```

### Expression Editor

- Syntax highlighting for JavaScript
- Real-time validation
- Autocomplete for context properties
- Example shown below editor
- Errors highlighted in red

### Best Practices

1. **Always check for null values**:

    ```javascript
    context.field.name !== null && context.field.name !== "";
    ```

2. **Use strict equality** (`===` not `==`):

    ```javascript
    context.field.type === "business"; // Good
    context.field.type == "business"; // Avoid
    ```

3. **Test with real data**: Use the launch workflow test feature to see how fields appear with actual data

## Field Types Reference

### Text Input

Single-line text entry. Basic input for names, titles, short answers.

**Settings**: Label, placeholder, required, default value, visibility

### Email

Email address with built-in validation.

**Settings**: Same as text, with automatic email format validation

### Number

Numeric input with up/down controls.

**Settings**: Same as text, automatically converts to number type

### Dropdown (Select)

Single selection from a list of options.

**Options**:

- **Static**: Define label/value pairs manually
- **Data Provider**: Load options dynamically from a data source

**Settings**: Label, required, placeholder, options source

### Checkbox

Single yes/no toggle.

**Settings**: Label, required, default (checked/unchecked)
**Note**: Returns `true` or `false` to workflow

### Text Area

Multi-line text entry for longer content.

**Settings**: Same as text input, displays with multiple rows

### Radio Buttons

Single selection with all options visible.

**Options**: Static label/value pairs only
**Settings**: Label, required, options list
**Use When**: Few options (2-5) that benefit from being all visible

### Date & Time

Date and time picker with calendar interface.

**Settings**: Label, required, default value
**Format**: Returns ISO 8601 datetime string

### Markdown

Display formatted text (non-input field).

**Content**: Supports full Markdown syntax

- Headings, lists, bold, italic
- Links and images
- Code blocks

**Use Cases**:

- Instructions and help text
- Section headers
- Dynamic content display

### HTML Content

Display rich HTML with dynamic context access.

**JSX Template Support**:

```jsx
<div className="p-4 bg-blue-50 rounded">
	<p>Welcome, {context.workflow.user_email}!</p>
	<p>Organization: {context.workflow.organization_name}</p>
</div>
```

**Features**:

- Full context access with `{context.*}`
- React-style className for styling
- Conditional rendering
- Sanitized for security

**Use Cases**:

- Dynamic welcome messages
- Display workflow results
- Conditional instructions
- Rich formatting with user data

### File Upload

Upload files with type and size restrictions. Files are uploaded directly to S3 storage using presigned URLs, bypassing the API for efficient large file handling.

**Settings**:

- **Allowed Types**: File type restrictions (`.pdf`, `image/*`, etc.)
- **Multiple Files**: Allow multiple file selection (requires `list[str]` workflow parameter)
- **Max Size**: Maximum file size in MB

**Upload Flow**:

1. User selects a file in the form
2. Client requests a presigned upload URL from the API
3. File uploads directly to S3 (with progress indicator)
4. The S3 path is stored as the field value
5. On form submit, the path (string) is passed to the workflow

**Workflow Parameter Types**:

- **Single file field**: Workflow parameter should be `str`
- **Multiple file field**: Workflow parameter should be `list[str]`

**What Workflows Receive**:

- **Single file**: A path string like `"form-id/uuid/document.pdf"`
- **Multiple files**: An array of paths like `["form-id/uuid/doc1.pdf", "form-id/uuid/doc2.pdf"]`

**Accessing Files in Workflows**:

Use the `files.read()` function with `location="uploads"`:

```python
from bifrost import files, workflow

@workflow
async def process_document(document: str):
    """Process an uploaded document.

    Args:
        document: Path from form file field
    """
    # Read file content from S3
    content = await files.read(document, location="uploads")

    # For binary files (images, PDFs, etc.)
    binary_data = await files.read_bytes(document, location="uploads")

    return {"processed": True, "size": len(content)}

@workflow
async def process_multiple_documents(documents: list[str]):
    """Process multiple uploaded documents.

    Args:
        documents: List of paths from multi-file upload field
    """
    results = []
    for doc_path in documents:
        content = await files.read(doc_path, location="uploads")
        results.append({"path": doc_path, "size": len(content)})
    return results
```

**Important Notes**:

- The path passed to `files.read()` should NOT include the `uploads/` prefix
- The `location="uploads"` parameter tells the SDK to look in the uploads storage
- Files are organized by form ID and upload UUID for isolation
- Uploaded files persist until explicitly deleted

## Form Execution

### User Experience

1. User navigates to `/execute/form-id` or clicks "Launch" on a form
2. If launch workflow is configured, it runs (loading state shown)
3. Form fields are displayed based on visibility rules
4. User fills out visible fields
5. Form validates required fields and formats
6. On submit, data is sent to the linked workflow
7. User is redirected to execution history

### Form Submission

When a user submits a form:

1. **Client-side validation**:
    - Required fields are filled
    - Email formats are valid
    - Numbers are valid

2. **Data sent to workflow**:
    - Field values as defined by field names
    - File uploads as arrays of file info objects
    - All fields sent, even if empty (null for empty)

3. **Workflow receives data**:
    - Parameters match field names
    - Data types are preserved
    - Available in workflow via decorated parameters

4. **Execution tracking**:
    - Creates execution record
    - Shows in Execution History
    - Links back to form

## Managing Forms

### Form List

The Forms page shows all available forms:

**Global Scope** (Platform Admins):

- View all global forms
- Filter by organization

**Organization Scope**:

- View organization-specific forms
- View global forms available to the organization

### Form Actions

**Launch** (▶️): Execute the form as an end-user

**Edit** (✏️): Modify form configuration and fields

**Delete** (🗑️): Remove the form permanently

**Enable/Disable**: Toggle form availability

- Enabled forms can be executed
- Disabled forms show "Inactive" message

### Form Status Indicators

**Active** (Green): Form is enabled and can be executed

**Inactive** (Gray): Form is disabled

- Form builder can still edit
- End users see inactive message
- Cannot be executed

**Global** (Badge): Form is available to all organizations

**Organization Name** (Badge): Form is specific to that organization

## Best Practices

### Form Design

1. **Start with workflow parameters**: Use workflow inputs when possible for automatic field generation

2. **Group related fields**: Use visibility to create wizard-like experiences

3. **Provide clear labels**: Make it obvious what data is needed

4. **Use help text**: Guide users on format and requirements

5. **Test with real data**: Use launch workflow to test with actual context

### Field Organization

1. **Required fields first**: Put must-have fields at the top

2. **Logical order**: Match the mental model of the task

3. **Progressive disclosure**: Show fields only when relevant

4. **Clear sections**: Use Markdown fields as section headers

### Visibility Rules

1. **Keep expressions simple**: Complex logic is hard to maintain

2. **Test edge cases**: What if field is null? Empty string?

3. **Consider user experience**: Don't hide/show fields too aggressively

4. **Document complex rules**: Use comments in field help text

### Performance

1. **Limit data provider fields**: Each one makes an API call

2. **Use static options when possible**: Faster and more reliable

3. **Minimize HTML template complexity**: Keep templates simple

## Troubleshooting

### Common Issues

**"No options available" in dropdown**:

- Check data provider is configured correctly
- Verify data provider returns data
- Check network tab for API errors

**Visibility expression not working**:

- Check syntax in expression editor
- Verify field names are correct
- Check context preview to see available data
- Look for null values that need checking

**Launch workflow not running**:

- Verify workflow is selected in form settings
- Check workflow has no required parameters (or set defaults)
- Save form before testing
- Look for errors in browser console

**Form validation failing**:

- Check required fields are configured correctly
- Verify email fields have valid format
- Check number fields have numeric values

**Query parameters not working**:

- Verify "Allow as Query Parameter" is enabled
- Check field name matches URL parameter
- Ensure parameter is in allowed list (auto-generated)

### Debug Tools

**Context Viewer**: Shows current context state

- Click ℹ️ button in form builder
- See all available data
- Test visibility expressions

**Test Launch Workflow**: Execute and view results

- Click ▶️ button in form builder
- Enter parameters
- See results in context

**Browser Console**: Check for JavaScript errors

- Open DevTools (F12)
- Look for red errors
- Check network requests

## Examples

### Simple Contact Form

```
Fields:
- first_name (text, required)
- last_name (text, required)
- email (email, required)
- message (textarea, required)

Linked Workflow: send_contact_email
```

### Conditional Employee Onboarding

```
Fields:
1. employee_type (radio: full-time, part-time, contractor)
2. email (email, required)
3. department (dropdown, required)
4. manager (dropdown, data provider: active_managers)
5. benefits_eligible (checkbox)
   - Visibility: context.field.employee_type === 'full-time'
6. equipment_request (textarea)
   - Visibility: context.field.employee_type !== 'contractor'

Launch Workflow: get_available_departments
Linked Workflow: provision_employee
```

### Dynamic Support Ticket

```
Launch Workflow: get_user_context
  Returns: user_email, organization_id, is_priority_customer

Fields:
1. priority (radio: low, medium, high)
   - Visibility: context.workflow.is_priority_customer === true
2. category (dropdown, static: technical, billing, feature request)
3. subject (text, required)
4. description (textarea, required)
5. attachments (file upload, multiple, allowed: .pdf,.jpg,.png)
6. emergency_contact (text)
   - Visibility: context.field.priority === 'high'

Linked Workflow: create_support_ticket
```

### Pre-filled Customer Survey

URL: `/execute/survey-form?customer_id=12345`

```
Fields:
1. customer_id (text, allow as query param)
   - Default: context.query.customer_id
   - Hidden from user (visibility: false)
2. satisfaction (radio: 1-5 stars, required)
3. would_recommend (checkbox, required)
4. feedback (textarea)
5. follow_up (checkbox: "May we contact you?")
6. contact_method (radio: email, phone)
   - Visibility: context.field.follow_up === true

Launch Workflow: load_customer_data
  Parameters: customer_id (from query)
  Returns: customer_name, purchase_date

HTML Header:
  <h2>Thank you, {context.workflow.customer_name}!</h2>
  <p>We'd love your feedback on your {context.workflow.purchase_date} purchase.</p>

Linked Workflow: submit_customer_survey
```

## Security Considerations

### Access Control

- Forms respect organization boundaries
- Global forms are Platform Admin only
- Workflow execution uses form submitter's permissions
- Launch workflows run with form owner's permissions

### Data Validation

- Client-side validation for user experience
- Server-side validation on workflow execution
- Input sanitization for HTML fields
- File upload restrictions enforced

### Best Practices

1. **Validate in workflows**: Don't trust client data
2. **Limit file uploads**: Set size and type restrictions
3. **Use data providers**: Prevent injection via dropdowns
4. **Review visibility expressions**: Ensure no sensitive data leakage
5. **Test permissions**: Verify users can't access unauthorized forms

## API Integration

Forms can be submitted via API for automation:

```bash
POST /api/forms/{form_id}/submit
Content-Type: application/json

{
  "formData": {
    "field_name": "value",
    "other_field": "value"
  }
}
```

Response includes execution ID for tracking.

## Future Enhancements

Planned features:

- Multi-step forms with progress indicators
- Form templates for common use cases
- Conditional field validation
- Field dependencies and calculations
- Draft save and resume
- Form versioning
- Submission history per user
- Export form submissions
