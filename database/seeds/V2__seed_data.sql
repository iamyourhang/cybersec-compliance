-- ============================================================
-- 种子数据：国家/地区 + 产品类型
-- 执行: psql -U compliance_user -d cybersec_compliance -f V2__seed_data.sql
-- ============================================================

-- ============================================================
-- 国家/地区种子数据
-- ============================================================
INSERT INTO countries (code, name_zh, name_en, region, priority) VALUES
-- P1：核心市场，每日检查
('EU',  '欧盟',     'European Union',       '欧洲',   'P1'),
('US',  '美国',     'United States',        '美洲',   'P1'),
('GB',  '英国',     'United Kingdom',       '欧洲',   'P1'),
('CN',  '中国',     'China',                '亚太',   'P1'),
('JP',  '日本',     'Japan',                '亚太',   'P1'),
('KR',  '韩国',     'South Korea',          '亚太',   'P1'),

-- P2：重要市场，每周检查
('SG',  '新加坡',   'Singapore',            '东南亚', 'P2'),
('AU',  '澳大利亚', 'Australia',            '大洋洲', 'P2'),
('CA',  '加拿大',   'Canada',               '美洲',   'P2'),
('IN',  '印度',     'India',                '南亚',   'P2'),
('AE',  '阿联酋',   'United Arab Emirates', '中东',   'P2'),
('SA',  '沙特阿拉伯','Saudi Arabia',         '中东',   'P2'),
('MY',  '马来西亚', 'Malaysia',             '东南亚', 'P2'),
('TH',  '泰国',     'Thailand',             '东南亚', 'P2'),
('ID',  '印度尼西亚','Indonesia',            '东南亚', 'P2'),
('VN',  '越南',     'Vietnam',              '东南亚', 'P2'),
('BR',  '巴西',     'Brazil',               '美洲',   'P2'),
('MX',  '墨西哥',   'Mexico',               '美洲',   'P2'),
('TR',  '土耳其',   'Turkey',               '中东欧', 'P2'),
('IL',  '以色列',   'Israel',               '中东',   'P2'),

-- P3：其他市场，每月检查
('DE',  '德国',     'Germany',              '欧洲',   'P3'),
('FR',  '法国',     'France',               '欧洲',   'P3'),
('NL',  '荷兰',     'Netherlands',          '欧洲',   'P3'),
('PL',  '波兰',     'Poland',               '欧洲',   'P3'),
('RU',  '俄罗斯',   'Russia',               '欧洲',   'P3'),
('ZA',  '南非',     'South Africa',         '非洲',   'P3'),
('NG',  '尼日利亚', 'Nigeria',              '非洲',   'P3'),
('EG',  '埃及',     'Egypt',                '非洲',   'P3'),
('PH',  '菲律宾',   'Philippines',          '东南亚', 'P3'),
('PK',  '巴基斯坦', 'Pakistan',             '南亚',   'P3'),
('BD',  '孟加拉国', 'Bangladesh',           '南亚',   'P3'),
('NZ',  '新西兰',   'New Zealand',          '大洋洲', 'P3'),
('AR',  '阿根廷',   'Argentina',            '美洲',   'P3'),
('CL',  '智利',     'Chile',                '美洲',   'P3'),
('CO',  '哥伦比亚', 'Colombia',             '美洲',   'P3'),
('KW',  '科威特',   'Kuwait',               '中东',   'P3'),
('QA',  '卡塔尔',   'Qatar',                '中东',   'P3'),
('TW',  '中国台湾', 'Taiwan, China',        '亚太',   'P3'),
('HK',  '香港',     'Hong Kong',            '亚太',   'P3')
ON CONFLICT (code) DO UPDATE SET
    name_zh  = EXCLUDED.name_zh,
    name_en  = EXCLUDED.name_en,
    region   = EXCLUDED.region,
    priority = EXCLUDED.priority;

-- ============================================================
-- 产品种子数据
-- ============================================================
INSERT INTO products (code, name_zh, name_en, category) VALUES
('enterprise_router',  '企业级路由器',  'Enterprise Router',         'enterprise_router'),
('home_router',        '家用路由器',    'Home/Consumer Router',      'home_router'),
('switch',             '网络交换机',    'Network Switch',            'switch'),
('firewall_utm',       '防火墙/UTM',    'Firewall / UTM',            'firewall_utm'),
('wireless_ap',        '无线AP',        'Wireless Access Point',     'wireless_ap'),
('industrial_gateway', '工业网关',      'Industrial Gateway',        'industrial_gateway'),
('sd_wan',             'SD-WAN',        'SD-WAN',                    'sd_wan'),
('security_gateway',   '网络安全网关',  'Network Security Gateway',  'security_gateway'),
('cloud_desktop',      '云桌面',        'Cloud Desktop',             'cloud_desktop'),
('software',           '软件',          'Software',                  'software')
ON CONFLICT (code) DO UPDATE SET
    name_zh  = EXCLUDED.name_zh,
    name_en  = EXCLUDED.name_en,
    category = EXCLUDED.category;

-- ============================================================
-- 合规知识库初始种子数据（重点条目，P1国家）
-- ============================================================
INSERT INTO compliance_knowledge (
    name, name_local, entry_type, mandatory, status,
    country_code, issuing_body, technical_standards, regulation_basis,
    effective_date, transition_end_date, validity_period, published_date,
    applicable_products, scope_description, requirements,
    official_url, remarks, data_source, verified, confidence_score
) VALUES

-- 欧盟 CRA（网络韧性法案）
(
    'EU Cyber Resilience Act (CRA)',
    'Verordnung über horizontale Cybersicherheitsanforderungen',
    'regulation', 'mandatory', 'active',
    'EU',
    'European Commission / ENISA',
    ARRAY['ETSI EN 303 645', 'IEC 62443', 'EN ISO/IEC 27001'],
    NULL,
    '2027-09-01',  -- 硬件产品强制生效日期（软件2026-09-11）
    '2026-09-11',
    'N/A（法规无有效期）',
    '2024-10-23',
    ARRAY['enterprise_router','home_router','switch','firewall_utm','wireless_ap','industrial_gateway','sd_wan','security_gateway'],
    '适用于欧盟市场销售的含数字元素产品（products with digital elements），涵盖硬件和软件',
    '{"key_requirements": ["安全设计（Security by Design）", "漏洞管理义务", "SBOM（软件物料清单）", "强制安全更新支持", "合规声明（DoC）", "CE标志"], "assessment_routes": ["自我评估（默认类别）", "第三方认证（重要/关键类别）"], "important_class": "路由器、防火墙通常属于Class II，需第三方认证"}'::jsonb,
    'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847',
    'CRA是欧盟对网络设备影响最重大的法规，2024-10-23正式发布，软件2026-09-11强制，硬件2027-09-01强制',
    'seed', FALSE, 98
),

-- 欧盟 RED（无线电设备指令）网络安全委托法规
(
    'EU RED Delegated Regulation (Cybersecurity) - 2022/30/EU',
    'Delegierte Verordnung (EU) 2022/30',
    'regulation', 'mandatory', 'active',
    'EU',
    'European Commission',
    ARRAY['ETSI EN 303 645', 'ETSI TS 103 701'],
    ARRAY['Radio Equipment Directive (RED) 2014/53/EU'],
    '2025-08-01',
    NULL,
    'N/A',
    '2022-01-12',
    ARRAY['home_router','wireless_ap','enterprise_router'],
    '适用于联网无线设备，包括路由器、智能家居设备、儿童玩具等',
    '{"articles": ["Article 3(3)(d): 不损害网络", "Article 3(3)(e): 保护个人数据", "Article 3(3)(f): 防欺诈"]}'::jsonb,
    'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R0030',
    '2025-08-01强制生效，与CRA存在过渡期协调安排',
    'seed', FALSE, 97
),

-- EUCC 认证
(
    'EUCC (EU Common Criteria-based Cybersecurity Certification Scheme)',
    'EUCC',
    'certification', 'voluntary', 'active',
    'EU',
    'ENISA / National Cybersecurity Certification Authorities',
    ARRAY['Common Criteria (ISO/IEC 15408)', 'CEM (ISO/IEC 18045)'],
    ARRAY['EU Cybersecurity Act (CSA) Regulation 2019/881', 'EU CRA'],
    '2024-02-27',
    NULL,
    '证书有效期通常3-5年，依评估等级',
    '2024-01-31',
    ARRAY['firewall_utm','security_gateway','enterprise_router','switch'],
    '适用于ICT产品，特别是安全敏感产品，如防火墙、VPN、操作系统',
    '{"assurance_levels": ["AVA_VAN.1 (Basic)", "AVA_VAN.3 (Substantial)", "AVA_VAN.5 (High)"], "process": ["申请认证机构", "提交安全目标(ST)", "实验室评估", "机构认可", "颁发证书"]}'::jsonb,
    'https://www.enisa.europa.eu/topics/eucc',
    'EUCC是欧盟首个正式发布的网络安全认证方案，部分CRA高风险产品可能强制要求',
    'seed', FALSE, 96
),

-- 美国 FCC Cyber Trust Mark
(
    'FCC Cyber Trust Mark (U.S. Cyber Trust Mark)',
    'FCC Cyber Trust Mark',
    'certification', 'voluntary', 'active',
    'US',
    'FCC (Federal Communications Commission)',
    ARRAY['NIST IR 8425', 'NISTIR 8259A'],
    ARRAY['Executive Order 14028 (Improving the Nation''s Cybersecurity)'],
    '2024-03-01',
    NULL,
    '证书有效期待定，预计年度更新',
    '2023-07-18',
    ARRAY['home_router','wireless_ap'],
    '主要针对消费类IoT设备，包括家用路由器、智能音箱、摄像头等',
    '{"requirements": ["唯一标识符", "默认安全配置", "数据保护", "安全更新支持", "漏洞报告机制", "加密通信"], "label": "U.S. Cyber Trust Mark + QR码"}'::jsonb,
    'https://www.fcc.gov/cybersecurity-certification-mark',
    '2024年正式启动，目前自愿，未来可能部分强制。通过授权标签机构申请。',
    'seed', FALSE, 95
),

-- 英国 PSTI Act
(
    'UK Product Security and Telecommunications Infrastructure Act (PSTI Act)',
    'PSTI Act 2022',
    'regulation', 'mandatory', 'active',
    'GB',
    'OPSS (Office for Product Safety and Standards)',
    ARRAY['ETSI EN 303 645', 'BS EN 303 645'],
    NULL,
    '2024-04-29',
    NULL,
    'N/A',
    '2022-12-06',
    ARRAY['home_router','wireless_ap','enterprise_router'],
    '适用于在英国销售的联网消费类产品及部分商用产品',
    '{"mandatory_requirements": ["禁止通用默认密码", "提供漏洞报告联系方式", "明确最低安全更新支持期限"], "compliance": "合规声明（Statement of Compliance）"}'::jsonb,
    'https://www.legislation.gov.uk/ukpga/2022/46',
    '2024-04-29已强制生效，违规最高罚款1000万英镑或全球营业额4%',
    'seed', FALSE, 98
),

-- 中国 网络关键设备安全认证
(
    '网络关键设备安全认证',
    '网络关键设备安全认证（MLPS关键设备）',
    'certification', 'mandatory', 'active',
    'CN',
    '中国网络安全审查技术与认证中心（CCRC）',
    ARRAY['GB/T 20281', 'GB/T 28455', 'GB/T 15843'],
    ARRAY['网络安全法第23条', '网络关键设备和网络安全专用产品目录'],
    '2017-06-01',
    NULL,
    '证书有效期3年',
    '2017-06-01',
    ARRAY['enterprise_router','switch','firewall_utm','security_gateway'],
    '列入《网络关键设备和网络安全专用产品目录》的设备，须经安全认证或安全检测方可销售',
    '{"key_equipment": ["路由器（核心/汇聚）", "交换机（核心/汇聚）", "服务器", "PLC"], "security_products": ["防火墙", "WAF", "IPS", "VPN"], "process": ["申请CCRC认证", "提交技术文件", "实验室测试", "工厂审查", "颁发证书"]}'::jsonb,
    'https://www.ccrc.org.cn/',
    '国内销售强制要求，非出口要求。出口到中国的设备须获此认证方可入市。',
    'seed', FALSE, 97
),

-- 中国 等保测评（三级及以上系统使用设备）
(
    '网络安全等级保护测评（等保2.0）',
    '信息安全技术 网络安全等级保护基本要求',
    'certification', 'mandatory', 'active',
    'CN',
    '公安部第三研究所 / 各省等保测评机构',
    ARRAY['GB/T 22239-2019', 'GB/T 28448-2019', 'GB/T 25070-2019'],
    ARRAY['网络安全法第21条', '网络安全等级保护条例'],
    '2019-12-01',
    NULL,
    '证书有效期3年，期间年度自查',
    '2019-05-13',
    ARRAY['enterprise_router','switch','firewall_utm','security_gateway','wireless_ap'],
    '面向在中国境内开展业务的信息系统，按保护等级（1-5级）要求配备合规网络设备',
    '{"levels": {"level2": "自查为主", "level3": "强制测评，每年1次", "level4": "强制测评，半年1次"}, "scope": "面向系统集成商和最终用户，网络设备需满足等保技术要求"}'::jsonb,
    'https://www.djbh.net/',
    '面向系统集成场景，网络设备厂商须确保产品满足等保技术要求，便于客户通过测评',
    'seed', FALSE, 96
),

-- 日本 NOTICE（IoT设备安全调查）
(
    'Japan NOTICE Program (National Operation Towards IoT Clean Environment)',
    'NOTICE（ICT-ISAC連携調査）',
    'regulation', 'mandatory', 'active',
    'JP',
    'NICT / 総務省',
    ARRAY['NICT技術基準'],
    ARRAY['電気通信事業法', '不正アクセス行為の禁止等に関する法律'],
    '2019-02-20',
    NULL,
    'N/A（持续进行）',
    '2019-02-20',
    ARRAY['home_router','wireless_ap','enterprise_router'],
    '日本政府对联网设备进行主动安全调查，针对使用弱密码或默认密码的设备',
    '{"requirements": ["禁止默认弱密码", "强制密码更改", "固件安全更新"], "enforcement": "运营商通知用户，ISP可封锁不合规设备"}'::jsonb,
    'https://notice.go.jp/',
    '日本已明确要求IoT设备禁止默认密码，违规设备被ISP通报',
    'seed', FALSE, 90
),

-- 韩国 ISMS-P
(
    'Korea ISMS-P (Information Security Management System - Personal Information)',
    '정보보호 및 개인정보보호 관리체계 (ISMS-P)',
    'certification', 'mandatory', 'active',
    'KR',
    'KISA (한국인터넷진흥원)',
    ARRAY['K-ISMS', 'PIPA (개인정보보호법)'],
    ARRAY['정보통신망법', '개인정보보호법'],
    '2019-11-07',
    NULL,
    '证书有效期3年，年度维护审查',
    '2019-11-07',
    ARRAY['enterprise_router','switch','firewall_utm','security_gateway'],
    '适用于在韩国提供网络服务的企业及相关ICT产品，一定规模以上强制认证',
    '{"mandatory_entities": ["年收入100亿韩元以上ISP", "日活100万以上平台"], "voluntary": "中小企业可自愿申请"}'::jsonb,
    'https://isms.kisa.or.kr/',
    '韩国市场准入重要认证，与产品直接关联的合规要求',
    'seed', FALSE, 90
)

ON CONFLICT DO NOTHING;

-- 输出统计
DO $$ 
DECLARE
    cnt_countries INTEGER;
    cnt_products  INTEGER;
    cnt_knowledge INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt_countries FROM countries;
    SELECT COUNT(*) INTO cnt_products  FROM products;
    SELECT COUNT(*) INTO cnt_knowledge FROM compliance_knowledge;
    RAISE NOTICE '✅ 种子数据导入完成：';
    RAISE NOTICE '   国家/地区: % 条', cnt_countries;
    RAISE NOTICE '   产品类型: % 条', cnt_products;
    RAISE NOTICE '   合规知识库: % 条', cnt_knowledge;
END $$;
