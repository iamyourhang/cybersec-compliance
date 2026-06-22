"""
collector/document/parse_service.py
文档解析服务 - 编排 PDF提取 + AI解析 + 入库
这是唯一有业务逻辑的模块，依赖其他三个模块
"""
from __future__ import annotations
import logging
import re
from datetime import date
from typing import Optional
from collector.document.cos_storage import CosStorage
from collector.document.html_extractor import extract_page_texts_from_html_bytes
from collector.document.pdf_extractor import extract_page_texts_from_bytes
from collector.document.text_cleaner import clean_page_texts, is_unusable_extracted_text
from collector.document.doc_repository import DocRepository
from collector.parsers.prompts import build_document_parse_prompt
from collector.parsers.compliance_parser import normalize_entry, parse_date, parse_single_entry
from collector.providers.channel_router import ChannelRouter, get_channel_router
from database.repository import CanonicalRequirementRepository

logger = logging.getLogger(__name__)

_PRODUCT_HINTS = {
    "enterprise_router": ["enterprise router", "企业级路由器"],
    "home_router": ["home router", "家用路由器"],
    "switch": ["switch", "交换机"],
    "firewall_utm": ["firewall", "utm", "防火墙"],
    "wireless_ap": ["wireless access point", "access point", "wireless ap", "无线ap"],
    "industrial_gateway": ["industrial gateway", "工业网关"],
    "sd_wan": ["sd-wan", "sd wan"],
    "security_gateway": ["security gateway", "安全网关", "network security gateway"],
    "cloud_desktop": ["cloud desktop", "云桌面"],
    "software": ["software", "软件"],
}

_STANDARD_PATTERNS = [
    r"\bETSI\s+EN\s+\d[\d\s.-]*\b",
    r"\bISO(?:/IEC)?\s+\d[\d\s.-]*\b",
    r"\bIEC\s+\d[\d\s.-]*\b",
    r"\bNIST(?:\s+SP)?\s+\d[\d\s.-]*\b",
    r"\bCNS\s+\d[\d\s.-]*\b",
]

_DATE_TOKEN_RE = re.compile(
    r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{2}\.\d{2}\.\d{4})"
)


class DocumentParseService:
    """
    法规原文解析服务。
    职责：从COS下载PDF → 提取文本 → AI解析 → 写入文档候选层
    """

    def __init__(
        self,
        storage: Optional[CosStorage] = None,
        router: Optional[ChannelRouter] = None,
    ):
        self._cos = storage or CosStorage()
        self._router = router or get_channel_router()

    def parse_document(self, doc_id: str, write_to_knowledge: bool = True) -> dict:
        """
        解析单个文档。
        write_to_knowledge=True 时将解析结果登记到候选层，但不直接写正式知识。
        返回解析结果字典。
        """
        doc = DocRepository.get(doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")
        if doc["parse_status"] == "parsing":
            raise RuntimeError(f"文档正在解析中: {doc_id}")

        DocRepository.set_parsing(doc_id)
        logger.info("🔍 开始解析文档: %s [%s]", doc["name"][:60], doc_id)

        try:
            # Step 1: 从 COS 下载文档工件
            content_bytes = self._cos.download_bytes(doc["cos_key"])

            # Step 2: 提取文本
            DocRepository.set_progress(doc_id, 25, "提取可检索文本")
            if (doc.get("file_type") or "").lower() == "html":
                page_texts = extract_page_texts_from_html_bytes(content_bytes)
            else:
                page_texts = extract_page_texts_from_bytes(content_bytes)
            page_texts = clean_page_texts(page_texts)
            text = "\n\n".join(page["text"] for page in page_texts if page["text"])
            pages = len(page_texts)
            if not text or len(text.strip()) < 200 or is_unusable_extracted_text(text):
                raise ValueError("当前版本不支持不可提取文本的源文件，请上传可复制文本 PDF 或稳定正文页")
            logger.info("  📄 文本提取: %d页, %d字符", pages, len(text))

            # Step 3: AI 解析
            DocRepository.set_progress(doc_id, 55, "抽取法规结构化摘要")
            prompt = build_document_parse_prompt(
                document_text=text,
                country_code=doc["country_code"],
                document_name=doc["name"],
                max_chars=20000,
            )
            try:
                response = self._router.chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=2500,
                    enable_web_search=False,  # 原文解析不需要联网，只读原文
                )
                entry = parse_single_entry(
                    ai_output=response.content,
                    source_name="document_parse",
                )
                logger.info("  🤖 AI解析完成: %s", entry.get("name", "?")[:60])
            except Exception as parse_exc:
                logger.warning("AI结构化抽取失败，切换兜底解析 [%s]: %s", doc_id, parse_exc)
                entry = self._build_fallback_entry(doc, text)

            # Step 4: 登记结构化候选
            compliance_id = doc.get("compliance_id")
            if write_to_knowledge:
                DocRepository.set_progress(doc_id, 80, "登记结构化候选")
                CanonicalRequirementRepository.upsert_parse_candidate(doc, entry)

            # Step 5: 更新文档记录
            DocRepository.set_parsed(doc_id, entry, compliance_id)
            return {"success": True, "entry": entry, "compliance_id": compliance_id}

        except Exception as e:
            logger.error("❌ 文档解析失败 [%s]: %s", doc_id, e, exc_info=True)
            DocRepository.set_failed(doc_id, str(e))
            return {"success": False, "error": str(e)}

    def _build_fallback_entry(self, doc: dict, text: str) -> dict:
        sample = text[:12000]
        lowered = sample.lower()
        status = "draft" if "draft" in lowered or "interim draft" in lowered else "active"
        name = self._extract_document_title(sample) or doc["name"]
        raw_entry = {
            "name": name,
            "name_local": None,
            "entry_type": self._guess_entry_type(name, lowered),
            "mandatory": "recommended" if status == "draft" else "mandatory",
            "status": status,
            "country_code": doc["country_code"],
            "issuing_body": self._guess_issuing_body(sample),
            "technical_standards": self._extract_standards(sample),
            "effective_date": self._extract_labeled_date(
                sample,
                ["date of enforcement", "effective date", "enforcement date"],
            ),
            "transition_end_date": self._extract_labeled_date(
                sample,
                ["transition end date", "transition period", "grace period"],
            ),
            "published_date": self._extract_labeled_date(
                sample,
                ["date of release", "publication date", "published on", "date"],
            ),
            "applicable_products": self._guess_products(lowered),
            "scope_description": self._build_scope_description(sample, name),
            "requirements": {
                "key_requirements": [],
                "assessment_route": "请基于原文切片检索确认合规证明路径",
                "penalty": "请基于原文切片检索确认处罚条款",
                "special_notes": "本条为兜底解析结果，详细结论请以原文切片和引用回答为准",
            },
            "testing_bodies": [],
            "assessment_procedure": "请基于原文切片检索查看评估流程",
            "official_url": None,
            "remarks": "AI 结构化抽取失败，已使用本地兜底解析并继续建立 RAG 索引",
            "confidence_score": 55,
        }
        entry = normalize_entry(raw_entry, source_name="document_parse_fallback")
        logger.info("  🧩 兜底解析完成: %s", entry.get("name", "?")[:60])
        return entry

    def _extract_document_title(self, text: str) -> Optional[str]:
        for line in text.splitlines()[:40]:
            cleaned = re.sub(r"\s+", " ", line).strip(" -:\t")
            if len(cleaned) < 12:
                continue
            if any(ch.isalpha() for ch in cleaned):
                return cleaned[:220]
        return None

    def _guess_entry_type(self, name: str, lowered_text: str) -> str:
        lowered_name = name.lower()
        if "certification" in lowered_name or "certification" in lowered_text:
            return "certification"
        if (
            "standard" in lowered_name
            or "draft etsi" in lowered_text
            or re.search(r"\b(etsi en|iso|iec|nist sp|cns)\b", lowered_text)
        ):
            return "standard"
        return "regulation"

    def _guess_issuing_body(self, text: str) -> Optional[str]:
        candidates = [
            ("ETSI", "European Telecommunications Standards Institute (ETSI)"),
            ("NCCS", "National Centre for Communication Security (NCCS)"),
            ("NIST", "National Institute of Standards and Technology (NIST)"),
            ("ENISA", "European Union Agency for Cybersecurity (ENISA)"),
        ]
        upper = text.upper()
        for token, label in candidates:
            if token in upper:
                return label
        return None

    def _extract_standards(self, text: str) -> list[str]:
        seen: list[str] = []
        for pattern in _STANDARD_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = re.sub(r"\s+", " ", match).strip(" .,:;")
                if cleaned and cleaned not in seen:
                    seen.append(cleaned)
                if len(seen) >= 6:
                    return seen
        return seen

    def _extract_labeled_date(self, text: str, labels: list[str]) -> Optional[date]:
        label_pattern = "|".join(re.escape(label) for label in labels)
        regex = re.compile(
            rf"(?i)(?:{label_pattern})\s*[:：-]?\s*{_DATE_TOKEN_RE.pattern}"
        )
        match = regex.search(text[:8000])
        if match:
            return parse_date(match.group(1))
        return None

    def _guess_products(self, lowered_text: str) -> list[str]:
        results = [
            product_code
            for product_code, keywords in _PRODUCT_HINTS.items()
            if any(keyword in lowered_text for keyword in keywords)
        ]
        return results or ["firewall_utm"] if "firewall" in lowered_text else []

    def _build_scope_description(self, text: str, name: str) -> str:
        for line in text.splitlines():
            cleaned = re.sub(r"\s+", " ", line).strip()
            lowered = cleaned.lower()
            if len(cleaned) < 30:
                continue
            if any(token in lowered for token in ("scope", "applicable", "firewall", "network", "device")):
                return cleaned[:120]
        return f"{name} 原文已上传，可通过切片检索进一步查看适用范围。"
