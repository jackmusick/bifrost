"""
HTML Table Example Workflow

Demonstrates returning formatted HTML output from a workflow.
The platform automatically detects HTML responses (strings starting with '<')
and renders them appropriately in the UI.
"""

import logging

from bifrost import workflow, context

logger = logging.getLogger(__name__)


@workflow(
    name="html_table_example",
    description="Generate a pretty HTML table with sample data",
    category="examples",
    tags=["example", "html", "reporting"]
)
async def html_table_example(
    title: str = "Sample Data Report",
    row_count: int = 5,
    theme: str = "blue"
) -> str:
    """
    Generate a pretty HTML table with sample data.

    This workflow demonstrates how to return HTML from a workflow.
    The platform automatically detects HTML responses and renders them
    in the UI with proper formatting.

    Args:
        title: Title for the table
        row_count: Number of rows to generate (1-50)
        theme: Color theme (blue, green, purple, orange)

    Returns:
        HTML string with formatted table
    """
    import datetime
    import random

    # Validate inputs
    row_count = max(1, min(50, row_count))  # Clamp between 1-50

    # Theme colors
    themes = {
        "blue": {"primary": "#3b82f6", "secondary": "#dbeafe", "hover": "#bfdbfe"},
        "green": {"primary": "#10b981", "secondary": "#d1fae5", "hover": "#a7f3d0"},
        "purple": {"primary": "#8b5cf6", "secondary": "#ede9fe", "hover": "#ddd6fe"},
        "orange": {"primary": "#f59e0b", "secondary": "#fed7aa", "hover": "#fcd34d"}
    }
    colors = themes.get(theme.lower(), themes["blue"])

    logger.info(
        f"Generating HTML table with {row_count} rows using {theme} theme")

    # Sample data generator
    products = ["Widget", "Gadget", "Doohickey",
                "Thingamajig", "Whatchamacallit"]
    statuses = ["Active", "Pending", "Completed", "On Hold"]

    # Build table rows
    rows_html = ""
    total_amount = 0.0

    for i in range(row_count):
        product = random.choice(products)
        status = random.choice(statuses)
        quantity = random.randint(1, 100)
        price = round(random.uniform(10.0, 500.0), 2)
        amount = round(quantity * price, 2)
        total_amount += amount

        # Status badge color
        status_colors = {
            "Active": "#10b981",
            "Pending": "#f59e0b",
            "Completed": "#3b82f6",
            "On Hold": "#6b7280"
        }
        status_color = status_colors.get(status, "#6b7280")

        rows_html += f"""
        <tr>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">{i + 1}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb; font-weight: 500;">{product}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                <span style="
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 9999px;
                    font-size: 12px;
                    font-weight: 600;
                    background-color: {status_color}20;
                    color: {status_color};
                ">{status}</span>
            </td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb; text-align: right;">{quantity}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb; text-align: right;">${price:,.2f}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb; text-align: right; font-weight: 600;">${amount:,.2f}</td>
        </tr>"""

    # Generate timestamp
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build HTML with dark mode support using CSS media query
    html = f"""
<style>
    .html-table-container {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        max-width: 1200px;
        margin: 0 auto;
    }}
    .html-table-header {{
        background: white;
        padding: 32px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        margin-bottom: 24px;
        border: 1px solid #e5e7eb;
    }}
    .html-table-header h1 {{
        color: {colors['primary']};
        font-size: 32px;
        font-weight: 700;
        margin: 0 0 8px 0;
    }}
    .html-table-header p {{
        color: #6b7280;
        font-size: 14px;
        margin: 0;
    }}
    .html-table-card {{
        background: white;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        overflow: hidden;
        border: 1px solid #e5e7eb;
    }}
    .html-table {{
        width: 100%;
        border-collapse: collapse;
    }}
    .html-table thead {{
        background: {colors['primary']};
        color: white;
    }}
    .html-table th {{
        padding: 16px;
        text-align: left;
        font-weight: 600;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    .html-table tbody tr {{
        border-bottom: 1px solid #e5e7eb;
    }}
    .html-table tbody tr:hover {{
        background-color: {colors['hover']};
    }}
    .html-table td {{
        padding: 12px 16px;
    }}
    .html-table tfoot {{
        background: #f9fafb;
        font-weight: 600;
    }}
    .html-table tfoot td {{
        padding: 16px;
        border-top: 2px solid {colors['primary']};
    }}
    .html-table-footer {{
        margin-top: 24px;
        text-align: center;
        color: #6b7280;
        font-size: 14px;
    }}
    .html-table-footer p {{
        margin: 0;
    }}

    /* Dark mode support */
    @media (prefers-color-scheme: dark) {{
        .html-table-header,
        .html-table-card {{
            background: #1f2937;
            border-color: #374151;
        }}
        .html-table-header h1 {{
            color: #60a5fa;
        }}
        .html-table-header p,
        .html-table-footer {{
            color: #9ca3af;
        }}
        .html-table tbody tr {{
            border-bottom-color: #374151;
        }}
        .html-table tbody tr:hover {{
            background-color: #374151;
        }}
        .html-table td {{
            color: #e5e7eb;
        }}
        .html-table tfoot {{
            background: #111827;
        }}
        .html-table tfoot td {{
            color: #e5e7eb;
        }}
    }}

    /* Support for .dark class on html/body (Tailwind style) */
    .dark .html-table-header,
    .dark .html-table-card {{
        background: #1f2937;
        border-color: #374151;
    }}
    .dark .html-table-header h1 {{
        color: #60a5fa;
    }}
    .dark .html-table-header p,
    .dark .html-table-footer {{
        color: #9ca3af;
    }}
    .dark .html-table tbody tr {{
        border-bottom-color: #374151;
    }}
    .dark .html-table tbody tr:hover {{
        background-color: #374151;
    }}
    .dark .html-table td {{
        color: #e5e7eb;
    }}
    .dark .html-table tfoot {{
        background: #111827;
    }}
    .dark .html-table tfoot td {{
        color: #e5e7eb;
    }}
</style>

<div class="html-table-container">
    <div class="html-table-header">
        <h1>{title}</h1>
        <p>Generated on {timestamp} • Organization: {context.org_id or 'Global'}</p>
    </div>

    <div class="html-table-card">
        <table class="html-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Product</th>
                    <th style="text-align: center;">Status</th>
                    <th style="text-align: right;">Quantity</th>
                    <th style="text-align: right;">Unit Price</th>
                    <th style="text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="5" style="text-align: right;">Total:</td>
                    <td style="text-align: right; color: {colors['primary']}; font-size: 18px;">${total_amount:,.2f}</td>
                </tr>
            </tfoot>
        </table>
    </div>

    <div class="html-table-footer">
        <p>Generated by Bifrost Workflows • Powered by {context.name}</p>
    </div>
</div>"""

    logger.info(
        f"HTML table generated successfully with total amount: ${total_amount:,.2f}")

    return html
