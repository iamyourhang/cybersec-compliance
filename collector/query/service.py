from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.connection import get_cursor
from database.repository import ComplianceIndexRepository


class ComplianceQueryService:
    def list_compliance(
        self,
        country_code: Optional[str] = None,
        entry_type: Optional[str] = None,
        mandatory: Optional[str] = None,
        status: Optional[str] = "active",
        product_code: Optional[str] = None,
        keyword: Optional[str] = None,
        authenticity_status: Optional[str] = None,
        include_suspicious: bool = True,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        return ComplianceIndexRepository.list_filtered(
            country_code=country_code,
            entry_type=entry_type,
            mandatory=mandatory,
            status=status,
            product_code=product_code,
            keyword=keyword,
            authenticity_status=authenticity_status,
            include_suspicious=include_suspicious,
            limit=page_size,
            offset=(page - 1) * page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def query_compliance(self, product_code: str, country_code: str, mandatory_only: bool = False) -> Dict[str, Any]:
        sql = """
            SELECT *
            FROM compliance_index
            WHERE country_code=%s
              AND %s = ANY(applicable_products)
              AND authenticity_status='verified'
              AND status='active'
        """
        params: List[Any] = [country_code, product_code]
        if mandatory_only:
            sql += " AND mandatory='mandatory'"
        sql += " ORDER BY mandatory DESC, entry_type, name"
        with get_cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "product_code": product_code,
            "country_code": country_code,
            "total": len(rows),
            "items": rows,
        }

    def query_regulation(self, keyword: str, country_code: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT *
            FROM compliance_index
            WHERE authenticity_status='verified'
              AND status='active'
              AND name ILIKE %s
        """
        params: List[Any] = [f"%{keyword}%"]
        if country_code:
            sql += " AND country_code=%s"
            params.append(country_code)
        sql += " ORDER BY updated_at DESC LIMIT 5"
        with get_cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def query_all_by_country(self, country_code: str) -> Dict[str, Any]:
        sql = """
            SELECT *
            FROM compliance_index
            WHERE country_code=%s
              AND authenticity_status='verified'
              AND status='active'
            ORDER BY mandatory DESC, entry_type, name
        """
        with get_cursor() as cur:
            cur.execute(sql, (country_code,))
            rows = [dict(row) for row in cur.fetchall()]
        return {
            "product_code": "all",
            "country_code": country_code,
            "total": len(rows),
            "items": rows,
        }


_SERVICE: Optional[ComplianceQueryService] = None


def get_compliance_query_service() -> ComplianceQueryService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ComplianceQueryService()
    return _SERVICE
