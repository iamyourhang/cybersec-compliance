-- V11__compliance_review_gate.sql
-- 正式知识库入库闸门：所有 compliance_knowledge 新记录默认进入 candidate；
-- verified 必须带 official_url + 原文工件/文档 + 可读证据备注。

CREATE OR REPLACE FUNCTION enforce_compliance_review_gate()
RETURNS trigger AS $$
BEGIN
    IF COALESCE(NEW.verified, FALSE) = TRUE
       OR COALESCE(NEW.authenticity_status, 'candidate') = 'verified' THEN
        IF NEW.official_url IS NULL OR NEW.official_url !~* '^https?://' THEN
            RAISE EXCEPTION 'verified compliance records require official_url';
        END IF;

        IF NEW.source_artifact_sha256 IS NULL
           AND NEW.source_document_id IS NULL
           AND NEW.source_artifact_url IS NULL THEN
            RAISE EXCEPTION 'verified compliance records require source artifact or source document evidence';
        END IF;

        IF NEW.authenticity_evidence IS NULL OR length(trim(NEW.authenticity_evidence)) = 0 THEN
            RAISE EXCEPTION 'verified compliance records require authenticity evidence note';
        END IF;

        NEW.verified := TRUE;
        NEW.authenticity_status := 'verified';
        NEW.authenticity_risk_score := COALESCE(NEW.authenticity_risk_score, 0);
        RETURN NEW;
    END IF;

    IF TG_OP = 'INSERT' THEN
        NEW.verified := FALSE;
        NEW.authenticity_status := COALESCE(NEW.authenticity_status, 'candidate');
        NEW.authenticity_risk_score := COALESCE(NEW.authenticity_risk_score, 60);
        NEW.authenticity_reasons := COALESCE(NEW.authenticity_reasons, '["requires_review_before_verified"]'::jsonb);
        IF NEW.authenticity_evidence IS NULL OR length(trim(NEW.authenticity_evidence)) = 0 THEN
            NEW.authenticity_evidence := '新入库条目默认进入候选池；必须完成官方正文页/PDF工件闭环和真实性审核后才能标记 verified。';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compliance_review_gate ON compliance_knowledge;

CREATE TRIGGER trg_compliance_review_gate
BEFORE INSERT OR UPDATE ON compliance_knowledge
FOR EACH ROW
EXECUTE FUNCTION enforce_compliance_review_gate();
