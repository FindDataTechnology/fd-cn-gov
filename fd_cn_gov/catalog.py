"""fd-cn-gov datasource manifest conforming to fd-open-data-protocol.

This module exposes a DatasourceManifest-compatible CATALOG for Chinese
central-government ministry open-information archives (11 ministries).
Loadable via: load_catalog("fd_cn_gov.catalog:CATALOG")
"""
from __future__ import annotations

CATALOG = {
    "version": "1",
    "name": "fd-cn-gov",
    "label": "Chinese Central Government Archives",
    "source_url": "https://github.com/FindDataTechnology/finddata/tree/main/fd-cn-gov",
    "ranking_seed": [0.85, 0.7],
    "scanner_mode": "full",
    "functions": [
        # MEE - Ministry of Ecology and Environment
        {
            "command": "mee_gsgg_archive",
            "category": "public_notice",
            "description": "MEE Public Announcement Archive (公示公告)",
            "frequency": "daily",
            "parameters": [
                {"name": "page_size", "type": "int", "required": False, "description": "Items per page (default 20)"},
                {"name": "page_num", "type": "int", "required": False, "description": "Page number"},
            ],
            "columns": [
                {"name": "section", "type": "str", "description": "Archive section type"},
                {"name": "title", "type": "str", "description": "Document title"},
                {"name": "date", "type": "date", "description": "Publish date YYYY-MM-DD"},
                {"name": "url", "type": "url", "description": "Document URL (.shtml)"},
                {"name": "doc_type", "type": "str", "description": "HTML or PDF"},
            ],
        },
        {
            "command": "mee_tzgg_archive",
            "category": "public_notice",
            "description": "MEE Notice & Notification Archive (通知公告)",
            "frequency": "daily",
            "parameters": [],
            "columns": [
                {"name": "section", "type": "str", "description": "Archive section"},
                {"name": "title", "type": "str", "description": "Document title"},
                {"name": "date", "type": "date", "description": "Publish date"},
                {"name": "url", "type": "url", "description": "Document URL"},
                {"name": "doc_type", "type": "str", "description": "Format"},
            ],
        },
        # MEM - Ministry of Emergency Management
        {
            "command": "mem_tzgg_archive",
            "category": "public_notice",
            "description": "MEM Notice & Notification Archive",
            "frequency": "daily",
            "parameters": [],
            "columns": [
                {"name": "title", "type": "str", "description": "Document title"},
                {"name": "date", "type": "date", "description": "Publish date"},
                {"name": "url", "type": "url", "description": "Document URL"},
            ],
        },
        # MDRC - Ministry of Human Resources and Social Security
        {
            "command": "mohrs_wj_gh",
            "category": "policy",
            "description": "MOHRS General Policy Documents (政策规章)",
            "frequency": "weekly",
            "parameters": [],
            "columns": [
                {"name": "department", "type": "str", "description": "Issuing department"},
                {"name": "title", "type": "str", "description": "Policy title"},
                {"name": "number", "type": "str", "description": "Document number"},
                {"name": "publish_date", "type": "date", "description": "Publication date"},
                {"name": "effective_date", "type": "date", "description": "Effective date"},
                {"name": "url", "type": "url", "description": "PDF download URL"},
            ],
        },
        # NDRC - National Development and Reform Commission
        {
            "command": "ndrc_wj",
            "category": "policy",
            "description": "NDRC Policy Documents",
            "frequency": "weekly",
            "parameters": [],
            "columns": [
                {"name": "title", "type": "str", "description": "Document title"},
                {"name": "publish_date", "type": "date", "description": "Publication date"},
                {"name": "url", "type": "url", "description": "Document URL"},
            ],
        },
        # MIIT - Ministry of Industry and Information Technology
        {
            "command": "miit_wj",
            "category": "policy",
            "description": "MIIT Policy Documents",
            "frequency": "weekly",
            "parameters": [],
            "columns": [
                {"name": "title", "type": "str", "description": "Document title"},
                {"name": "publish_date", "type": "date", "description": "Publication date"},
                {"name": "url", "type": "url", "description": "Document URL"},
            ],
        },
    ],
    "concepts": [
        # Government document concepts
        {"column": "title", "concept": "document.title", "entity_type": "organization", "measure": "official_document", "unit": "string", "frequency": "variable"},
        {"column": "date", "concept": "document.publish_date", "entity_type": "organization", "measure": "publication_date", "unit": "date", "frequency": "variable"},
        {"column": "url", "concept": "document.url", "entity_type": "organization", "measure": "document_url", "unit": "url", "frequency": "variable"},
        {"column": "doc_type", "concept": "document.format", "entity_type": "organization", "measure": "format_type", "unit": "categorical", "frequency": "variable"},
        # Taxonomy concepts for unified classification
        {"column": "taxonomy_code", "concept": "taxonomy.report_section", "entity_type": "industry", "measure": "report_section_classification", "unit": "string", "frequency": "static"},
        {"column": "document_type_codes", "concept": "taxonomy.document_type", "entity_type": "organization", "measure": "document_type_classification", "unit": "array", "frequency": "static"},
    ],
    "entities": [
        {"entity_type": "organization", "coverage": "universe"},
        {"entity_type": "country", "coverage": "explicit", "codes": ["CN"]},
    ],
    "fetch": {"runner": "fd-cn-gov"},
}


class FDcnGovProvider:
    """DataProvider class for fd-open-data-protocol compatibility."""

    name = "fd-cn-gov"

    def registry(self) -> dict:
        """Return the CATALOG."""
        return CATALOG

    def run(self, command: str, params: dict):
        """Execute a command via the CLI dispatcher."""
        from fd_cn_gov.cli import dispatch
        return dispatch(command, params)
