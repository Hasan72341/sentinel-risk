"""
Document Intelligence Service — OCR-based financial document extraction.
Supports PDF (native + scanned), Excel, CSV, and image-based statements.
Extracts financial data using a combination of pdfplumber, pytesseract, and regex parsing.

English-language documents only. Label matching covers terminology common in
English filings from India, China, Japan and South Korea.
"""

import re
import io
import pandas as pd
from typing import Optional
from PIL import Image


# English financial term mappings. Besides US/IFRS wording, the list covers
# terminology common in English-language filings from India (Ind AS / Schedule
# III), China, Japan (English "tanshin" summaries) and South Korea (K-IFRS).
FINANCIAL_TERMS_EN = {
    # Revenue
    'revenue': 'revenue', 'net revenue': 'revenue', 'sales': 'revenue', 'net sales': 'revenue',
    'total revenue': 'revenue', 'revenue from operations': 'revenue', 'turnover': 'revenue',
    'net turnover': 'revenue', 'operating revenue': 'revenue', 'income from operations': 'revenue',
    'sales revenue': 'revenue',
    # Cost of sales
    'cost of goods sold': 'cogs', 'cogs': 'cogs', 'cost of revenue': 'cogs', 'cost of sales': 'cogs',
    'cost of materials consumed': 'cogs', 'operating costs': 'cogs',
    # Profit lines
    'gross profit': 'gross_profit',
    'operating income': 'ebit', 'operating profit': 'ebit', 'ebit': 'ebit',
    'profit from operations': 'ebit', 'profit before interest and tax': 'ebit',
    'profit before tax': 'ebt', 'profit before taxation': 'ebt', 'ebt': 'ebt',
    'income before income taxes': 'ebt', 'profit before income tax': 'ebt',
    'ordinary income': 'ebt', 'ordinary profit': 'ebt',
    'net income': 'net_income', 'net profit': 'net_income', 'net earnings': 'net_income',
    'profit after tax': 'net_income', 'profit for the year': 'net_income',
    'profit for the period': 'net_income',
    'profit attributable to owners of parent': 'net_income',
    'profit attributable to owners of the parent': 'net_income',
    'net profit attributable to shareholders': 'net_income',
    # Expenses
    'interest expense': 'interest_expense', 'interest expenses': 'interest_expense',
    'interest': 'interest_expense', 'finance costs': 'interest_expense',
    'finance cost': 'interest_expense',
    'tax expense': 'tax_expense', 'income tax': 'tax_expense', 'income taxes': 'tax_expense',
    'income tax expense': 'tax_expense', 'provision for taxation': 'tax_expense',
    'operating expenses': 'operating_expenses',
    'selling expenses': 'selling_expenses', 'administrative expenses': 'admin_expenses',
    'other income': 'other_income', 'non-operating income': 'other_income',
    'depreciation': 'depreciation', 'depreciation and amortisation': 'depreciation',
    'depreciation and amortization': 'depreciation',
    # Balance sheet
    'total assets': 'total_assets', 'assets': 'total_assets',
    'total equity': 'total_equity', 'shareholders equity': 'total_equity',
    "shareholders' equity": 'total_equity', 'stockholders equity': 'total_equity',
    "stockholders' equity": 'total_equity', "shareholders' funds": 'total_equity',
    'shareholders funds': 'total_equity', 'net worth': 'total_equity',
    'total net assets': 'total_equity', 'net assets': 'total_equity',
    "total owners' equity": 'total_equity', 'total owners equity': 'total_equity',
    'total liabilities': 'total_liabilities',
    'current assets': 'current_assets', 'total current assets': 'current_assets',
    'current liabilities': 'current_liabilities', 'total current liabilities': 'current_liabilities',
    'inventory': 'inventory', 'inventories': 'inventory', 'stock in trade': 'inventory',
    'cash': 'cash', 'cash and equivalents': 'cash', 'cash & equivalents': 'cash',
    'cash and cash equivalents': 'cash', 'cash and bank balances': 'cash',
    'cash and deposits': 'cash', 'cash at bank and on hand': 'cash',
    'accounts receivable': 'accounts_receivable', 'receivables': 'accounts_receivable',
    'trade receivables': 'accounts_receivable', 'sundry debtors': 'accounts_receivable',
    'notes and accounts receivable': 'accounts_receivable',
    'retained earnings': 'retained_earnings', 'reserves and surplus': 'retained_earnings',
    'surplus reserve': 'retained_earnings',
    'fixed assets': 'fixed_assets', 'property, plant and equipment': 'fixed_assets',
    'tangible assets': 'fixed_assets',
    'long term debt': 'long_term_debt', 'long-term debt': 'long_term_debt',
    'long-term borrowings': 'long_term_debt', 'long term borrowings': 'long_term_debt',
    'long-term loans payable': 'long_term_debt', 'bonds payable': 'long_term_debt',
    'working capital': 'working_capital',
}

# Longest term first, so "cost of revenue" is recognised before "revenue" and
# "total current assets" before "assets". Terms match on whole words only.
_TERM_PATTERNS = [
    (re.compile(r'(?<![a-z])' + re.escape(term) + r'(?![a-z])'), key)
    for term, key in sorted(FINANCIAL_TERMS_EN.items(), key=lambda item: -len(item[0]))
]

# Cost lines are reported as positive amounts even when a filing prints them
# in parentheses.
_EXPENSE_KEYS = frozenset({
    'cogs', 'interest_expense', 'tax_expense', 'operating_expenses',
    'selling_expenses', 'admin_expenses', 'depreciation',
})

# Reporting-unit declarations such as "(Rs. in crore)", "INR in lakhs",
# "Millions of yen", "RMB'000" or "KRW in millions".
_UNIT_MULTIPLIERS = [
    (r'crores?|\bcr\b', 'crore', 10_000_000),
    (r'lakhs?|lacs?', 'lakh', 100_000),
    (r'trillions?', 'trillion', 1_000_000_000_000),
    (r'billions?|\bbn\b', 'billion', 1_000_000_000),
    (r'millions?|\bmn\b', 'million', 1_000_000),
    (r"thousands?|'000|\b000s\b", 'thousand', 1_000),
]
_CURRENCY_HINTS = [
    (r'\binr\b|\brs\b\.?|rupees?|\u20b9', 'INR'),
    (r'\bcny\b|\brmb\b|renminbi|yuan', 'CNY'),
    (r'\bjpy\b|\byen\b', 'JPY'),
    (r'\bkrw\b|\bwon\b|\u20a9', 'KRW'),
    (r'\busd\b|us\$|u\.s\. dollars?|us dollars?', 'USD'),
]
_CURRENCY_TOKENS = r'(INR|CNY|RMB|JPY|KRW|USD|Rs\.?|\$|\u20ac|\u00a3|\u00a5|\u20b9|\u20a9)'


def detect_reporting_unit(text: str) -> dict:
    """Detect the reporting currency and unit declared in a statement header.

    Looks for wording such as "(Rs. in crore)", "INR in lakhs", "Millions of
    yen", "RMB'000" or "KRW in millions". Returns ``currency`` (INR, CNY, JPY,
    KRW, USD or None), ``unit`` and the ``multiplier`` that converts a reported
    figure to single currency units (1 crore = 10,000,000; 1 lakh = 100,000).
    Extracted figures are NOT rescaled; this is metadata for the reviewer.
    """
    lowered = text.lower()
    currency = next((code for pattern, code in _CURRENCY_HINTS if re.search(pattern, lowered)), None)
    unit, multiplier = 'units', 1
    # Only trust a unit word when it appears in a declaration ("in crore",
    # "millions of yen", "'000"), not anywhere in running text.
    money = r"(?:rs\.?|inr|indian\s+rupees?|rupees?|cny|rmb|yuan|jpy|yen|krw|won|usd|us\$|\$|\u20b9|\u20a9)"
    declaration = re.search(
        r"\bin\s+(?:" + money + r"\s+)?"
        r"(crores?|cr|lakhs?|lacs?|trillions?|billions?|bn|millions?|mn|thousands?)\b"
        r"|(trillions?|billions?|millions?|thousands?)\s+of\s+(?:u\.s\.\s+|korean\s+|japanese\s+|indian\s+)?"
        r"(?:rupees|yuan|yen|won|dollars|inr|rmb|cny|jpy|krw|usd)"
        r"|('000|\b000s\b)",
        lowered,
    )
    if declaration:
        word = next(group for group in declaration.groups() if group)
        for pattern, name, value in _UNIT_MULTIPLIERS:
            if re.fullmatch(pattern.replace('\b', ''), word):
                unit, multiplier = name, value
                break
    return {'currency': currency, 'unit': unit, 'multiplier': multiplier}


def _normalize_text(text: str) -> str:
    """Normalise typographic apostrophes so "shareholders' funds" matches."""
    return text.replace('\u2019', "'").replace('\u2018', "'")


def _extract_number(text: str) -> Optional[float]:
    """Extract a number from text, handling commas and parentheses (negative)."""
    text = text.strip()
    # Remove common currency prefixes/suffixes
    text = re.sub(_CURRENCY_TOKENS, '', text, flags=re.IGNORECASE).strip()
    # Handle parentheses for negative numbers
    if re.match(r'^\([\d,.]+\)$', text):
        text = '-' + text.strip('()')
    # Remove commas and spaces within numbers (also covers 1,23,45,678 grouping)
    text = re.sub(r'[\s,]', '', text)
    # Extract first number
    match = re.search(r'-?[\d]+(?:\.\d+)?', text)
    return float(match.group()) if match else None


def _parse_line_items(text: str) -> dict:
    """Parse key-value pairs from OCR text lines."""
    results = {}
    lines = _normalize_text(text).split('\n')

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        line_lower = line_stripped.lower()

        for pattern, key in _TERM_PATTERNS:
            # Check if the line contains this financial term
            if pattern.search(line_lower):
                # Try to extract the number from the line
                # Strategy: find the last number on the line (usually the value).
                # A value in accounting parentheses, e.g. (1,234), is negative,
                # except on cost lines, which stay positive.
                numbers = re.findall(r'\(?-?\d[\d,]*(?:\.\d+)?\)?', line_stripped)
                if numbers:
                    token = numbers[-1]
                    negative = token.startswith('(') and token.endswith(')')
                    value_str = token.strip('()').replace(',', '')
                    try:
                        value = float(value_str)
                        if negative and key not in _EXPENSE_KEYS:
                            value = -value
                        if key not in results:  # First match wins
                            results[key] = value
                    except ValueError:
                        pass
                break

    return results


def extract_from_text(text: str) -> dict:
    """Extract financial data from raw English text (OCR output or pasted text)."""
    data = _parse_line_items(text)
    
    # Apply basic validation and derived calculations
    if 'gross_profit' not in data and 'revenue' in data and 'cogs' in data:
        data['gross_profit'] = data['revenue'] - data['cogs']
    if 'total_liabilities' not in data and 'total_assets' in data and 'total_equity' in data:
        data['total_liabilities'] = data['total_assets'] - data['total_equity']
    if 'ebit' not in data and 'net_income' in data and 'tax_expense' in data and 'interest_expense' in data:
        data['ebit'] = data['net_income'] + data['tax_expense'] + data['interest_expense']
    
    return data


def extract_from_pdf(file_content: bytes, use_ocr: bool = False) -> dict:
    """Extract financial data from PDF.
    
    Args:
        file_content: Raw PDF bytes
        use_ocr: Force OCR mode (for scanned PDFs)
    
    Returns:
        dict with 'financial_data', 'extraction_method', 'confidence', 'raw_text'
    """
    import pdfplumber
    
    pdf_file = io.BytesIO(file_content)
    
    # Try native PDF text extraction first
    financial_data = {}
    raw_text = ''
    extraction_method = 'native'
    confidence = 0.9
    
    if not use_ocr:
        try:
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    raw_text += text + '\n'
                    
                    # Try table extraction
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row:
                                row_text = ' | '.join(str(cell or '') for cell in row)
                                raw_text += row_text + '\n'
                    
                    financial_data.update(_parse_line_items(text))
        except Exception:
            pass
    
    # If native extraction yielded little data, try OCR
    if len(financial_data) < 3 or use_ocr:
        try:
            ocr_data, ocr_text = _ocr_extract(file_content)
            if len(ocr_data) > len(financial_data):
                financial_data = ocr_data
                raw_text = ocr_text
                extraction_method = 'ocr'
                confidence = 0.7
        except Exception:
            if not financial_data:
                extraction_method = 'failed'
                confidence = 0.0
    
    return {
        'financial_data': financial_data,
        'extraction_method': extraction_method,
        'confidence': confidence,
        'fields_found': len(financial_data),
        'raw_text': raw_text[:5000],  # Limit raw text
        'reporting_unit': detect_reporting_unit(raw_text),
    }


def _ocr_extract(file_content: bytes) -> tuple[dict, str]:
    """OCR extraction from PDF pages."""
    import pytesseract
    from pdf2image import convert_from_bytes
    
    images = convert_from_bytes(file_content, dpi=300)
    all_text = ''
    
    for img in images:
        # English OCR
        text = pytesseract.image_to_string(
            img,
            lang='eng',
            config='--psm 6'
        )
        all_text += text + '\n'
    
    financial_data = _parse_line_items(all_text)
    return financial_data, all_text


def extract_from_image(file_content: bytes) -> dict:
    """Extract financial data from an image file (PNG, JPG, etc.)."""
    import pytesseract
    
    img = Image.open(io.BytesIO(file_content))
    
    text = pytesseract.image_to_string(img, lang='eng', config='--psm 6')
    
    financial_data = _parse_line_items(text)
    
    return {
        'financial_data': financial_data,
        'extraction_method': 'ocr',
        'confidence': 0.65,
        'fields_found': len(financial_data),
        'raw_text': text[:5000],
        'reporting_unit': detect_reporting_unit(text),
    }


def extract_from_excel(file_content: bytes, filename: str) -> dict:
    """Smart extraction from Excel with multi-sheet support and header detection."""
    financial_data = {}
    raw_text = ''
    
    try:
        xls = pd.ExcelFile(io.BytesIO(file_content))
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            raw_text += f"--- Sheet: {sheet_name} ---\n"
            
            for _, row in df.iterrows():
                row_text = ' | '.join(str(v) for v in row if pd.notna(v))
                raw_text += row_text + '\n'
                financial_data.update(_parse_line_items(row_text))
    except Exception:
        pass
    
    # Derived calculations
    if 'gross_profit' not in financial_data and 'revenue' in financial_data and 'cogs' in financial_data:
        financial_data['gross_profit'] = financial_data['revenue'] - financial_data['cogs']
    if 'total_liabilities' not in financial_data and 'total_assets' in financial_data and 'total_equity' in financial_data:
        financial_data['total_liabilities'] = financial_data['total_assets'] - financial_data['total_equity']
    
    return {
        'financial_data': financial_data,
        'extraction_method': 'structured',
        'confidence': 0.95,
        'fields_found': len(financial_data),
        'raw_text': raw_text[:5000],
        'reporting_unit': detect_reporting_unit(raw_text),
    }


def detect_document_type(text: str) -> str:
    """Detect the type of financial document from extracted text."""
    text_lower = text.lower()
    
    if any(w in text_lower for w in ['balance sheet', 'statement of financial position', 'position statement']):
        return 'balance_sheet'
    if any(w in text_lower for w in ['income statement', 'statement of income', 'profit and loss', 'profit or loss']):
        return 'income_statement'
    if any(w in text_lower for w in ['cash flow', 'cashflow']):
        return 'cash_flow'
    if any(w in text_lower for w in ['stockholders', 'equity', 'net assets']):
        return 'equity_statement'
    
    return 'mixed'


def analyze_extraction_quality(financial_data: dict) -> dict:
    """Analyze the quality of extracted data and suggest improvements."""
    critical_fields = ['revenue', 'net_income', 'total_assets', 'total_liabilities', 'total_equity']
    found = [f for f in critical_fields if f in financial_data]
    missing = [f for f in critical_fields if f not in financial_data]
    
    completeness = len(found) / len(critical_fields)
    
    # Check for reasonable ranges
    warnings = []
    for key, value in financial_data.items():
        if key in ('revenue', 'total_assets', 'total_liabilities', 'total_equity'):
            if value < 0:
                warnings.append(f"{key} is negative ({value}), please verify")
            elif value == 0:
                warnings.append(f"{key} is zero, may indicate extraction error")
        if key == 'net_income' and abs(value) > (financial_data.get('revenue', 0) * 2):
            warnings.append("net_income exceeds 2x revenue, please verify")
    
    # Balance sheet check
    if all(k in financial_data for k in ['total_assets', 'total_liabilities', 'total_equity']):
        expected = financial_data['total_liabilities'] + financial_data['total_equity']
        actual = financial_data['total_assets']
        diff_pct = abs(expected - actual) / max(abs(expected), 1) * 100
        if diff_pct > 5:
            warnings.append(f"Balance sheet doesn't balance: Assets={actual}, L+E={expected} ({diff_pct:.1f}% diff)")
    
    return {
        'completeness': round(completeness, 2),
        'fields_found': len(financial_data),
        'critical_found': len(found),
        'critical_missing': missing,
        'warnings': warnings,
        'quality_score': round(completeness * 100 - len(warnings) * 10, 1),
    }
