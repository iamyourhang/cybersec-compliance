#!/usr/bin/env python3
"""Promote exact official-source entries into link-only verified records.

This is for cases where the official source registry already contains a specific
government PDF/HTML legal text or strategy page. Generic agency homepages are not
included here because they are discovery frontiers, not verified compliance records.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_cursor
from scripts.import_curated_official_docs import ensure_record, register_link_only_source


DEFAULT_PRODUCTS = ["software", "cloud_desktop", "security_gateway", "industrial_gateway"]

PROMOTABLE_OFFICIAL_SOURCES: list[dict[str, Any]] = [
    {
        "source_name": "Barbados Computer Misuse Act Official Laws Source",
        "record_name": "Barbados Computer Misuse Act",
        "country_code": "BB",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Parliament of Barbados / Barbados Parliament Laws",
        "scope_description": "巴巴多斯 Computer Misuse Act 官方法律文本，覆盖计算机误用、未授权访问、数据/系统相关违法行为和执法条款。",
    },
    {
        "source_name": "Burundi ARCT Cybercrime Law",
        "record_name": "Burundi Law No. 1/10 of 16 March 2022 on Cybercrime",
        "country_code": "BI",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Agence de Régulation et de Contrôle des Télécommunications (ARCT)",
        "scope_description": "布隆迪 2022 年网络犯罪防治官方法规页面，覆盖网络犯罪预防、惩治和执法协作。",
    },
    {
        "source_name": "Bahamas Computer Misuse Act Official Laws Source",
        "record_name": "Bahamas Computer Misuse Act 2003",
        "country_code": "BS",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Government of The Bahamas Laws",
        "scope_description": "巴哈马 Computer Misuse Act 官方 PDF，覆盖计算机误用、未授权访问和相关犯罪。",
    },
    {
        "source_name": "Botswana Cybercrime and Computer Related Crimes Act",
        "record_name": "Botswana Cybercrime and Computer Related Crimes Act 2018",
        "country_code": "BW",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Botswana Communications Regulatory Authority (BOCRA)",
        "scope_description": "博茨瓦纳 Cybercrime and Computer Related Crimes Act 官方监管页面，覆盖网络犯罪和计算机相关犯罪。",
    },
    {
        "source_name": "Belize National Assembly Cybercrime Act",
        "record_name": "Belize Cybercrime Act 2020",
        "country_code": "BZ",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "National Assembly of Belize",
        "scope_description": "伯利兹 Cybercrime Act 官方 PDF，覆盖网络犯罪、电子证据、执法和相关处罚。",
    },
    {
        "source_name": "DRC Presidency National Cybersecurity Strategy",
        "record_name": "Democratic Republic of the Congo National Cybersecurity Strategy",
        "country_code": "CD",
        "entry_type": "standard",
        "mandatory": "recommended",
        "issuing_body": "Presidency of the Democratic Republic of the Congo",
        "scope_description": "刚果（金）国家网络安全战略官方页面，覆盖国家网络安全治理、能力建设和关键领域保护方向。",
    },
    {
        "source_name": "Cabo Verde National Cybersecurity Strategy Government Source",
        "record_name": "Cabo Verde National Cybersecurity Strategy",
        "country_code": "CV",
        "entry_type": "standard",
        "mandatory": "recommended",
        "issuing_body": "Government of Cabo Verde",
        "scope_description": "佛得角国家网络安全战略官方政府页面，覆盖国家网络安全治理、能力建设和风险管理方向。",
    },
    {
        "source_name": "Republic of Congo Official Journal Cybersecurity Laws",
        "record_name": "Republic of Congo Law No. 27-2020 on Cybersecurity",
        "country_code": "CG",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Secrétariat Général du Gouvernement de la République du Congo",
        "scope_description": "刚果共和国 2020 年第 27 号网络安全相关官方公报 PDF，覆盖国家网络安全法律框架、网络犯罪和信息系统安全相关条款。",
    },
    {
        "source_name": "Guatemala CONCIBER National Cybersecurity Strategy",
        "record_name": "Guatemala National Cybersecurity Strategy",
        "country_code": "GT",
        "entry_type": "standard",
        "mandatory": "recommended",
        "issuing_body": "CONCIBER Guatemala",
        "scope_description": "危地马拉国家网络安全战略官方 PDF，覆盖国家网络安全治理、公共部门协调、能力建设和风险管理。",
    },
    {
        "source_name": "Guyana Cybercrime Act Parliament Source",
        "record_name": "Guyana Cybercrime Act 2018",
        "country_code": "GY",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Parliament of Guyana",
        "scope_description": "圭亚那 Cybercrime Act 2018 官方议会页面，覆盖网络犯罪、计算机系统与数据相关违法行为和执法程序。",
    },
    {
        "source_name": "Saint Lucia Computer Misuse Act Attorney General Source",
        "record_name": "Saint Lucia Computer Misuse Act",
        "country_code": "LC",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Attorney General's Chambers of Saint Lucia",
        "scope_description": "圣卢西亚 Computer Misuse Act 官方法律页面，覆盖计算机误用、未授权访问和相关处罚。",
    },
    {
        "source_name": "Nicaragua National Assembly Cybercrimes Law",
        "record_name": "Nicaragua Special Cybercrimes Law",
        "country_code": "NI",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Asamblea Nacional de Nicaragua",
        "scope_description": "尼加拉瓜 National Assembly 官方网络犯罪法页面，覆盖网络犯罪、信息系统和数据相关违法行为。",
    },
    {
        "source_name": "Paraguay MITIC National Cybersecurity Strategy 2025-2028",
        "record_name": "Paraguay National Cybersecurity Strategy 2025-2028",
        "country_code": "PY",
        "entry_type": "standard",
        "mandatory": "recommended",
        "issuing_body": "Ministerio de Tecnologías de la Información y Comunicación (MITIC)",
        "scope_description": "巴拉圭 MITIC 国家网络安全战略 2025-2028 官方页面，覆盖国家网络安全治理、风险管理、能力建设和协调机制。",
    },
    {
        "source_name": "Russia Official Publication 187-FZ Critical Information Infrastructure",
        "record_name": "Russia Federal Law No. 187-FZ on Critical Information Infrastructure Security",
        "country_code": "RU",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Official Internet Portal of Legal Information of the Russian Federation",
        "scope_description": "俄罗斯 187-FZ 关键信息基础设施安全官方公布文本，覆盖 CII 对象、运营者义务、安全保障和监管要求。",
    },
    {
        "source_name": "Somalia NCA Cybersecurity Law Source",
        "record_name": "Somalia Cybersecurity Law",
        "country_code": "SO",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "National Communications Authority of Somalia",
        "scope_description": "索马里 NCA 官方 Cybersecurity Law 页面，覆盖国家网络安全法律框架、监管职责和相关义务。",
    },
    {
        "source_name": "Eswatini Computer Crime and Cybercrime Act",
        "record_name": "Eswatini Computer Crime and Cybercrime Act",
        "country_code": "SZ",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Government of Eswatini",
        "scope_description": "斯威士兰 Computer Crime and Cybercrime Act 官方 PDF，覆盖计算机犯罪、网络犯罪和相关执法条款。",
    },
    {
        "source_name": "Venezuela TSJ Special Law Against Computer Crimes",
        "record_name": "Venezuela Special Law Against Computer Crimes",
        "country_code": "VE",
        "entry_type": "regulation",
        "mandatory": "mandatory",
        "issuing_body": "Tribunal Supremo de Justicia de Venezuela",
        "scope_description": "委内瑞拉 Special Law Against Computer Crimes 官方页面，覆盖计算机犯罪、系统/数据相关违法行为和处罚。",
    },
]


def _load_official_sources() -> dict[str, dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, country_code, name, list_url, source_type, parser_config
            FROM official_sources
            WHERE enabled=TRUE
            """
        )
        return {row["name"]: dict(row) for row in cur.fetchall()}


def promote(selected_names: set[str] | None = None) -> dict[str, Any]:
    sources = _load_official_sources()
    items = []
    errors = []
    for spec in PROMOTABLE_OFFICIAL_SOURCES:
        if selected_names and spec["source_name"] not in selected_names and spec["record_name"] not in selected_names:
            continue
        source = sources.get(spec["source_name"])
        if not source:
            errors.append({"name": spec["source_name"], "error": "official source not found"})
            continue
        parser_config = source.get("parser_config") or {}
        official_url = parser_config.get("official_evidence_url") or source.get("list_url")
        item = {
            "name": spec["record_name"],
            "country_code": spec["country_code"],
            "entry_type": spec["entry_type"],
            "mandatory": spec["mandatory"],
            "issuing_body": spec["issuing_body"],
            "official_url": official_url,
            "artifact_url": official_url if source.get("source_type") == "pdf_index" else None,
            "applicable_products": spec.get("applicable_products") or DEFAULT_PRODUCTS,
            "scope_description": spec["scope_description"],
            "evidence_note": (
                "2026-05-10 人工复核官方源注册表，确认该条目为具体官方法规/战略正文或 PDF；"
                f"来源：{spec['source_name']}；官方链接：{official_url}。"
            ),
            "generate_spec": False,
        }
        try:
            record = ensure_record(item)
            items.append(register_link_only_source(record, item))
        except Exception as exc:  # noqa: BLE001 - batch importer must continue per row
            errors.append({"name": spec["record_name"], "country_code": spec["country_code"], "error": str(exc)})
    return {"items": items, "errors": errors, "total": len(items), "error_count": len(errors)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", nargs="*", help="Optional source_name or record_name allow-list")
    args = parser.parse_args()
    result = promote(set(args.names) if args.names else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
