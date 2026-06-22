from __future__ import annotations

from collector.discovery.service import (
    AIDiscoveryService,
    CandidateValidationService,
    CandidateWriter,
    DiscoveryCandidate,
    DiscoveryPlanner,
    DiscoveryQuery,
    ResponsesWebSearchDiscoverySearcher,
    DiscoveryTarget,
    EvidenceValidator,
    is_vulnerability_advisory_not_compliance,
)


def test_evidence_validator_rejects_non_official_domain():
    target = DiscoveryTarget(
        country_code="EU",
        country_name="欧盟",
        priority="P0",
        official_domains=["eur-lex.europa.eu", "digital-strategy.ec.europa.eu"],
    )
    query = DiscoveryQuery(target=target, query="EU cybersecurity product certification official")
    candidate = DiscoveryCandidate(
        title="Cyber Resilience Act summary",
        detail_url="https://example.com/cra-summary",
        entry_type="regulation",
        ai_reason="Looks relevant",
    )

    result = EvidenceValidator().validate(target, query, candidate)

    assert result.accepted is False
    assert "非官方域名" in result.reason


def test_discovery_planner_adds_recency_window_and_multilingual_rotation():
    target = DiscoveryTarget(
        country_code="FR",
        country_name="法国",
        country_name_en="France",
        priority="P1",
        official_domains=["cyber.gouv.fr"],
    )

    class _Targets:
        def list_targets(self, priorities=None, limit_countries=40):
            return [target]

    plan = DiscoveryPlanner(target_repository=_Targets()).build_plan(
        priorities=["P1"],
        limit_countries=1,
        queries_per_country=4,
    )

    assert len(plan) == 4
    query_text = "\n".join(query.query for query in plan)
    assert "updated after" in query_text
    assert "published after" in query_text
    assert "France" in query_text
    assert "cybersécurité" in query_text or "certificación" in query_text or "الأمن السيبراني" in query_text


def test_evidence_validator_rejects_official_but_non_cyber_product_topic():
    target = DiscoveryTarget(
        country_code="ZA",
        country_name="南非",
        priority="P1",
        official_domains=["icasa.org.za"],
    )
    query = DiscoveryQuery(target=target, query="South Africa cybersecurity product certification official")
    candidate = DiscoveryCandidate(
        title="Radio frequency spectrum licence quarterly statistics",
        detail_url="https://www.icasa.org.za/pages/radio-frequency-spectrum",
        entry_type="standard",
        ai_reason="Official regulator page",
    )

    result = EvidenceValidator().validate(target, query, candidate)

    assert result.accepted is False
    assert "非网络安全产品合规主题" in result.reason


def test_evidence_validator_rejects_generic_product_certification_summary_even_when_query_mentions_cyber():
    target = DiscoveryTarget(
        country_code="CN",
        country_name="中国",
        priority="P1",
        official_domains=["cnca.gov.cn"],
    )
    query = DiscoveryQuery(target=target, query="China cybersecurity product certification official")
    candidate = DiscoveryCandidate(
        title="强制性产品认证实施规则汇总（更新日期：2026年4月）",
        detail_url="https://www.cnca.gov.cn/hlwfw/ywzl/qzxcprz/ssgz/art/2026/example.html",
        entry_type="certification",
        summary="国家认监委强制性产品认证实施规则汇总页面。",
        ai_reason="官方产品认证规则汇总。",
        cyber_product_relevance_reason="与产品认证合规框架有关。",
    )

    result = EvidenceValidator().validate(target, query, candidate)

    assert result.accepted is False
    assert "通用产品认证汇总" in result.reason


def test_evidence_validator_rejects_official_news_story_not_formal_source():
    target = DiscoveryTarget(
        country_code="VN",
        country_name="越南",
        priority="P1",
        official_domains=["mic.gov.vn", "english.mic.gov.vn"],
    )
    query = DiscoveryQuery(target=target, query="Vietnam cybersecurity trust mark certification official")
    candidate = DiscoveryCandidate(
        title="6,000 systems for e-transactions receive a 'trust mark' label",
        detail_url="https://english.mic.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205080947425.htm",
        entry_type="certification",
        published_date="2024-12-05",
        summary="Official news about systems receiving a trust mark label.",
        ai_reason="The page is on the official MIC website and mentions trust mark labels.",
        cyber_product_relevance_reason="Mentions a trust mark label for e-transaction systems.",
    )

    result = EvidenceValidator().validate(target, query, candidate)

    assert result.accepted is False
    assert "官方新闻/案例页面" in result.reason


def test_evidence_validator_rejects_cve_advisory_even_when_product_related():
    target = DiscoveryTarget(
        country_code="BO",
        country_name="玻利维亚",
        priority="P2",
        official_domains=["csirt.gob.bo"],
    )
    query = DiscoveryQuery(target=target, query="Bolivia cybersecurity product regulation official")
    candidate = DiscoveryCandidate(
        title="Vulnerabilidad crítica CVE-2026-24858 Bypass crítico de autenticación en productos Fortinet",
        detail_url="https://csirt.gob.bo/es/alertas-de-seguridad/vulnerabilidad-critica-cve-2026-24858-bypass-critico-de-autenticacion",
        entry_type="regulation",
        published_date="2026-05-21",
        summary="Official CSIRT security advisory about an authentication bypass in Fortinet products.",
        cyber_product_relevance_reason="与网络安全产品本身的安全缺陷和补丁/缓解措施直接相关。",
    )

    result = EvidenceValidator().validate(target, query, candidate)

    assert result.accepted is False
    assert "漏洞/CVE/安全通告" in result.reason


def test_vulnerability_advisory_filter_keeps_formal_cra_and_psti_sources():
    assert (
        is_vulnerability_advisory_not_compliance(
            "Regulation (EU) 2024/2847 Cyber Resilience Act horizontal cybersecurity requirements "
            "for products with digital elements includes vulnerability reporting obligations "
            "https://eur-lex.europa.eu/eli/reg/2024/2847/oj"
        )
        is False
    )
    assert (
        is_vulnerability_advisory_not_compliance(
            "Product Security and Telecommunications Infrastructure Act 2022 secure connected products PSTI "
            "https://www.legislation.gov.uk/ukpga/2022/31/contents"
        )
        is False
    )


def test_candidate_writer_writes_ai_candidate_and_pending_artifact_only():
    target = DiscoveryTarget(
        country_code="SG",
        country_name="新加坡",
        priority="P0",
        official_domains=["csa.gov.sg"],
    )
    query = DiscoveryQuery(target=target, query="Singapore Cybersecurity Labelling Scheme IoT official")
    candidate = DiscoveryCandidate(
        title="Cybersecurity Labelling Scheme for IoT",
        detail_url="https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme",
        artifact_url="https://www.csa.gov.sg/docs/default-source/csa/documents/cls/cls-publication.pdf",
        entry_type="certification",
        published_date="2024-01-01",
        ai_reason="Official CSA scheme for connected products",
        official_evidence_reason="The URL is on csa.gov.sg",
        cyber_product_relevance_reason="The scheme applies to IoT products",
        ai_confidence=0.91,
    )
    validation = EvidenceValidator().validate(target, query, candidate)

    class _SourceRecords:
        calls = []

        @classmethod
        def upsert_candidate(cls, **kwargs):
            cls.calls.append(kwargs)
            return "src-1"

    class _Artifacts:
        calls = []

        @classmethod
        def upsert_for_compliance(cls, **kwargs):
            cls.calls.append(kwargs)
            return "artifact-1"

    writer = CandidateWriter(source_record_repository=_SourceRecords, source_artifact_repository=_Artifacts)
    source_record_id = writer.write(target, query, candidate, validation)

    assert source_record_id == "src-1"
    record_call = _SourceRecords.calls[0]
    assert record_call["country_code"] == "SG"
    assert record_call["title"] == "Cybersecurity Labelling Scheme for IoT"
    assert record_call["discovery_method"] == "ai_weekly_discovery"
    assert record_call["source_status"] == "validation_pending"
    assert record_call["source_payload"]["query"] == query.query
    assert record_call["source_payload"]["ai_reason"] == "Official CSA scheme for connected products"
    assert record_call["source_payload"]["official_evidence_reason"]
    assert record_call["source_payload"]["cyber_product_relevance_reason"]
    assert record_call["source_payload"]["ai_confidence"] == 0.91
    assert record_call["source_payload"]["discovered_at"]
    assert record_call["source_payload"]["validation_stage"]["status"] == "pending"

    assert _Artifacts.calls == []


def test_candidate_validation_manual_accept_enqueues_artifact():
    record = {
        "id": "src-1",
        "country_code": "SG",
        "title": "Cybersecurity Labelling Scheme for IoT",
        "entry_type": "certification",
        "source_url": "https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme",
        "artifact_url": "https://www.csa.gov.sg/docs/cls.pdf",
        "source_payload": {"query": "Singapore cybersecurity label"},
    }

    class _Records:
        updates = []

        @staticmethod
        def get_by_id(source_record_id):
            return record if source_record_id == "src-1" else None

        @classmethod
        def update_validation(cls, source_record_id, *, source_status, validation_stage):
            cls.updates.append(
                {
                    "source_record_id": source_record_id,
                    "source_status": source_status,
                    "validation_stage": validation_stage,
                }
            )
            return True

    class _Artifacts:
        calls = []

        @staticmethod
        def get_by_source_record_id(source_record_id):
            return None

        @classmethod
        def upsert_for_compliance(cls, **kwargs):
            cls.calls.append(kwargs)
            return "artifact-1"

    service = CandidateValidationService(
        source_record_repository=_Records,
        source_artifact_repository=_Artifacts,
    )

    result = service.validate(
        "src-1",
        mode="manual",
        decision="accepted",
        reasons=["official_domain_confirmed"],
        evidence_note="人工确认该页面属于 CSA 官方产品网络安全认证页面。",
        checked_by="tester",
    )

    assert result["source_status"] == "candidate"
    assert result["validation_stage"]["mode"] == "manual"
    assert result["validation_stage"]["status"] == "accepted"
    assert _Records.updates[0]["source_status"] == "candidate"
    assert _Artifacts.calls[0]["source_record_id"] == "src-1"
    assert _Artifacts.calls[0]["download_status"] == "pending"


def test_candidate_validation_manual_reject_does_not_enqueue_artifact():
    record = {
        "id": "src-1",
        "country_code": "ZA",
        "title": "Radio frequency statistics",
        "entry_type": "standard",
        "source_url": "https://www.icasa.org.za/pages/radio-frequency-spectrum",
        "artifact_url": None,
        "source_payload": {"query": "South Africa cybersecurity official"},
    }

    class _Records:
        updates = []

        @staticmethod
        def get_by_id(source_record_id):
            return record if source_record_id == "src-1" else None

        @classmethod
        def update_validation(cls, source_record_id, *, source_status, validation_stage):
            cls.updates.append({"source_status": source_status, "validation_stage": validation_stage})
            return True

    class _Artifacts:
        calls = []

        @staticmethod
        def get_by_source_record_id(source_record_id):
            return None

        @classmethod
        def upsert_for_compliance(cls, **kwargs):
            cls.calls.append(kwargs)
            return "artifact-1"

    service = CandidateValidationService(
        source_record_repository=_Records,
        source_artifact_repository=_Artifacts,
    )

    result = service.validate(
        "src-1",
        mode="manual",
        decision="rejected",
        reasons=["not_cyber_product_compliance"],
        evidence_note="人工确认这是频谱统计页面，不属于产品网络安全合规。",
        checked_by="tester",
    )

    assert result["source_status"] == "rejected"
    assert result["validation_stage"]["status"] == "rejected"
    assert _Records.updates[0]["source_status"] == "rejected"
    assert _Artifacts.calls == []


def test_candidate_validation_ai_rejects_generic_product_certification_without_calling_model():
    record = {
        "id": "src-cnca",
        "country_code": "CN",
        "title": "强制性产品认证实施规则汇总（更新日期：2026年4月）",
        "entry_type": "certification",
        "source_url": "https://www.cnca.gov.cn/hlwfw/ywzl/qzxcprz/ssgz/art/2026/example.html",
        "artifact_url": "https://www.cnca.gov.cn/hlwfw/ywzl/qzxcprz/ssgz/art/2026/example.html",
        "source_payload": {
            "query": "China cybersecurity product certification official",
            "cyber_product_relevance_reason": "与产品认证合规框架有关。",
            "raw_candidate": {
                "title_zh": "强制性产品认证实施规则汇总",
                "summary_zh": "国家认监委强制性产品认证实施规则汇总页面。",
            },
        },
    }

    class _Router:
        def chat(self, **kwargs):
            raise AssertionError("generic certification should be rejected before model call")

    class _Records:
        updates = []

        @staticmethod
        def get_by_id(source_record_id):
            return record if source_record_id == "src-cnca" else None

        @classmethod
        def update_validation(cls, source_record_id, *, source_status, validation_stage):
            cls.updates.append(
                {
                    "source_record_id": source_record_id,
                    "source_status": source_status,
                    "validation_stage": validation_stage,
                }
            )
            return True

    class _Artifacts:
        calls = []

        @staticmethod
        def get_by_source_record_id(source_record_id):
            return None

        @classmethod
        def upsert_for_compliance(cls, **kwargs):
            cls.calls.append(kwargs)
            return "artifact-1"

    result = CandidateValidationService(
        router=_Router(),
        source_record_repository=_Records,
        source_artifact_repository=_Artifacts,
    ).validate("src-cnca", mode="ai", checked_by="ai_discovery")

    assert result["source_status"] == "rejected"
    assert _Records.updates[0]["validation_stage"]["reasons"] == [
        "generic_product_certification_not_cybersecurity"
    ]
    assert _Artifacts.calls == []


def test_candidate_validation_ai_rejects_cve_advisory_without_calling_model():
    record = {
        "id": "src-cve",
        "country_code": "BO",
        "title": "Vulnerabilidad (CVE-2026-32014) - Omisión de Autenticación por falsificación",
        "entry_type": "regulation",
        "source_url": "https://csirt.gob.bo/es/alertas-de-seguridad/vulnerabilidad-cve-2026-32014-omision-de-autenticacion-por-falsificacion",
        "artifact_url": None,
        "source_payload": {
            "query": "Bolivia cybersecurity product regulation official",
            "cyber_product_relevance_reason": "It concerns a software vulnerability and update for a product implementation.",
            "raw_candidate": {
                "summary": "Official security advisory recommending immediate update after an authentication-bypass issue.",
            },
        },
    }

    class _Router:
        def chat(self, **kwargs):
            raise AssertionError("CVE advisory should be rejected before model call")

    class _Records:
        updates = []

        @staticmethod
        def get_by_id(source_record_id):
            return record if source_record_id == "src-cve" else None

        @classmethod
        def update_validation(cls, source_record_id, *, source_status, validation_stage):
            cls.updates.append(
                {
                    "source_record_id": source_record_id,
                    "source_status": source_status,
                    "validation_stage": validation_stage,
                }
            )
            return True

    class _Artifacts:
        calls = []

        @staticmethod
        def get_by_source_record_id(source_record_id):
            return None

        @classmethod
        def upsert_for_compliance(cls, **kwargs):
            cls.calls.append(kwargs)
            return "artifact-1"

    result = CandidateValidationService(
        router=_Router(),
        source_record_repository=_Records,
        source_artifact_repository=_Artifacts,
    ).validate("src-cve", mode="ai", checked_by="ai_discovery")

    assert result["source_status"] == "rejected"
    assert _Records.updates[0]["validation_stage"]["reasons"] == [
        "vulnerability_advisory_not_compliance"
    ]
    assert _Artifacts.calls == []


def test_responses_web_search_searcher_parses_candidates_and_tool_actions():
    target = DiscoveryTarget(
        country_code="EU",
        country_name="欧盟",
        priority="P1",
        official_domains=["eur-lex.europa.eu"],
    )
    query = DiscoveryQuery(target=target, query="EU CRA official EUR-Lex")

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "resp-1",
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "type": "search",
                            "query": "EU CRA official EUR-Lex",
                        },
                    },
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": """
                                [
                                  {
                                    "title": "Regulation (EU) 2024/2847",
                                    "detail_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847",
                                    "entry_type": "regulation",
                                    "published_date": "2024-11-20",
                                    "summary": "EU Cyber Resilience Act official text",
                                    "official_evidence_reason": "EUR-Lex official page",
                                    "cyber_product_relevance_reason": "Cybersecurity requirements for products with digital elements",
                                    "ai_confidence": 0.93
                                  }
                                ]
                                """,
                            }
                        ],
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

    class _Client:
        calls = []

        def post(self, url, *, headers, json, timeout):
            self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return _Response()

    client = _Client()
    searcher = ResponsesWebSearchDiscoverySearcher(
        api_key="key",
        base_url="https://uniapi.ruijie.com.cn/v1",
        model="gpt-5.4-mini",
        http_client=client,
    )

    candidates = searcher.search(query)

    assert client.calls[0]["url"] == "https://uniapi.ruijie.com.cn/v1/responses"
    assert client.calls[0]["json"]["model"] == "gpt-5.4-mini"
    assert client.calls[0]["json"]["tools"] == [{"type": "web_search"}]
    assert candidates[0].title == "Regulation (EU) 2024/2847"
    assert candidates[0].detail_url.endswith("32024R2847")
    assert candidates[0].raw_payload["web_search_backend"] == "responses_web_search"
    assert candidates[0].raw_payload["web_search_actions"][0]["type"] == "search"


def test_ai_discovery_prompt_includes_current_date_and_recency_requirements():
    from collector.discovery import service as discovery_service

    target = DiscoveryTarget(
        country_code="EU",
        country_name="欧盟",
        priority="P1",
        official_domains=["eur-lex.europa.eu"],
    )
    query = DiscoveryQuery(target=target, query="EU cybersecurity regulation official updated after 2026-05-01")

    prompt = discovery_service._build_ai_discovery_prompt(query)

    assert "当前日期" in prompt
    assert "最近7天" in prompt
    assert "发布时间或更新时间" in prompt
    assert "不要返回旧闻" in prompt
    assert "published_date 不得为 null" in prompt


def test_ai_discovery_service_records_failed_run_without_writing_verified():
    target = DiscoveryTarget(
        country_code="US",
        country_name="美国",
        priority="P0",
        official_domains=["nist.gov"],
    )

    class _Targets:
        def list_targets(self, priorities=None, limit_countries=40):
            return [target]

    class _Searcher:
        def search(self, query):
            raise RuntimeError("AI channel unavailable")

    class _Writer:
        calls = []

        def write(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    class _Runs:
        finishes = []

        def start_run(self, scope, countries_count, queries_count):
            return "run-1"

        def finish_run(self, run_id, **kwargs):
            self.finishes.append((run_id, kwargs))

    service = AIDiscoveryService(
        planner=DiscoveryPlanner(target_repository=_Targets(), queries_per_country=1),
        searcher=_Searcher(),
        validator=EvidenceValidator(),
        writer=_Writer(),
        run_repository=_Runs(),
    )

    result = service.run(priorities=["P0"], limit_countries=1, queries_per_country=1)

    assert result["status"] == "failed"
    assert result["candidate_count"] == 0
    assert result["accepted_count"] == 0
    assert result["rejected_count"] == 0
    assert "AI channel unavailable" in result["error"]
    assert _Writer.calls == []


def test_ai_discovery_service_can_ai_validate_written_candidates():
    target = DiscoveryTarget(
        country_code="SG",
        country_name="新加坡",
        priority="P1",
        official_domains=["csa.gov.sg"],
    )
    candidate = DiscoveryCandidate(
        title="Cybersecurity Labelling Scheme",
        detail_url="https://www.csa.gov.sg/our-programmes/cybersecurity-labelling-scheme",
        entry_type="certification",
        summary="cybersecurity product certification",
    )

    class _Targets:
        def list_targets(self, priorities=None, limit_countries=40):
            return [target]

    class _Searcher:
        def search(self, query):
            return [candidate]

    class _Writer:
        calls = []

        def write(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return "src-1"

    class _Validator:
        calls = []

        def validate(self, source_record_id, **kwargs):
            self.calls.append({"source_record_id": source_record_id, **kwargs})
            return {"source_status": "candidate"}

    class _Runs:
        def start_run(self, scope, countries_count, queries_count):
            self.scope = scope
            return "run-1"

        def finish_run(self, run_id, **kwargs):
            self.finish = kwargs

    runs = _Runs()
    ai_validator = _Validator()
    service = AIDiscoveryService(
        planner=DiscoveryPlanner(target_repository=_Targets(), queries_per_country=1),
        searcher=_Searcher(),
        validator=EvidenceValidator(),
        writer=_Writer(),
        run_repository=runs,
        candidate_validation_service=ai_validator,
    )

    result = service.run(priorities=["P1"], limit_countries=1, queries_per_country=1, validation_mode="ai")

    assert result["accepted_count"] == 1
    assert runs.scope["validation_mode"] == "ai"
    assert ai_validator.calls == [
        {
            "source_record_id": "src-1",
            "mode": "ai",
            "checked_by": "ai_discovery",
        }
    ]


def test_ai_discovery_service_writes_official_news_as_reference_not_candidate():
    target = DiscoveryTarget(
        country_code="VN",
        country_name="越南",
        priority="P1",
        official_domains=["mic.gov.vn", "english.mic.gov.vn"],
    )
    candidate = DiscoveryCandidate(
        title="6,000 systems for e-transactions receive a 'trust mark' label",
        detail_url="https://english.mic.gov.vn/6000-systems-for-e-transactions-receive-a-trust-mark-label-197241205080947425.htm",
        entry_type="certification",
        published_date="2024-12-05",
        summary="Official news about systems receiving a trust mark label.",
        cyber_product_relevance_reason="Mentions a trust mark label for e-transaction systems.",
    )

    class _Targets:
        def list_targets(self, priorities=None, limit_countries=40):
            return [target]

    class _Searcher:
        def search(self, query):
            return [candidate]

    class _Writer:
        candidate_calls = []
        reference_calls = []

        def write(self, *args, **kwargs):
            self.candidate_calls.append((args, kwargs))
            return "src-candidate"

        def write_reference(self, *args, **kwargs):
            self.reference_calls.append((args, kwargs))
            return "src-reference"

    class _Validator:
        calls = []

        def validate(self, source_record_id, **kwargs):
            self.calls.append({"source_record_id": source_record_id, **kwargs})
            return {"source_status": "candidate"}

    class _Runs:
        def start_run(self, scope, countries_count, queries_count):
            return "run-1"

        def finish_run(self, run_id, **kwargs):
            self.finish = kwargs

    writer = _Writer()
    runs = _Runs()
    ai_validator = _Validator()
    service = AIDiscoveryService(
        planner=DiscoveryPlanner(target_repository=_Targets(), queries_per_country=1),
        searcher=_Searcher(),
        validator=EvidenceValidator(),
        writer=writer,
        run_repository=runs,
        candidate_validation_service=ai_validator,
    )

    result = service.run(priorities=["P1"], limit_countries=1, queries_per_country=1, validation_mode="ai")

    assert result["accepted_count"] == 0
    assert result["reference_count"] == 1
    assert result["rejected_count"] == 0
    assert writer.candidate_calls == []
    assert len(writer.reference_calls) == 1
    assert ai_validator.calls == []
