"""
HTML Transformation Helpers

Functions for converting data structures and markdown to nicely formatted HTML
with dark mode support.
"""

import re
from typing import Any, Optional


def sanitize_key(key: str) -> str:
    """
    Convert snake_case, camelCase, or kebab-case to Title Case.

    Examples:
        output_path -> Output Path
        outputPath -> Output Path
        my-cool-key -> My Cool Key
        APIKey -> API Key

    Args:
        key: The key string to sanitize

    Returns:
        Title-cased string with spaces
    """
    # Handle camelCase/PascalCase by inserting spaces
    # Insert space before uppercase letters that follow lowercase letters
    s1 = re.sub('([a-z0-9])([A-Z])', r'\1 \2', key)
    # Insert space before uppercase letter followed by lowercase (for acronyms)
    s2 = re.sub('([A-Z]+)([A-Z][a-z])', r'\1 \2', s1)

    # Replace underscores and hyphens with spaces
    s3 = s2.replace('_', ' ').replace('-', ' ')

    # Title case and clean up multiple spaces
    return ' '.join(word.capitalize() for word in s3.split())


def markdown_to_html(markdown: str) -> str:
    """
    Convert markdown to HTML with syntax highlighting support for code blocks.

    Supports:
    - Headers (# ## ###)
    - Bold (**text** or __text__)
    - Italic (*text* or _text_)
    - Code blocks (```language)
    - Inline code (`code`)
    - Links ([text](url))
    - Lists (- item or * item or 1. item)

    Args:
        markdown: Markdown string to convert

    Returns:
        HTML string with styling
    """
    html = markdown

    # Code blocks with language (```python ... ```)
    def code_block_replacer(match):
        language = match.group(1) or 'text'
        code = match.group(2)
        # HTML escape the code
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'''<div class="code-block">
    <div class="code-header">{language}</div>
    <pre><code class="language-{language}">{code}</code></pre>
</div>'''

    html = re.sub(r'```(\w+)?\n(.*?)```', code_block_replacer, html, flags=re.DOTALL)

    # Inline code
    html = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', html)

    # Headers
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Bold
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)

    # Italic
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    html = re.sub(r'_(.*?)_', r'<em>\1</em>', html)

    # Links
    html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)

    # Lists (simple implementation)
    lines = html.split('\n')
    in_list = False
    result_lines = []

    for line in lines:
        # Unordered list
        if re.match(r'^[\-\*] ', line):
            if not in_list:
                result_lines.append('<ul>')
                in_list = 'ul'
            content = re.sub(r'^[\-\*] ', '', line)
            result_lines.append(f'  <li>{content}</li>')
        # Ordered list
        elif re.match(r'^\d+\. ', line):
            if not in_list:
                result_lines.append('<ol>')
                in_list = 'ol'
            content = re.sub(r'^\d+\. ', '', line)
            result_lines.append(f'  <li>{content}</li>')
        else:
            if in_list:
                result_lines.append(f'</{in_list}>')
                in_list = False
            result_lines.append(line)

    if in_list:
        result_lines.append(f'</{in_list}>')

    html = '\n'.join(result_lines)

    # Paragraphs (lines separated by blank lines)
    paragraphs = re.split(r'\n\n+', html)
    formatted_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para and not para.startswith('<'):
            formatted_paragraphs.append(f'<p>{para}</p>')
        else:
            formatted_paragraphs.append(para)

    return '\n'.join(formatted_paragraphs)


def object_to_html(
    obj: Any,
    title: Optional[str] = None,
    subtitle: Optional[str] = None
) -> str:
    """
    Convert a dictionary or list to nicely formatted HTML with dark mode support.

    Features:
    - Clean, modern design
    - Dark mode support (both media query and .dark class)
    - Sanitized keys (snake_case -> Title Case)
    - Values can contain HTML (will be rendered as-is)
    - Nested structures supported

    Args:
        obj: Dictionary or list to convert
        title: Optional title for the output
        subtitle: Optional subtitle

    Returns:
        HTML string with full styling
    """

    def render_value(value: Any, depth: int = 0) -> str:
        """Recursively render a value to HTML."""
        indent = "  " * depth

        if isinstance(value, dict):
            items_html = ""
            for k, v in value.items():
                key_display = sanitize_key(str(k))
                value_html = render_value(v, depth + 1)
                items_html += f'''
{indent}<div class="data-item">
{indent}  <div class="data-key">{key_display}</div>
{indent}  <div class="data-value">{value_html}</div>
{indent}</div>'''
            return f'<div class="nested-object">{items_html}\n{indent}</div>'

        elif isinstance(value, list):
            if not value:
                return '<em class="empty-value">Empty list</em>'
            items_html = "\n".join(
                f'{indent}  <li>{render_value(item, depth + 1)}</li>'
                for item in value
            )
            return f'<ul class="data-list">\n{items_html}\n{indent}</ul>'

        elif value is None:
            return '<em class="null-value">null</em>'

        elif isinstance(value, bool):
            return f'<span class="bool-value">{str(value).lower()}</span>'

        elif isinstance(value, (int, float)):
            return f'<span class="number-value">{value}</span>'

        else:
            # Treat as string/HTML - don't escape if it looks like HTML
            str_value = str(value)
            if str_value.strip().startswith('<'):
                return str_value
            else:
                # Escape HTML for plain text
                escaped = str_value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                return escaped

    # Build the main content
    content_html = ""

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_display = sanitize_key(str(key))
            value_html = render_value(value)
            content_html += f'''
    <div class="data-item">
      <div class="data-key">{key_display}</div>
      <div class="data-value">{value_html}</div>
    </div>'''

    elif isinstance(obj, list):
        for i, item in enumerate(obj, 1):
            value_html = render_value(item)
            content_html += f'''
    <div class="data-item">
      <div class="data-key">Item {i}</div>
      <div class="data-value">{value_html}</div>
    </div>'''

    else:
        content_html = f'<div class="data-value">{render_value(obj)}</div>'

    # Build the full HTML
    header_html = ""
    if title or subtitle:
        header_html = f'''
  <div class="data-header">
    {f'<h1>{title}</h1>' if title else ''}
    {f'<p>{subtitle}</p>' if subtitle else ''}
  </div>
'''

    html = f'''
<style>
    .data-container {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        max-width: 1200px;
        margin: 0 auto;
    }}
    .data-header {{
        padding: 0 0 16px 0;
        margin-bottom: 16px;
        border-bottom: 1px solid #e5e7eb;
    }}
    .data-header h1 {{
        color: #374151;
        font-size: 20px;
        font-weight: 600;
        margin: 0 0 4px 0;
    }}
    .data-header p {{
        color: #6b7280;
        font-size: 14px;
        margin: 0;
    }}
    .data-content {{
        padding: 0;
    }}
    .data-item {{
        margin-bottom: 24px;
        padding-bottom: 24px;
        border-bottom: 1px solid #e5e7eb;
    }}
    .data-item:last-child {{
        border-bottom: none;
        margin-bottom: 0;
        padding-bottom: 0;
    }}
    .data-key {{
        font-size: 14px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #6b7280;
        margin-bottom: 8px;
    }}
    .data-value {{
        font-size: 16px;
        line-height: 1.6;
        color: #1f2937;
    }}
    .nested-object {{
        margin-left: 16px;
        padding-left: 16px;
        border-left: 2px solid #e5e7eb;
    }}
    .nested-object .data-item {{
        margin-bottom: 16px;
        padding-bottom: 16px;
    }}
    .data-list {{
        margin: 8px 0;
        padding-left: 24px;
    }}
    .data-list li {{
        margin: 4px 0;
        line-height: 1.6;
    }}
    .empty-value, .null-value {{
        color: #9ca3af;
        font-style: italic;
    }}
    .bool-value {{
        color: #8b5cf6;
        font-weight: 600;
    }}
    .number-value {{
        color: #10b981;
        font-weight: 600;
    }}
    .inline-code {{
        background: #f3f4f6;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 14px;
        color: #dc2626;
    }}
    .code-block {{
        margin: 16px 0;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e5e7eb;
    }}
    .code-header {{
        background: #f3f4f6;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        color: #6b7280;
        letter-spacing: 0.5px;
    }}
    .code-block pre {{
        margin: 0;
        padding: 16px;
        background: #1f2937;
        overflow-x: auto;
    }}
    .code-block code {{
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 14px;
        line-height: 1.5;
        color: #e5e7eb;
    }}

    /* Dark mode support - media query */
    @media (prefers-color-scheme: dark) {{
        .data-header {{
            border-bottom-color: #374151;
        }}
        .data-header h1 {{
            color: #e5e7eb;
        }}
        .data-key {{
            color: #9ca3af;
        }}
        .data-header p {{
            color: #9ca3af;
        }}
        .data-value {{
            color: #e5e7eb;
        }}
        .data-item {{
            border-bottom-color: #374151;
        }}
        .nested-object {{
            border-left-color: #374151;
        }}
        .inline-code {{
            background: #374151;
            color: #fca5a5;
        }}
        .code-header {{
            background: #374151;
            color: #9ca3af;
        }}
        .code-block {{
            border-color: #374151;
        }}
    }}

    /* Dark mode support - .dark class */
    .dark .data-header {{
        border-bottom-color: #374151;
    }}
    .dark .data-header h1 {{
        color: #e5e7eb;
    }}
    .dark .data-key {{
        color: #9ca3af;
    }}
    .dark .data-header p {{
        color: #9ca3af;
    }}
    .dark .data-value {{
        color: #e5e7eb;
    }}
    .dark .data-item {{
        border-bottom-color: #374151;
    }}
    .dark .nested-object {{
        border-left-color: #374151;
    }}
    .dark .inline-code {{
        background: #374151;
        color: #fca5a5;
    }}
    .dark .code-header {{
        background: #374151;
        color: #9ca3af;
    }}
    .dark .code-block {{
        border-color: #374151;
    }}
</style>

<div class="data-container">
{header_html}
  <div class="data-content">
{content_html}
  </div>
</div>'''

    return html.strip()
