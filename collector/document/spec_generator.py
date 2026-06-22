"""
collector/document/spec_generator.py
规格生成服务 - 编排 AI提取 + Excel生成 + COS上传
完全独立，不修改任何现有模块
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from collector.document.cos_storage import CosStorage
from collector.document.html_extractor import extract_text_from_html_bytes
from collector.document.pdf_extractor import extract_text_from_bytes
from collector.document.doc_repository import DocRepository
from collector.document.spec_prompt import (
    ALL_PRODUCTS,
    build_spec_extraction_prompt,
    build_spec_merge_prompt,
)
from collector.document.spec_compiler import ClauseExtractor, RequirementCompiler, SpecVerifier
from collector.parsers.compliance_parser import extract_json_from_text
from collector.providers.channel_router import ChannelRouter, get_channel_router
from config.settings import get_settings
from database.repository import (
    RegulationChunkRepository,
    RegulationSectionRepository,
    RegulationSpecRequirementRepository,
)

logger = logging.getLogger(__name__)

SPEC_MODEL_TIMEOUT_SECONDS = 45
SPEC_EXTRACTION_RETRIES = (
    {"max_chars": 3000, "max_tokens": 900},
    {"max_chars": 1800, "max_tokens": 600},
)
SPEC_WINDOW_CHARS = 3000
SPEC_WINDOW_OVERLAP = 300
SPEC_MIN_SPLIT_CHARS = 1800
SPEC_MAX_SPLIT_DEPTH = 2
SPEC_STRUCTURED_WINDOW_CHARS = 2500
SPEC_LARGE_DOC_WINDOW_THRESHOLD = 30
SPEC_GENERIC_FALLBACK_LIMIT = 60


def generate_spec_excel(*args, **kwargs):
    from collector.document.spec_excel_writer import generate_spec_excel as _generate_spec_excel

    return _generate_spec_excel(*args, **kwargs)


class SpecGeneratorService:
    """
    产品规格生成服务。
    职责：读PDF → AI提取规格 → 生成Excel → 上传COS
    """

    def __init__(self):
        self._cos = CosStorage()
        self._router = get_channel_router()

    def generate_from_doc(
        self,
        doc_id: str,
        applicable_products: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        从已上传的文档生成规格要求 Excel。
        applicable_products=None 时对全部产品类型生成。
        返回: {success, spec_count, cos_url, excel_cos_key, specs}
        """
        doc = DocRepository.get(doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")

        DocRepository.set_spec_progress(doc_id, 5, "正在读取原文文件")

        products = applicable_products or ALL_PRODUCTS
        logger.info("🔧 开始生成规格: %s [%d个产品类型]", doc["name"][:60], len(products))

        # Step1: 下载源文件
        file_bytes = self._cos.download_bytes(doc["cos_key"])

        # Step2: 提取文本
        if (doc.get("file_type") or "").lower() == "html":
            text, pages = extract_text_from_html_bytes(file_bytes)
        else:
            text, pages = extract_text_from_bytes(file_bytes)
        if not text or len(text.strip()) < 200:
            raise ValueError(f"源文件文本提取失败（{len(text)}字符，{pages}页）")
        logger.info("  📄 文本: %d页 %d字符", pages, len(text))
        DocRepository.set_spec_progress(doc_id, 12, "原文读取完成，准备结构化规格提取")

        # Step3: AI提取规格
        specs = self._extract_specs(text, doc["name"], doc["country_code"], products, doc_id=doc_id)
        logger.info("  🤖 提取到 %d 条规格要求", len(specs))

        if not specs:
            raise ValueError("AI未能提取到任何规格要求")

        # Step4: 落结构化规格库
        stored_count = RegulationSpecRequirementRepository.upsert_many(
            self._build_spec_rows(doc, specs)
        )
        DocRepository.set_spec_progress(doc_id, 82, "规格已提取，正在写入结构化规格库")

        # Step5: 生成Excel
        excel_bytes = generate_spec_excel(
            specs=specs,
            regulation_name=doc["name"],
            country_code=doc["country_code"],
        )

        # Step6: 上传到COS
        s = get_settings()
        today = date.today().strftime("%Y%m%d")
        safe_name = doc["name"][:30].replace(" ", "_").replace("/", "-")
        cos_key = f"{s.cos.report_prefix}specs/{doc['country_code']}/{today}_{safe_name}_specs.xlsx"
        cos_url = self._cos.upload_bytes(excel_bytes, cos_key)

        logger.info("  ✅ Excel已上传: %s (%dKB)", cos_key, len(excel_bytes)//1024)
        DocRepository.set_spec_progress(doc_id, 96, "结构化规格已完成，正在上传导出文件")

        DocRepository.set_spec_generated(doc_id, cos_url, cos_key, stored_count)

        return {
            "success": True,
            "doc_id": doc_id,
            "doc_name": doc["name"],
            "spec_count": len(specs),
            "stored_count": stored_count,
            "cos_url": cos_url,
            "cos_key": cos_key,
            "file_size": len(excel_bytes),
            "specs": specs,
            "summary": self._build_summary(specs),
        }

    def generate_from_text(
        self,
        text: str,
        regulation_name: str,
        country_code: str,
        applicable_products: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        直接从文本生成规格（无需先上传文档）。
        供调试和测试使用。
        """
        products = applicable_products or ALL_PRODUCTS
        specs = self._extract_specs(text, regulation_name, country_code, products, doc_id=None)
        excel_bytes = generate_spec_excel(specs, regulation_name, country_code)

        s = get_settings()
        today = date.today().strftime("%Y%m%d")
        safe_name = regulation_name[:30].replace(" ", "_").replace("/", "-")
        cos_key = f"{s.cos.report_prefix}specs/{country_code}/{today}_{safe_name}_specs.xlsx"
        cos_url = self._cos.upload_bytes(excel_bytes, cos_key)

        return {
            "success": True,
            "spec_count": len(specs),
            "stored_count": 0,
            "cos_url": cos_url,
            "cos_key": cos_key,
            "file_size": len(excel_bytes),
            "specs": specs,
            "summary": self._build_summary(specs),
        }

    def _extract_specs(
        self,
        text: str,
        regulation_name: str,
        country_code: str,
        products: List[str],
        doc_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """调用AI提取规格，采用全文分窗遍历 + 全局归并，避免漏读中间内容。"""
        windows = self._build_extraction_windows(doc_id, text)
        logger.info("  🧩 规格提取窗口数: %d", len(windows))
        fallback_specs = self._build_rule_level_fallback_specs(doc_id, country_code, products)
        if fallback_specs and len(windows) > SPEC_LARGE_DOC_WINDOW_THRESHOLD:
            logger.warning("长文档优先使用原文切片生成 %d 条规则级规格草案，避免同步规格提取长时间阻塞", len(fallback_specs))
            return fallback_specs
        if len(windows) > SPEC_LARGE_DOC_WINDOW_THRESHOLD:
            generic_specs = self._build_generic_chunk_fallback_specs(doc_id, country_code, products)
            if generic_specs:
                logger.warning(
                    "长文档未命中特定模板，改用全文 chunk 扫描生成 %d 条可追溯规格草案",
                    len(generic_specs),
                )
                return generic_specs
            raise ValueError("长文档未识别到可追溯规格证据，已停止同步模型逐窗抽取以避免超时")
        if doc_id:
            DocRepository.set_spec_progress(doc_id, 18, f"开始全文规格提取，共 {len(windows)} 个窗口")

        window_specs: List[Dict[str, Any]] = []
        last_error: Optional[Exception] = None

        for idx, window_text in enumerate(windows, start=1):
            if doc_id:
                progress = 18 + int((idx - 1) / max(1, len(windows)) * 42)
                DocRepository.set_spec_progress(doc_id, progress, f"正在提取窗口 {idx}/{len(windows)}")
            window_result = self._extract_specs_from_window(
                window_text=window_text,
                regulation_name=regulation_name,
                country_code=country_code,
                products=products,
                window_index=idx,
                total_windows=len(windows),
            )
            if window_result:
                window_specs.extend(window_result)

        if not window_specs:
            fallback_specs = self._build_rule_level_fallback_specs(doc_id, country_code, products)
            if fallback_specs:
                logger.warning("AI未提取到规格，使用原文切片生成 %d 条规则级规格草案", len(fallback_specs))
                return fallback_specs
            if isinstance(last_error, FuturesTimeoutError):
                raise ValueError("规格提取超时，请稍后重试或缩小法规原文范围")
            raise ValueError(f"AI输出解析失败: {last_error or '全文窗口未提取到任何规格'}")

        if doc_id:
            DocRepository.set_spec_progress(doc_id, 68, f"全文窗口提取完成，共得到 {len(window_specs)} 条候选规格，正在全局归并")
        merged_specs = self._merge_specs(
            regulation_name=regulation_name,
            country_code=country_code,
            products=products,
            candidate_specs=window_specs,
        )
        if merged_specs:
            return merged_specs
        return self._local_dedupe_specs(window_specs)

    def _build_extraction_windows(self, doc_id: Optional[str], text: str) -> List[str]:
        if doc_id:
            section_windows = self._build_windows_from_sections(doc_id)
            if section_windows:
                return section_windows
            chunk_windows = self._build_windows_from_chunks(doc_id)
            if chunk_windows:
                return chunk_windows
        return self._split_text_windows(text)

    def _build_windows_from_sections(self, doc_id: str) -> List[str]:
        sections = RegulationSectionRepository.list_by_document(doc_id, limit=5000)
        units = []
        for section in sections:
            content = (section.get("content") or "").strip()
            if not content:
                continue
            title = (section.get("title") or "").strip()
            ref = (section.get("section_ref") or "").strip()
            path = (section.get("section_path") or "").strip()
            header = " | ".join(part for part in [ref, title, path] if part)
            units.append(f"{header}\n{content}" if header else content)
        return self._merge_units_to_windows(units)

    def _build_windows_from_chunks(self, doc_id: str) -> List[str]:
        chunks = RegulationChunkRepository.list_by_document(doc_id, limit=5000)
        units = []
        for chunk in chunks:
            content = (chunk.get("content") or "").strip()
            if not content:
                continue
            clause = (chunk.get("clause_ref") or "").strip()
            path = (chunk.get("section_path") or "").strip()
            pages = f"页码 {chunk.get('page_from')}-{chunk.get('page_to')}" if chunk.get("page_from") else ""
            header = " | ".join(part for part in [clause, path, pages] if part)
            units.append(f"{header}\n{content}" if header else content)
        return self._merge_units_to_windows(units)

    def _merge_units_to_windows(self, units: List[str]) -> List[str]:
        if not units:
            return []
        windows: List[str] = []
        buffer = ""
        for unit in units:
            if len(unit) > SPEC_STRUCTURED_WINDOW_CHARS:
                if buffer:
                    windows.append(buffer)
                    buffer = ""
                windows.extend(self._split_oversized_structured_unit(unit))
                continue
            candidate = unit if not buffer else f"{buffer}\n\n{unit}"
            if len(candidate) > SPEC_STRUCTURED_WINDOW_CHARS and buffer:
                windows.append(buffer)
                buffer = unit
            else:
                buffer = candidate
        if buffer:
            windows.append(buffer)
        return windows

    def _split_oversized_structured_unit(self, unit: str) -> List[str]:
        header, separator, body = unit.partition("\n")
        if not separator:
            return self._split_structured_text_windows(unit)
        body_windows = self._split_structured_text_windows(body)
        return [f"{header}\n{window}" for window in body_windows if window.strip()]

    def _split_structured_text_windows(self, text: str) -> List[str]:
        windows: List[str] = []
        start = 0
        step = max(1, SPEC_STRUCTURED_WINDOW_CHARS - SPEC_WINDOW_OVERLAP)
        while start < len(text):
            end = min(len(text), start + SPEC_STRUCTURED_WINDOW_CHARS)
            windows.append(text[start:end])
            if end >= len(text):
                break
            start += step
        return windows

    def _extract_specs_from_window(
        self,
        window_text: str,
        regulation_name: str,
        country_code: str,
        products: List[str],
        window_index: int,
        total_windows: int,
        split_depth: int = 0,
    ) -> List[Dict[str, Any]]:
        last_error: Optional[Exception] = None

        for attempt, config in enumerate(SPEC_EXTRACTION_RETRIES, start=1):
            prompt = build_spec_extraction_prompt(
                document_text=window_text[: config["max_chars"]],
                regulation_name=regulation_name,
                country_code=country_code,
                applicable_products=products,
                window_label=f"{window_index}/{total_windows}",
                full_document_hint="当前任务为全文分窗遍历，所有窗口处理完成后还会统一归并",
            )
            try:
                response = self._call_spec_model(prompt, config["max_tokens"])
                return self._parse_specs_response(response.content)
            except FuturesTimeoutError as exc:
                last_error = exc
                logger.warning(
                    "规格窗口 %d/%d 提取超时，第%d次尝试失败（timeout=%ss, max_chars=%d, max_tokens=%d, split_depth=%d）",
                    window_index,
                    total_windows,
                    attempt,
                    SPEC_MODEL_TIMEOUT_SECONDS,
                    config["max_chars"],
                    config["max_tokens"],
                    split_depth,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "规格窗口 %d/%d 第%d次尝试失败: %s（max_chars=%d, max_tokens=%d）",
                    window_index,
                    total_windows,
                    attempt,
                    exc,
                    config["max_chars"],
                    config["max_tokens"],
                )

        if isinstance(last_error, FuturesTimeoutError):
            if len(window_text) > SPEC_MIN_SPLIT_CHARS and split_depth < SPEC_MAX_SPLIT_DEPTH:
                logger.warning(
                    "规格窗口 %d/%d 持续超时，自动拆分为更小窗口继续提取（len=%d, split_depth=%d）",
                    window_index,
                    total_windows,
                    len(window_text),
                    split_depth,
                )
                smaller_windows = self._split_text_windows(
                    window_text,
                    window_chars=max(SPEC_MIN_SPLIT_CHARS, len(window_text) // 2),
                    overlap=min(SPEC_WINDOW_OVERLAP, max(800, len(window_text) // 10)),
                )
                nested_specs: List[Dict[str, Any]] = []
                for sub_idx, sub_window in enumerate(smaller_windows, start=1):
                    nested_specs.extend(
                        self._extract_specs_from_window(
                            window_text=sub_window,
                            regulation_name=regulation_name,
                            country_code=country_code,
                            products=products,
                            window_index=sub_idx,
                            total_windows=len(smaller_windows),
                            split_depth=split_depth + 1,
                        )
                    )
                return nested_specs
            raise last_error
        if last_error:
            logger.warning(
                "规格窗口 %d/%d 多次解析失败，跳过该窗口以继续全文提取: %s",
                window_index,
                total_windows,
                last_error,
            )
            return []
        raise last_error or ValueError("窗口规格提取失败")

    def _merge_specs(
        self,
        regulation_name: str,
        country_code: str,
        products: List[str],
        candidate_specs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        deduped = self._local_dedupe_specs(candidate_specs)
        if len(deduped) <= 1:
            return deduped

        prompt = build_spec_merge_prompt(
            regulation_name=regulation_name,
            country_code=country_code,
            applicable_products=products,
            candidate_specs=deduped,
        )
        try:
            response = self._call_spec_model(prompt, 4000)
            merged = self._parse_specs_response(response.content)
            if merged:
                return self._local_dedupe_specs(merged)
        except Exception as exc:
            logger.warning("规格全局归并失败，回退本地去重: %s", exc)
        return deduped

    def _split_text_windows(self, text: str, window_chars: int = SPEC_WINDOW_CHARS, overlap: int = SPEC_WINDOW_OVERLAP) -> List[str]:
        if len(text) <= window_chars:
            return [text]

        windows: List[str] = []
        step = max(1, window_chars - overlap)
        cursor = 0
        length = len(text)
        while cursor < length:
            end = min(length, cursor + window_chars)
            windows.append(text[cursor:end])
            if end >= length:
                break
            cursor += step
        return windows

    def _local_dedupe_specs(self, specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for spec in specs:
            key = (
                (spec.get("req_id") or "").strip().lower()
                or (spec.get("regulation_clause") or "").strip().lower()
                or (spec.get("title_zh") or "").strip().lower()
                or (spec.get("description_zh") or "").strip().lower()[:80]
            )
            if not key:
                key = str(uuid.uuid4())
            if key not in merged:
                merged[key] = dict(spec)
                continue

            existing = merged[key]
            for field, value in spec.items():
                if value in (None, "", [], {}):
                    continue
                if existing.get(field) in (None, "", [], {}):
                    existing[field] = value
                elif isinstance(value, list) and isinstance(existing.get(field), list):
                    existing[field] = list(dict.fromkeys([*existing[field], *value]))

        return list(merged.values())

    def _build_rule_level_fallback_specs(
        self,
        doc_id: Optional[str],
        country_code: str,
        products: List[str],
    ) -> List[Dict[str, Any]]:
        if not doc_id:
            return []
        chunks = RegulationChunkRepository.list_by_document(doc_id, limit=5000)
        evidence = ClauseExtractor(chunks).extract()
        specs = RequirementCompiler(products).compile(evidence)
        return SpecVerifier().filter_valid(specs)

    def _build_generic_chunk_fallback_specs(
        self,
        doc_id: Optional[str],
        country_code: str,
        products: List[str],
        limit: int = SPEC_GENERIC_FALLBACK_LIMIT,
    ) -> List[Dict[str, Any]]:
        """For long laws, scan every indexed chunk and keep only traceable obligation-like excerpts."""
        if not doc_id:
            return []
        specs: List[Dict[str, Any]] = []
        seen: set[str] = set()
        chunks = RegulationChunkRepository.list_by_document(doc_id, limit=5000)
        for chunk in chunks:
            excerpt = self._extract_obligation_excerpt(chunk.get("content") or "")
            if not excerpt:
                continue
            dedupe_key = re.sub(r"\W+", " ", excerpt.lower())[:180]
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            module_zh, module_en = self._infer_module(excerpt)
            clause_ref = (chunk.get("clause_ref") or chunk.get("section_path") or "").strip()
            source_pages = self._format_chunk_pages(chunk)
            source_chunk_ids = self._format_chunk_ids(chunk)
            specs.append(
                {
                    "req_id": f"GEN-{country_code.upper()}-{len(specs) + 1:03d}",
                    "module_zh": module_zh,
                    "module_en": module_en,
                    "title_zh": f"{clause_ref or '原文条款'} - {module_zh}要求",
                    "title_en": f"{clause_ref or 'Source clause'} - {module_en} requirement",
                    "description_zh": f"原文要求（保守摘录）：{excerpt}",
                    "description_en": excerpt,
                    "applicable_products": products,
                    "mandatory": "mandatory" if self._looks_mandatory(excerpt) else "recommended",
                    "priority": self._infer_priority(excerpt),
                    "regulation_clause": clause_ref,
                    "verification_method_zh": self._verification_method_zh(module_zh),
                    "verification_method_en": self._verification_method_en(module_en),
                    "notes_zh": "长文档规则级草案，由本地原文 chunk 全量扫描生成；不得脱离来源页码和 chunk 证据使用。",
                    "notes_en": "Long-document draft generated by scanning all local source chunks; use only with the cited pages and chunk evidence.",
                    "source_pages": source_pages,
                    "source_chunk_ids": source_chunk_ids,
                }
            )
            if len(specs) >= limit:
                break
        return SpecVerifier().filter_valid(specs)

    def _extract_obligation_excerpt(self, content: str) -> str:
        text = re.sub(r"\s+", " ", (content or "")).strip()
        if len(text) < 60:
            return ""
        lowered = text.lower()
        cyber_markers = (
            "cyber", "security", "information technology", "network", "vulnerab", "incident",
            "certification", "conformity", "cryptograph", "authentication", "access",
            "keamanan", "siber", "sandi", "kriptografi", "sertifikasi", "kesesuaian",
            "seguridad", "ciberseguridad", "segurança", "sécurité", "信息安全", "网络安全", "认证",
        )
        obligation_markers = (
            "shall", "must", "required", "requirement", "ensure", "provide", "maintain",
            "establish", "implement", "comply", "obligation", "notify", "report",
            "wajib", "harus", "persyaratan", "memenuhi", "debe", "deberá", "devem",
            "doit", "doivent", "应当", "必须", "要求", "应",
        )
        if not any(marker in lowered for marker in cyber_markers):
            return ""
        sentences = re.split(r"(?<=[.!?。；;])\s+|\n+", text)
        selected = [
            sentence.strip()
            for sentence in sentences
            if len(sentence.strip()) >= 40
            and any(marker in sentence.lower() for marker in obligation_markers)
        ]
        if not selected and any(marker in lowered for marker in obligation_markers):
            selected = [text[:900]]
        return " ".join(selected[:3])[:1000].strip()

    def _infer_module(self, excerpt: str) -> tuple[str, str]:
        lowered = excerpt.lower()
        if any(term in lowered for term in ["update", "patch", "vulnerab", "sbom"]):
            return "安全更新与漏洞管理", "Security Updates and Vulnerability Management"
        if any(term in lowered for term in ["password", "authentication", "identity", "access", "login"]):
            return "身份认证与访问控制", "Authentication and Access Control"
        if any(term in lowered for term in ["encrypt", "cryptograph", "kriptografi", "sandi", "key"]):
            return "加密与密钥安全", "Cryptography and Key Security"
        if any(term in lowered for term in ["incident", "notify", "report", "csirt"]):
            return "事件报告与响应", "Incident Reporting and Response"
        if any(term in lowered for term in ["certification", "conformity", "assessment", "sertifikasi", "kesesuaian"]):
            return "合规认证与评估", "Compliance Certification and Assessment"
        if any(term in lowered for term in ["log", "audit", "record"]):
            return "日志与审计", "Logging and Audit"
        return "安全治理与产品要求", "Security Governance and Product Requirements"

    def _looks_mandatory(self, excerpt: str) -> bool:
        lowered = excerpt.lower()
        return any(term in lowered for term in ["shall", "must", "required", "wajib", "harus", "应当", "必须", "deberá", "doit"])

    def _infer_priority(self, excerpt: str) -> str:
        lowered = excerpt.lower()
        if any(term in lowered for term in ["vulnerab", "incident", "password", "authentication", "encrypt", "cryptograph", "update", "shall", "must", "wajib", "harus"]):
            return "P1"
        return "P2"

    def _verification_method_zh(self, module_zh: str) -> str:
        if "更新" in module_zh or "漏洞" in module_zh:
            return "核验漏洞处理流程、安全更新机制、修复记录和发布证据，并抽样验证更新完整性。"
        if "认证" in module_zh or "评估" in module_zh:
            return "核验证书/评估报告、适用范围、测试机构资质和官方注册或公告记录。"
        if "加密" in module_zh:
            return "检查密码算法、密钥生命周期、配置基线和相关安全测试报告。"
        if "认证与访问" in module_zh:
            return "检查身份认证、权限控制、默认凭据和访问控制测试记录。"
        if "事件" in module_zh:
            return "检查事件报告流程、时限要求、通知模板和演练/真实处置记录。"
        return "核验制度文件、产品设计证据、测试报告和与原文条款对应的符合性说明。"

    def _verification_method_en(self, module_en: str) -> str:
        if "Updates" in module_en or "Vulnerability" in module_en:
            return "Verify vulnerability handling, security update mechanisms, remediation records, and update integrity evidence."
        if "Certification" in module_en or "Assessment" in module_en:
            return "Verify certificates, assessment reports, scope, lab competence, and official registry or notice records."
        if "Cryptography" in module_en:
            return "Review cryptographic algorithms, key lifecycle controls, configuration baselines, and security test reports."
        if "Authentication" in module_en:
            return "Review authentication, authorisation, default credential handling, and access-control test evidence."
        if "Incident" in module_en:
            return "Review incident reporting procedures, deadlines, notification templates, and exercise or response records."
        return "Verify governance documents, product design evidence, test reports, and clause-level conformity statements."

    def _format_chunk_pages(self, chunk: Dict[str, Any]) -> Optional[str]:
        page_from = chunk.get("page_from")
        page_to = chunk.get("page_to")
        if not page_from:
            return None
        return str(page_from) if not page_to or page_to == page_from else f"{page_from}-{page_to}"

    def _format_chunk_ids(self, chunk: Dict[str, Any]) -> List[str]:
        raw_id = chunk.get("id")
        if not raw_id:
            return []
        try:
            return [str(uuid.UUID(str(raw_id)))]
        except (TypeError, ValueError):
            return []

    def _call_spec_model(self, prompt: str, max_tokens: int):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._router.chat,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens,
            enable_web_search=False,
            timeout=SPEC_MODEL_TIMEOUT_SECONDS,
            max_retries=1,
        )
        try:
            return future.result(timeout=SPEC_MODEL_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            future.cancel()
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _parse_specs_response(self, content: str) -> List[Dict[str, Any]]:
        try:
            json_str = extract_json_from_text(content)
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                specs = [parsed]
            elif isinstance(parsed, list):
                specs = parsed
            else:
                raise ValueError("返回格式不是数组")
            valid = [
                s for s in specs
                if s.get("req_id") and s.get("description_zh") and s.get("module_zh")
            ]
            if len(valid) < len(specs):
                logger.warning("过滤掉 %d 条不完整规格", len(specs) - len(valid))
            return valid
        except Exception as e:
            salvaged = self._salvage_complete_spec_objects(content)
            if salvaged:
                logger.warning("规格解析失败但成功保守恢复 %d 条完整对象: %s", len(salvaged), e)
                return salvaged
            logger.error("规格解析失败: %s\n原始输出(前500字): %s", e, content[:500])
            raise

    def _salvage_complete_spec_objects(self, content: str) -> List[Dict[str, Any]]:
        objects: List[Dict[str, Any]] = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(content):
            start = content.find("{", idx)
            if start < 0:
                break
            try:
                parsed, end = decoder.raw_decode(content[start:])
            except json.JSONDecodeError:
                idx = start + 1
                continue
            if isinstance(parsed, dict):
                objects.append(parsed)
            idx = start + end
        return [
            item for item in objects
            if item.get("req_id") and item.get("description_zh") and item.get("module_zh")
        ]

    def _build_spec_rows(self, doc: Dict[str, Any], specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for spec in specs:
            if not spec.get("regulation_clause") and not spec.get("source_pages") and not spec.get("source_chunk_ids"):
                continue
            rows.append(
                {
                    "document_id": doc["id"],
                    "compliance_id": doc.get("compliance_id"),
                    "country_code": doc["country_code"],
                    "regulation_name": doc["name"],
                    "req_id": spec["req_id"],
                    "module_zh": spec.get("module_zh"),
                    "module_en": spec.get("module_en"),
                    "title_zh": spec.get("title_zh"),
                    "title_en": spec.get("title_en"),
                    "description_zh": spec.get("description_zh"),
                    "description_en": spec.get("description_en"),
                    "applicable_products": spec.get("applicable_products") or [],
                    "mandatory": spec.get("mandatory"),
                    "priority": spec.get("priority"),
                    "regulation_clause": spec.get("regulation_clause"),
                    "verification_method_zh": spec.get("verification_method_zh"),
                    "verification_method_en": spec.get("verification_method_en"),
                    "notes_zh": spec.get("notes_zh"),
                    "notes_en": spec.get("notes_en"),
                    "source_pages": spec.get("source_pages"),
                    "source_chunk_ids": spec.get("source_chunk_ids") or [],
                }
            )
        return rows

    def _build_summary(self, specs: List[Dict]) -> Dict:
        """生成统计摘要"""
        from collections import Counter
        return {
            "total": len(specs),
            "by_priority": dict(Counter(s.get("priority","?") for s in specs)),
            "by_module": dict(Counter(s.get("module_zh","?") for s in specs)),
            "by_mandatory": dict(Counter(s.get("mandatory","?") for s in specs)),
            "p1_count": len([s for s in specs if s.get("priority") == "P1"]),
        }
