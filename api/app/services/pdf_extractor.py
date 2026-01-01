"""
PDF Financial Statement Extractor.
Extracts tabular data from PDF financial statements using multiple strategies:
1. pdfplumber for text-based PDFs (most common)
2. Table detection with heuristic column mapping
3. Fallback to raw text extraction

This service enables users to upload PDF balance sheets and income statements
directly, without manual data entry.
"""

import io
import re
from typing import Optional


def extract_tables_from_pdf(pdf_bytes: bytes) -> list[list[str]]:
    """
    Extract all tables from a PDF file.
    Returns a list of tables, where each table is a list of rows,
    and each row is a list of cell strings.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for PDF extraction. "
            "Install it with: pip install pdfplumber"
        )
    
    all_tables = []
    
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                # Clean table data
                cleaned = []
                for row in table:
                    cleaned_row = []
                    for cell in row:
                        if cell is None:
                            cleaned_row.append('')
                        else:
                            # Strip whitespace and normalize
                            cleaned_row.append(str(cell).strip())
                    # Skip empty rows
                    if any(cell for cell in cleaned_row):
                        cleaned.append(cleaned_row)
                if cleaned:
                    all_tables.append(cleaned)
    
    return all_tables


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract raw text from a PDF file.
    Used as fallback when table extraction fails.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required for PDF extraction.")
    
    text_parts = []
    
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    
    return '\n'.join(text_parts)


# Mapping of common financial terms to our standard field names. English only;
# includes wording common in English-language filings from India, China, Japan
# and South Korea.
FIELD_ALIASES = {
    'revenue': ['revenue', 'sales', 'net sales', 'total revenue', 'net revenue', 'turnover',
                'revenue from operations', 'operating revenue', 'income from operations'],
    'cost_of_goods_sold': ['cost of goods sold', 'cogs', 'cost of revenue', 'cost of sales',
                           'cost of materials consumed'],
    'gross_profit': ['gross profit', 'gross margin', 'gross income'],
    'operating_income': ['operating income', 'operating profit', 'ebit', 'income from operations',
                         'profit from operations'],
    'net_income': ['net income', 'net profit', 'net earnings', 'profit after tax', 'bottom line',
                   'profit for the year', 'profit for the period',
                   'profit attributable to owners of parent',
                   'profit attributable to owners of the parent'],
    'total_assets': ['total assets', 'assets', 'total current and non-current assets'],
    'current_assets': ['current assets', 'total current assets'],
    'cash': ['cash', 'cash and cash equivalents', 'cash & equivalents',
             'cash and bank balances', 'cash and deposits', 'cash at bank and on hand'],
    'accounts_receivable': ['accounts receivable', 'receivables', 'trade receivables',
                            'sundry debtors', 'notes and accounts receivable'],
    'inventory': ['inventory', 'inventories', 'stock', 'stock in trade'],
    'total_liabilities': ['total liabilities', 'liabilities', 'total current and non-current liabilities'],
    'current_liabilities': ['current liabilities', 'total current liabilities'],
    'total_equity': ['total equity', 'shareholders equity', 'stockholders equity', 'owners equity',
                     'total shareholders\' equity', 'net assets', 'total net assets', 'net worth',
                     'shareholders\' funds', 'shareholders funds'],
    'interest_expense': ['interest expense', 'interest paid', 'interest and finance costs',
                         'finance costs', 'finance cost', 'interest expenses'],
    'tax_expense': ['income tax expense', 'tax expense', 'provision for tax', 'income taxes',
                    'provision for taxation'],
    'retained_earnings': ['retained earnings', 'accumulated earnings', 'retained profit',
                          'reserves and surplus'],
    'ebit': ['ebit', 'operating income', 'operating profit', 'earnings before interest and taxes',
             'profit before interest and tax'],
}

# Unit words that may follow a figure, e.g. "12.5 crore", "3 lakh", "1.2 bn".
# Checked longest first so "crore" is not read as a trailing "e" or "m".
_UNIT_SUFFIXES = [
    ('trillion', 1_000_000_000_000), ('billion', 1_000_000_000), ('million', 1_000_000),
    ('thousand', 1_000), ('crores', 10_000_000), ('crore', 10_000_000),
    ('lakhs', 100_000), ('lakh', 100_000), ('lacs', 100_000), ('lac', 100_000),
    ('bn', 1_000_000_000), ('mn', 1_000_000), ('cr', 10_000_000),
    ('b', 1_000_000_000), ('m', 1_000_000), ('k', 1_000),
]


def _parse_number(text: str) -> Optional[float]:
    """
    Parse a financial number from text.
    Handles: 1,234.56 | 1234.56 | (1,234.56) | -1,234.56 | 1.23M | 1.23B
    and Indian units and grouping: 12.5 crore | 3 lakh | 1,23,45,678
    """
    if not text:
        return None

    text = text.strip()

    # Handle parentheses as negative (accounting format)
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]

    # Remove currency symbols/codes and whitespace
    text = re.sub(r'[$\u20ac\u00a3\u00a5\u20b9\u20a9]\s*', '', text)
    text = re.sub(r'(?i)\b(?:INR|CNY|RMB|JPY|KRW|USD)\b|\bRs\.?', '', text)
    text = re.sub(r'\s+', '', text)

    # Handle unit suffixes (thousand/million/billion, crore/lakh)
    multiplier = 1.0
    lowered = text.lower()
    for suffix, mult in _UNIT_SUFFIXES:
        if lowered.endswith(suffix):
            multiplier = mult
            text = text[:-len(suffix)]
            break

    # Remove commas
    text = text.replace(',', '')

    # Try to parse
    try:
        value = float(text) * multiplier
        return value
    except ValueError:
        return None


def _match_field(label: str) -> Optional[str]:
    """
    Match a table header/label to a standard field name.
    Returns the standard field name or None. When several aliases appear in the
    label, the longest alias wins, so "cost of sales" maps to cost of goods sold rather
    than to revenue via "sales".
    """
    label_lower = label.strip().lower().replace('\u2019', "'")
    if not label_lower:
        return None

    # Pass 1: an alias contained in the label; the longest alias wins.
    best_field = None
    best_length = 0
    for field_name, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in label_lower and len(alias) > best_length:
                best_field = field_name
                best_length = len(alias)
    if best_field:
        return best_field

    # Pass 2: a short label contained in an alias (e.g. "equity"); the
    # shortest (closest) alias wins.
    if len(label_lower) < 3:
        return None
    for field_name, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if label_lower in alias and (best_field is None or len(alias) < best_length):
                best_field = field_name
                best_length = len(alias)

    return best_field


def extract_financial_data_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Main extraction function.
    Extracts financial figures from a PDF and returns a structured dict
    compatible with the analyzer service.
    
    Returns:
        dict with extracted financial figures, or raises ValueError if extraction fails.
    """
    # Strategy 1: Extract tables
    tables = extract_tables_from_pdf(pdf_bytes)
    
    extracted = {}
    
    if tables:
        # Process each table to find financial figures
        for table in tables:
            if len(table) < 2:
                continue
            
            # Try to identify if this is a key-value table or a matrix table
            for row_idx, row in enumerate(table):
                for col_idx, cell in enumerate(row):
                    field = _match_field(cell)
                    if field:
                        # Look for the value in the same row (next column) or next row
                        value = None
                        
                        # Try same row, next columns
                        for next_col in range(col_idx + 1, len(row)):
                            v = _parse_number(row[next_col])
                            if v is not None:
                                value = v
                                break
                        
                        # Try next row, same or next column
                        if value is None and row_idx + 1 < len(table):
                            next_row = table[row_idx + 1]
                            for next_col in range(col_idx, len(next_row)):
                                v = _parse_number(next_row[next_col])
                                if v is not None:
                                    value = v
                                    break
                        
                        if value is not None and field not in extracted:
                            extracted[field] = value
    
    # Strategy 2: If table extraction didn't find enough, try text extraction
    if len(extracted) < 5:
        text = extract_text_from_pdf(pdf_bytes)
        
        # Find "label: value" or "label  value" patterns
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Try various patterns
            patterns = [
                r'^([A-Za-z\s]+?)\s*[:\-=]\s*([\(\)\-\$\d,\.]+)',
                r'^([A-Za-z][A-Za-z\s]+?)\s{2,}([\(\)\-\$\d,\.]+)',
            ]
            
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    label = match.group(1).strip()
                    value_str = match.group(2).strip()
                    field = _match_field(label)
                    if field and field not in extracted:
                        value = _parse_number(value_str)
                        if value is not None:
                            extracted[field] = value
    
    if len(extracted) < 3:
        raise ValueError(
            f"Could not extract enough financial data from PDF. "
            f"Found {len(extracted)} fields: {list(extracted.keys())}. "
            f"Please ensure the PDF contains a financial statement with recognizable labels."
        )
    
    # Normalize extracted data to match analyzer expectations
    result = {
        'revenue': extracted.get('revenue', 0),
        'cogs': extracted.get('cost_of_goods_sold', 0),
        'gross_profit': extracted.get('gross_profit', 0),
        'net_income': extracted.get('net_income', 0),
        'ebit': extracted.get('ebit', extracted.get('operating_income', 0)),
        'interest_expense': extracted.get('interest_expense', 0),
        'tax_expense': extracted.get('tax_expense', 0),
        'total_assets': extracted.get('total_assets', 0),
        'current_assets': extracted.get('current_assets', 0),
        'cash': extracted.get('cash', 0),
        'accounts_receivable': extracted.get('accounts_receivable', 0),
        'inventory': extracted.get('inventory', 0),
        'total_liabilities': extracted.get('total_liabilities', 0),
        'current_liabilities': extracted.get('current_liabilities', 0),
        'total_equity': extracted.get('total_equity', 0),
        'retained_earnings': extracted.get('retained_earnings', None),
    }
    
    # Compute derived values
    if result['gross_profit'] == 0 and result['revenue'] > 0 and result['cogs'] > 0:
        result['gross_profit'] = result['revenue'] - result['cogs']
    
    if result['total_liabilities'] == 0 and result['total_assets'] > 0 and result['total_equity'] > 0:
        result['total_liabilities'] = result['total_assets'] - result['total_equity']
    
    return {
        'extracted_fields': list(extracted.keys()),
        'field_count': len(extracted),
        'financial_data': result,
    }
