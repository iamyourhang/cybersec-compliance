"""
scripts/ai_verify.py
旧 AI 二次核实脚本。

默认拒绝执行，避免再用 AI 搜索结果直接影响正式库。
只有显式传入 --legacy-unsafe 时才允许运行。
"""
import sys, argparse, time, json, logging
sys.path.insert(0, '.')

from database.connection import get_cursor, get_connection
from collector.providers.factory import get_provider_manager
from collector.parsers.compliance_parser import extract_json_from_text
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def ensure_legacy_opt_in(enabled: bool) -> None:
    if enabled:
        return
    print(
        "❌ scripts/ai_verify.py 已默认禁用：它会让 AI 联网结果直接影响正式库。\n"
        "如确需临时排障，请显式传入 --legacy-unsafe，并且不要把输出直接当作 verified 依据。",
        file=sys.stderr,
    )
    raise SystemExit(2)

VERIFY_PROMPT = """请联网搜索，核实以下网络安全认证/法规是否真实存在。

名称: {name}
国家: {country_code}
发布机构: {issuing_body}

搜索要求:
1. 搜索 "{name} {country_code} official"
2. 搜索 "{issuing_body} {name}"

输出JSON:
{{
  "is_real": true或false,
  "confidence": 0-100,
  "evidence": "找到的证据摘要，如找不到任何官方来源则说明",
  "official_url": "官方链接或null",
  "correct_name": "如名称有误则给出正确名称，否则null",
  "action": "keep/deprecate/update"
}}

判断标准:
- keep: 找到官方来源，确认真实存在
- deprecate: 找不到任何官方来源，疑似AI编造
- update: 真实存在但名称/信息有误需更新

只输出JSON。"""


def verify_record(pm, record: dict) -> dict:
    prompt = VERIFY_PROMPT.format(
        name=record['name'],
        country_code=record['country_code'],
        issuing_body=record.get('issuing_body') or '未知',
    )
    try:
        resp = pm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
            enable_web_search=True,
            require_web_search=True,
        )
        json_str = extract_json_from_text(resp.content)
        return json.loads(json_str)
    except Exception as e:
        logger.error("核实失败 [%s]: %s", record['name'][:40], e)
        return {"action": "keep", "confidence": 50, "evidence": f"核实出错: {e}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--country', help='只核实指定国家')
    parser.add_argument('--limit', type=int, default=30, help='每次核实条数')
    parser.add_argument('--type', default='certification', help='条目类型: certification/regulation/standard/all')
    parser.add_argument('--dry-run', action='store_true', help='只输出结果不修改数据库')
    parser.add_argument('--legacy-unsafe', action='store_true', help='显式确认运行旧 AI 核实脚本（不推荐）')
    args = parser.parse_args()
    ensure_legacy_opt_in(args.legacy_unsafe)

    # 查询待核实记录（优先核实置信度低的认证类）
    sql = """
        SELECT id, name, entry_type, country_code, issuing_body, 
               confidence_score, official_url
        FROM compliance_knowledge
        WHERE status='active' AND verified=FALSE
    """
    params = []
    if args.country:
        sql += " AND country_code=%s"; params.append(args.country)
    if args.type != 'all':
        sql += " AND entry_type=%s"; params.append(args.type)
    sql += " ORDER BY confidence_score ASC NULLS FIRST LIMIT %s"
    params.append(args.limit)

    with get_cursor() as cur:
        cur.execute(sql, params)
        records = [dict(r) for r in cur.fetchall()]

    print(f"待核实: {len(records)} 条（类型={args.type}, dry-run={args.dry_run}）\n")
    pm = get_provider_manager()

    kept = deprecated = updated = 0
    for i, record in enumerate(records, 1):
        print(f"[{i}/{len(records)}] {record['country_code']} | {record['name'][:60]}")
        result = verify_record(pm, record)
        action = result.get('action', 'keep')
        conf = result.get('confidence', 50)
        evidence = result.get('evidence', '')[:80]
        print(f"  → {action} | 置信度:{conf} | {evidence}")

        if not args.dry_run:
            rid = str(record['id'])
            with get_connection() as conn:
                with conn.cursor() as cur:
                    if action == 'deprecate':
                        cur.execute("""UPDATE compliance_knowledge 
                                      SET status='deprecated',
                                          ai_verified=TRUE,
                                          ai_verify_count=ai_verify_count+1,
                                          ai_verified_at=NOW(),
                                          updated_at=NOW() WHERE id=%s AND verified=FALSE""", (rid,))
                        deprecated += 1
                    elif action == 'update':
                        updates = {"confidence_score": conf}
                        if result.get('correct_name'):
                            updates['name'] = result['correct_name']
                        if result.get('official_url'):
                            updates['official_url'] = result['official_url']
                        evidence_note = result.get('evidence', '')
                        if evidence_note:
                            updates['remarks'] = f"[AI核实:{evidence_note[:200]}]"
                        set_clause = ", ".join(f"{k}=%s" for k in updates)
                        cur.execute(f"""UPDATE compliance_knowledge 
                                       SET {set_clause},
                                           ai_verified=TRUE,
                                           ai_verify_count=ai_verify_count+1,
                                           ai_verified_at=NOW(),
                                           updated_at=NOW() WHERE id=%s AND verified=FALSE""",
                                   list(updates.values()) + [rid])
                        updated += 1
                    else:
                        # keep: 更新置信度、官方链接、核实证据、ai_verified
                        evidence_note = result.get('evidence', '')
                        if evidence_note:
                            evidence_note = f"[AI核实:{evidence_note[:200]}]"
                        cur.execute("""UPDATE compliance_knowledge 
                                      SET confidence_score=%s,
                                          official_url=COALESCE(%s, official_url),
                                          ai_verified=TRUE,
                                          ai_verify_count=ai_verify_count+1,
                                          ai_verified_at=NOW(),
                                          remarks=CASE 
                                            WHEN %s != '' THEN COALESCE(remarks||' ', '')||%s
                                            ELSE remarks 
                                          END,
                                          updated_at=NOW() WHERE id=%s AND verified=FALSE""",
                                   (conf, result.get('official_url'),
                                    evidence_note, evidence_note, rid))
                        kept += 1

        time.sleep(2)  # 避免限流

    print(f"\n✅ 核实完成: 保留={kept} 更新={updated} 废止={deprecated}")

if __name__ == '__main__':
    main()
