from __future__ import annotations

from typing import Any


def _evidence(document: str, page: int, printed: str, text: str, bbox: list[float] | None = None) -> dict[str, Any]:
    return {
        "document": document,
        "pdf_page": page,
        "printed_page": printed,
        "text": text,
        "bbox": bbox,
        "precision": "word-region" if bbox else "page-only",
    }


DEMO_WORKSPACES = [
    {"id": "delhivery", "name": "Delhivery", "description": "Company disclosures across prospectus, annual report, and earnings presentation."},
    {"id": "india-macro", "name": "India Macroeconomy", "description": "Institutional reports with overlapping macroeconomic series and vintages."},
]

DEMO_DOCUMENTS = [
    {"id": "delhivery-prospectus", "workspace_id": "delhivery", "name": "Delhivery Prospectus 2022 · curated excerpt", "publisher": "Delhivery Limited", "source_url": "https://www.delhivery.com/wp-content/uploads/2022/05/Delhivery-Limited-Prospectus-1-min.pdf", "page_count": 100, "published_at": "2022-05-14"},
    {"id": "delhivery-annual", "workspace_id": "delhivery", "name": "Delhivery Annual Report FY24 · curated excerpt", "publisher": "Delhivery Limited", "source_url": "https://www.delhivery.com/uploads/2024/08/Annual_Report_FY24.pdf", "page_count": 100, "published_at": "2024-08-01"},
    {"id": "delhivery-presentation", "workspace_id": "delhivery", "name": "Delhivery Q4 FY24 Earnings Presentation", "publisher": "Delhivery Limited", "source_url": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/d70668ee-4f13-485e-ba19-62bec5116a59.pdf", "page_count": 27, "published_at": "2024-05-17"},
    {"id": "economic-survey", "workspace_id": "india-macro", "name": "Economic Survey 2024–25 · curated excerpt", "publisher": "Government of India", "source_url": "https://www.indiabudget.gov.in/budget2025-26/economicsurvey/doc/echapter.pdf", "page_count": 89, "published_at": "2025-01-31"},
    {"id": "rbi-report", "workspace_id": "india-macro", "name": "RBI Annual Report 2024–25 · curated excerpt", "publisher": "Reserve Bank of India", "source_url": "https://rbidocs.rbi.org.in/rdocs/AnnualReport/PDFs/0ANNUALREPORT202425DA4AE08189C848C8846718B080F2A0A9.PDF", "page_count": 100, "published_at": "2025-05-29"},
    {"id": "imf-report", "workspace_id": "india-macro", "name": "IMF India 2025 Article IV Consultation", "publisher": "International Monetary Fund", "source_url": "https://www.imf.org/en/publications/cr/issues/2025/11/25/india-2025-article-iv-consultation-press-release-staff-report-and-statement-by-the-572056", "page_count": 95, "published_at": "2025-11-25"},
]

DEMO_CLAIMS = [
    {"id": "clm-delhivery-revenue-annual", "workspace_id": "delhivery", "document_id": "delhivery-annual", "subject": "Delhivery", "predicate": "revenue_from_services", "raw_value": "₹81,415.38 million", "normalized_value": "81415380000", "value_type": "money", "unit": "INR", "precision": 2, "period": "FY24", "modality": "actual", "scope": "consolidated", "evidence": _evidence("Delhivery Annual Report FY24", 85, "249", "Revenue from services 81,415.38 72,236.47. Revenue from contracts with customers totaled 81,415.38 million for FY24.", [1027.8, 120.0, 1120.0, 220.0])},
    {"id": "clm-delhivery-revenue-presentation", "workspace_id": "delhivery", "document_id": "delhivery-presentation", "subject": "Delhivery", "predicate": "revenue_from_services", "raw_value": "₹8,142 crore", "normalized_value": "81420000000", "value_type": "money", "unit": "INR", "precision": 0, "period": "FY24", "modality": "actual", "scope": "consolidated", "evidence": _evidence("Delhivery Q4 FY24 Earnings Presentation", 6, "5", "₹8,142 Cr FY24 revenue from services. YoY: 12.7%.", [75.0, 145.0, 330.0, 210.0])},
    {"id": "clm-delhivery-service-fy23", "workspace_id": "delhivery", "document_id": "delhivery-annual", "subject": "Delhivery", "predicate": "revenue_from_services", "raw_value": "₹72,236.47 million", "normalized_value": "72236470000", "value_type": "money", "unit": "INR", "period": "FY23", "modality": "actual", "scope": "consolidated", "evidence": _evidence("Delhivery Annual Report FY24", 85, "249", "Sale of services. Revenue from services 81,415.38 72,236.47.")},
    {"id": "clm-delhivery-customer-fy23", "workspace_id": "delhivery", "document_id": "delhivery-annual", "subject": "Delhivery", "predicate": "revenue_from_contracts_with_customers", "raw_value": "₹72,253.01 million", "normalized_value": "72253010000", "value_type": "money", "unit": "INR", "period": "FY23", "modality": "actual", "scope": "consolidated", "evidence": _evidence("Delhivery Annual Report FY24", 85, "249", "Total revenue from customers 81,415.38 72,253.01; the FY23 total includes revenue from traded goods.")},
    {"id": "clm-suvir-prospectus", "workspace_id": "delhivery", "document_id": "delhivery-prospectus", "subject": "Suvir Suren Sujan", "predicate": "director_role", "raw_value": "Non-Executive Nominee Director", "normalized_value": "director", "value_type": "semantic", "unit": None, "period": "2022-05-14", "modality": "actual", "scope": "Delhivery Limited", "evidence": _evidence("Delhivery Prospectus 2022", 88, "262", "Suvir Suren Sujan is a Non-Executive Nominee Director of our Company.")},
    {"id": "clm-suvir-resignation", "workspace_id": "delhivery", "document_id": "delhivery-annual", "subject": "Suvir Suren Sujan", "predicate": "director_role", "raw_value": "resigned from the Board with effect from August 24, 2023", "normalized_value": "ceased", "value_type": "semantic", "unit": None, "period": "2023-08-24", "modality": "actual", "scope": "Delhivery Limited", "evidence": _evidence("Delhivery Annual Report FY24", 24, "24", "Mr. Suvir Suren Sujan, Non-Executive Director, resigned from the Board with effect from August 24, 2023.")},
    {"id": "clm-survey-gdp-fy25", "workspace_id": "india-macro", "document_id": "economic-survey", "subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.4 per cent", "normalized_value": "0.064", "value_type": "percentage", "unit": "%", "period": "FY25", "modality": "estimate", "scope": "India", "evidence": _evidence("Economic Survey 2024–25", 4, "4", "As per the first advance estimates of national accounts, India’s real GDP is estimated to grow by 6.4 per cent in FY25.")},
    {"id": "clm-rbi-gdp-fy25", "workspace_id": "india-macro", "document_id": "rbi-report", "subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.5 per cent", "normalized_value": "0.065", "value_type": "percentage", "unit": "%", "period": "FY25", "modality": "estimate", "scope": "India", "evidence": _evidence("RBI Annual Report 2024–25", 8, "3", "All references to GDP data in this Report are based on the Second Advance Estimates (SAE) of National Income 2024–25 released on February 28, 2025.")},
    {"id": "clm-rbi-gdp-fy26", "workspace_id": "india-macro", "document_id": "rbi-report", "subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.5 per cent projected", "normalized_value": "0.065", "value_type": "percentage", "unit": "%", "period": "FY26", "modality": "forecast", "scope": "India", "evidence": _evidence("RBI Annual Report 2024–25", 17, "12", "Taking into account these factors, real GDP growth for 2025-26 is projected at 6.5 per cent.")},
    {"id": "clm-imf-gdp-fy26", "workspace_id": "india-macro", "document_id": "imf-report", "subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.6 percent projected", "normalized_value": "0.066", "value_type": "percentage", "unit": "%", "period": "FY26", "modality": "forecast", "scope": "India", "evidence": _evidence("IMF India 2025 Article IV Consultation", 3, "2", "Under the baseline assumption of prolonged 50 percent U.S. tariffs, real GDP is projected to grow at 6.6 percent in FY2025/26.")},
]

DEMO_RELATIONSHIPS = [
    {"id": "rel-revenue-corroborates", "workspace_id": "delhivery", "claim_a": "clm-delhivery-revenue-annual", "claim_b": "clm-delhivery-revenue-presentation", "relationship_type": "CORROBORATES", "reason": "₹8,142 crore normalizes to ₹81.42 billion; the 0.006% display difference is explained by presentation rounding.", "dimensions": {"subject": "MATCH", "predicate": "MATCH", "period": "MATCH", "unit": "EQUIVALENT", "value": "ROUNDING_COMPATIBLE", "independence": "SAME_ISSUER"}, "confidence": 0.96},
    {"id": "rel-director-supersedes", "workspace_id": "delhivery", "claim_a": "clm-suvir-prospectus", "claim_b": "clm-suvir-resignation", "relationship_type": "SUPERSEDES", "reason": "The later evidenced resignation ends the earlier director role from August 24, 2023; it does not invalidate the 2022 disclosure.", "dimensions": {"subject": "MATCH", "predicate": "MATCH", "effective_time": "CHANGED", "value": "STATE_CHANGE"}, "confidence": 0.99},
    {"id": "rel-gdp-vintage", "workspace_id": "india-macro", "claim_a": "clm-survey-gdp-fy25", "claim_b": "clm-rbi-gdp-fy25", "relationship_type": "RECONCILES", "reason": "The 6.4% first advance estimate and 6.5% second advance estimate are different data vintages for FY25.", "dimensions": {"subject": "MATCH", "predicate": "MATCH", "period": "MATCH", "modality": "MATCH", "data_vintage": "DIFFERENT", "value": "DIFFERENT"}, "confidence": 0.98},
    {"id": "rel-gdp-forecast", "workspace_id": "india-macro", "claim_a": "clm-rbi-gdp-fy26", "claim_b": "clm-imf-gdp-fy26", "relationship_type": "CONTRADICTS", "reason": "Both are FY26 real GDP projections for India, but they differ by 10 basis points and retain different institutional assumptions and vintages.", "dimensions": {"subject": "MATCH", "predicate": "MATCH", "period": "MATCH", "modality": "MATCH", "assumptions": "DIFFERENT", "value": "DIFFERENT"}, "confidence": 0.89},
]

DEMO_CASES = [
    {"id": "case-corroboration", "number": 1, "title": "FY24 service revenue", "label": "Corroboration", "workspace_id": "delhivery", "relationship_id": "rel-revenue-corroborates", "description": "Two Delhivery disclosures use different scales for the same FY24 service-revenue metric."},
    {"id": "case-conflict", "number": 2, "title": "FY26 GDP projection", "label": "Likely conflict", "workspace_id": "india-macro", "relationship_id": "rel-gdp-forecast", "description": "RBI and IMF publish competing FY26 projections; the system preserves both instead of choosing a winner."},
    {"id": "case-reconciliation", "number": 3, "title": "FY25 GDP data vintage", "label": "Contextual reconciliation", "workspace_id": "india-macro", "relationship_id": "rel-gdp-vintage", "description": "The 6.4% and 6.5% figures use first and second advance estimates respectively."},
    {"id": "case-failure", "number": 4, "title": "IMF cover native extraction", "label": "Observed failure", "workspace_id": "india-macro", "relationship_id": None, "description": "The IMF cover is visually readable but produces no native text; Project SuperJoin routes it to visual fallback or keeps it quarantined."},
]
