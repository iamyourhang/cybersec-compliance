<template>
  <div class="screen-wrap">
    <!-- 顶部 -->
    <header class="screen-header">
      <div class="header-left">
        <div class="logo-dot"></div>
        <span class="header-title">全球网络安全合规地图</span>
        <span class="header-sub">全球网络安全合规情报</span>
      </div>
      <div class="header-stats">
        <div class="stat-item" v-for="s in headerStats" :key="s.label">
          <div class="stat-num">{{ s.value }}</div>
          <div class="stat-lbl">{{ s.label }}</div>
        </div>
      </div>
      <div class="header-right">
        <div class="live-dot"></div>
        <span class="header-time">{{ currentTime }}</span>
      </div>
    </header>

    <div class="screen-body">
      <!-- 左侧 -->
      <aside class="side-panel left-panel">
        <div class="panel-title">📊 地区分布</div>
        <div class="region-list">
          <div v-for="r in regionStats" :key="r.region" class="region-item">
            <div class="region-name">{{ r.region }}</div>
            <div class="region-bar-wrap">
              <div class="region-bar" :style="{width: r.pct+'%'}"></div>
            </div>
            <div class="region-cnt">{{ r.cnt }}</div>
          </div>
        </div>
        <div class="panel-title" style="margin-top:20px">🔥 覆盖最多</div>
        <div class="top-list">
          <div v-for="(c,i) in topCountries" :key="c.country_code" class="top-item"
            @click="selectCountryByCode(c.country_code)" style="cursor:pointer">
            <span class="top-rank">{{ i+1 }}</span>
            <span class="top-name">{{ countryNameMap[c.country_code] || c.country_code }}</span>
            <span class="top-cnt">{{ c.cnt }}</span>
          </div>
        </div>
      </aside>

      <!-- 地图 -->
      <div class="globe-wrap">
        <!-- 搜索框 -->
        <div class="search-bar">
          <input
            id="screen-country-search"
            name="screen-country-search"
            v-model="searchQuery"
            class="search-input"
            placeholder="🔍 搜索国家/地区/组织..."
            @input="onSearch"
            @keydown.escape="searchQuery='';searchResults=[]"
          />
          <div v-if="searchResults.length" class="search-dropdown">
            <div v-for="r in searchResults" :key="r.code"
              class="search-item" @click="selectCountryByCode(r.code); searchQuery=''; searchResults=[]">
              <span class="search-code">{{ r.code }}</span>
              <span class="search-name">{{ r.name_zh }}</span>
              <span class="search-cnt">{{ countryCoverageLabel(r) }}</span>
            </div>
          </div>
        </div>

        <svg ref="mapSvg" class="map-svg" @wheel.prevent="onWheel">
          <defs>
            <!-- 地球背景渐变 -->
            <radialGradient id="globeGrad" cx="50%" cy="45%" r="55%">
              <stop offset="0%" stop-color="#0a2a6e" stop-opacity="1"/>
              <stop offset="60%" stop-color="#020e2a" stop-opacity="1"/>
              <stop offset="100%" stop-color="#010812" stop-opacity="1"/>
            </radialGradient>
            <!-- 大气光晕 -->
            <radialGradient id="glowGrad" cx="50%" cy="50%" r="50%">
              <stop offset="70%" stop-color="#003388" stop-opacity="0"/>
              <stop offset="90%" stop-color="#0055cc" stop-opacity="0.15"/>
              <stop offset="100%" stop-color="#0088ff" stop-opacity="0.3"/>
            </radialGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <filter id="countryGlow">
              <feGaussianBlur stdDeviation="2" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <clipPath id="globeClip">
              <circle :cx="cx" :cy="cy" :r="radius"/>
            </clipPath>
          </defs>

          <!-- 大气层 -->
          <circle :cx="cx" :cy="cy" :r="radius+18" fill="url(#glowGrad)"/>
          <!-- 地球底色 -->
          <circle :cx="cx" :cy="cy" :r="radius" fill="url(#globeGrad)" style="cursor:grab"/>

          <!-- 地图内容（裁剪到球内） -->
          <g clip-path="url(#globeClip)">
            <!-- 经纬度网格 -->
            <g class="graticule" v-html="graticuleHtml"></g>
            <!-- 国家 -->
            <g class="countries">
              <path
                v-for="c in countryPaths"
                :key="c.code"
                :d="c.d"
                :class="['country-path', c.level, {selected: selectedCodes.has(c.code), 'has-data': c.hasData}]"
                @click="c.hasData && selectCountryByCode(c.code)"
                @mouseenter="hoveredCountry=c.code"
                @mouseleave="hoveredCountry=null"
              />
            </g>
            <!-- 国家标签（有数据的主要国家） -->
            <g class="labels">
              <text v-for="l in countryLabels" :key="l.code"
                :x="l.x" :y="l.y"
                class="country-label"
                :class="{selected: selectedCodes.has(l.code)}"
                @click="selectCountryByCode(l.code)"
              >{{ l.label }}</text>
            </g>
          </g>

          <!-- 地球边框光晕 -->
          <circle :cx="cx" :cy="cy" :r="radius" fill="none" stroke="#0055aa" stroke-width="1.5" opacity="0.6"/>
          <circle :cx="cx" :cy="cy" :r="radius+2" fill="none" stroke="#003388" stroke-width="1" opacity="0.3"/>

          <!-- Tooltip -->
          <g v-if="hoveredCountry && !selectedCountry && tooltipPos" class="tooltip-g">
            <rect :x="tooltipPos.x+8" :y="tooltipPos.y-22" :width="tooltipWidth" height="24" rx="3"
              fill="#0a1a3a" stroke="#0055aa" stroke-width="1" opacity="0.95"/>
            <text :x="tooltipPos.x+14" :y="tooltipPos.y-5" class="tooltip-text">
              {{ countryNameMap[hoveredCountry] || hoveredCountry }}
              <tspan style="fill:#00ccff"> · {{ getCountryCoverageText(hoveredCountry) }}</tspan>
            </text>
          </g>
        </svg>

        <!-- 操作提示 -->
        <div class="map-hint">
          <span>拖拽旋转</span>
          <span class="hint-sep">·</span>
          <span>滚轮缩放</span>
          <span class="hint-sep">·</span>
          <span>点击辖区查看详情</span>
        </div>
      </div>

      <!-- 右侧 -->
      <aside :class="['side-panel', 'right-panel', 'agent-side', { 'chat-mode': activePanel==='ask' }]">
        <div class="agent-tabs">
          <button :class="{active: activePanel==='overview'}" @click="activePanel='overview'">概览</button>
          <button :class="{active: activePanel==='ask'}" @click="activePanel='ask'">合规问答</button>
          <button :class="{active: activePanel==='evidence'}" @click="activePanel='evidence'">证据</button>
        </div>

        <div class="builtin-ai-strip">
          <div>
            <span class="ai-dot"></span>
            <strong>合规助手 · 已核验本地语料</strong>
          </div>
          <button v-if="!isLoggedIn" class="login-chip" @click="openLogin">登录问答</button>
        </div>

        <template v-if="activePanel==='overview'">
          <template v-if="!selectedCountry">
            <div class="panel-title">⚡ 实时动态</div>
            <div class="change-list">
              <div v-for="c in recentChanges" :key="c.changed_at+c.name" class="change-item">
                <span :class="['change-type', c.change_type]">
                  {{ {created:'新增',updated:'更新',deprecated:'废止'}[c.change_type] }}
                </span>
                <div class="change-info">
                  <div class="change-name">{{ shortText(displayText(c, 'name'), 36) }}</div>
                  <div class="change-meta">{{ c.country_name }} · {{ c.changed_at }}</div>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="country-detail">
              <div class="country-header">
                <button class="back-btn" @click="selectedCountry=null; countryDetail=null; selectedCodes=new Set()">← 返回</button>
                <div>
                  <div class="country-name-big">{{ countryDetail?.country?.name_zh || selectedCountry }}</div>
                  <div class="country-region">
                    {{ countryDetail?.country?.region || '' }} · {{ jurisdictionTypeText(countryDetail?.country?.jurisdiction_type) }}
                  </div>
                </div>
                <div class="country-code-tag">{{ selectedCountry }}</div>
              </div>

              <div v-if="detailLoading" class="loading-txt">加载中...</div>
              <template v-else-if="countryDetail">
                <div class="detail-stats">
                  <div class="ds-item" v-for="s in detailStats" :key="s.label">
                    <div class="ds-num" :style="{color: s.color}">{{ s.value }}</div>
                    <div class="ds-lbl">{{ s.label }}</div>
                  </div>
                </div>

                <div class="overview-actions">
                  <button class="agent-action" @click="activePanel='ask'; askCountryPreset()">询问该辖区要求</button>
                  <button class="agent-action ghost" @click="activePanel='evidence'">查看证据台</button>
                </div>

                <div class="coverage-card" :class="coverageClass(countryDetail.coverage?.coverage_status)">
                  <div class="coverage-row">
                    <span class="coverage-label">覆盖状态</span>
                    <span class="coverage-value">{{ coverageStatusText(countryDetail.coverage?.coverage_status) }}</span>
                  </div>
                  <div class="coverage-row">
                    <span class="coverage-label">产品制度</span>
                    <span class="coverage-value">{{ productCoverageText(countryDetail.coverage?.product_coverage_status) }}</span>
                  </div>
                  <div class="coverage-note">
                    {{ displayText(countryDetail.coverage, 'review_note') || displayText(countryDetail.coverage, 'next_action') || '暂无覆盖备注' }}
                  </div>
                </div>

                <div v-if="countryScopeSummary.total" class="scope-summary-card">
                  <div>
                    <span>本地制度</span>
                    <b>{{ countryScopeSummary.local }}</b>
                  </div>
                  <div>
                    <span>区域/上级适用</span>
                    <b>{{ countryScopeSummary.inherited }}</b>
                  </div>
                  <p v-if="countryScopeSummary.inherited">
                    已自动合并欧盟等上级辖区的已核验证据；例如法国会展示欧盟 CRA、RED、EUCC 等适用要求。
                  </p>
                </div>

                <div v-if="countryDetail.upcoming?.length" class="upcoming-section">
                  <div class="section-title">⏰ 近90天适用节点</div>
                  <div v-for="u in countryDetail.upcoming" :key="u.name" class="upcoming-item" @click="openItemDetail(u.id)">
                    <span class="days-badge" :class="{urgent: u.days_left<=30}">{{ u.days_left }}天</span>
                    <span class="upcoming-name">{{ shortText(`${displayText(u, 'name')} · ${u.milestone_label_zh || '生效/适用节点'}`, 50) }}</span>
                  </div>
                </div>

                <div v-if="countryDetail.changes?.length" class="changes-section">
                  <div class="section-title">🔄 最近变更</div>
                  <div v-for="c in countryDetail.changes" :key="c.changed_at+c.name" class="mini-change">
                    <span :class="['mini-type', c.change_type]">{{ {created:'增',updated:'改',deprecated:'废'}[c.change_type] }}</span>
                    <span class="mini-name">{{ shortText(displayText(c, 'name'), 35) }}</span>
                  </div>
                </div>

                <div v-if="priorityComplianceItems(countryDetail.items).length" class="priority-regimes">
                  <div class="section-title">⭐ 关键适用要求</div>
                  <button
                    v-for="item in priorityComplianceItems(countryDetail.items)"
                    :key="`priority-${item.id || item.name}`"
                    class="priority-regime-card"
                    @click="openItemDetail(item.id)"
                  >
                    <span class="priority-regime-meta">
                      {{ mandatoryText(item.mandatory) }} · {{ item.scope_origin === 'inherited' ? `${item.inherited_from_code || item.source_jurisdiction_code}适用` : '本地' }}
                    </span>
                    <strong>{{ shortText(displayText(item, 'name'), 52) }}</strong>
                  </button>
                </div>

                <div class="compliance-list">
                  <div class="section-title">📋 合规要求（{{ countryDetail.summary.total }}条）</div>
                  <div v-if="localComplianceItems.length" class="compliance-group-title">本地制度</div>
                  <div v-for="item in localComplianceItems" :key="item.id || item.name" class="comp-item" @click="openItemDetail(item.id)">
                    <span :class="['comp-type', item.entry_type]">
                      {{ {regulation:'法规',certification:'认证',standard:'标准'}[item.entry_type] }}
                    </span>
	                    <span :class="['comp-mand', item.mandatory]">
	                      {{ mandatoryText(item.mandatory) }}
	                    </span>
	                    <span :class="['comp-regime', item.regime_category || 'general_cyber_law']">
	                      {{ regimeCategoryText(item.regime_category) }}
	                    </span>
	                    <span class="comp-scope local">本地</span>
	                    <span class="comp-name" :title="item.name">{{ shortText(displayText(item, 'name'), 40) }}</span>
                  </div>
                  <div v-if="inheritedComplianceItems.length" class="compliance-group-title inherited">区域/上级辖区适用</div>
                  <div v-for="item in inheritedComplianceItems" :key="item.id || item.name" class="comp-item inherited" @click="openItemDetail(item.id)">
                    <span :class="['comp-type', item.entry_type]">
                      {{ {regulation:'法规',certification:'认证',standard:'标准'}[item.entry_type] }}
                    </span>
                    <span :class="['comp-mand', item.mandatory]">
                      {{ mandatoryText(item.mandatory) }}
                    </span>
                    <span :class="['comp-regime', item.regime_category || 'general_cyber_law']">
                      {{ regimeCategoryText(item.regime_category) }}
                    </span>
                    <span class="comp-scope inherited">{{ complianceScopeLabel(item) }}</span>
                    <span class="comp-name" :title="item.name">{{ shortText(displayText(item, 'name'), 40) }}</span>
                  </div>
                  <div v-if="!countryDetail.items?.length" class="empty-list">暂无已核验条目；可先查看官方源，等待工件下载和审核闭环。</div>
                </div>

                <div class="source-list">
                  <div class="section-title">🔗 官方源（{{ countryDetail.official_sources?.length || 0 }}个）</div>
                  <a v-for="source in countryDetail.official_sources" :key="source.id" class="source-item"
                    :href="source.official_evidence_url || source.list_url" target="_blank" rel="noreferrer">
                    <span class="source-type" :title="source.source_type">{{ sourceTypeLabel(source.source_type) }}</span>
                    <span v-if="source.scope_origin === 'inherited'" class="source-scope">{{ sourceScopeText(source) }}</span>
                    <span class="source-name">{{ sourceDisplayName(source) }}</span>
                  </a>
                </div>
              </template>
            </div>
          </template>
        </template>

        <template v-else-if="activePanel==='ask'">
          <div class="qa-panel chatgpt-panel">
            <div class="chat-header">
              <div>
                <div class="chat-kicker">内置合规助手</div>
                <div class="chat-title">网安合规助手</div>
              </div>
              <button class="chat-clear" :disabled="qaAsking || !qaTurns.length" @click="resetScreenQa">清空</button>
            </div>

            <div class="chat-scope-grid">
              <div><span>辖区/市场</span><b>{{ qaScopeCountryName }}</b></div>
              <div><span>文档</span><b>{{ qaScopeDocumentLabel }}</b></div>
              <div><span>边界</span><b>仅已核验</b></div>
            </div>

            <div ref="chatScroll" class="chat-thread">
              <div v-if="!qaTurns.length" class="chat-welcome">
                <div class="welcome-orb"></div>
                <h3>只回答网安合规问题</h3>
                <p>我会调用清单、规格库、已核验原文检索、生效提醒和证据链工具；无关问题会被过滤，不进入补源工单。</p>
                <div class="welcome-prompts">
                  <button :disabled="!selectedCountry" @click="askCountryPreset">查该辖区强制/自愿要求</button>
                  <button @click="askProductPreset">查产品适用要求</button>
                  <button @click="askAlertPreset">查生效提醒</button>
                  <button :disabled="!selectedCountry && (!itemDetail || itemDetail.error)" @click="askEvidencePreset">查看证据链</button>
                </div>
              </div>

              <article v-for="turn in qaTurns" :key="turn.id" :class="['chat-message-row', turn.role]">
                <div class="chat-avatar">{{ turn.role === 'user' ? '你' : 'AI' }}</div>
                <div class="chat-bubble">
                  <div class="chat-meta">
                    <span>{{ turn.role === 'user' ? '你的问题' : '内置 AI · 已核验本地语料' }}</span>
                    <span>{{ turn.createdAt }}</span>
                  </div>
                  <div
                    v-if="turn.role === 'assistant'"
                    class="chat-content markdown-body"
                    v-html="renderAgentMarkdown(turn.content)"
                  ></div>
                  <div v-else class="chat-content">{{ turn.content }}</div>
                  <div v-if="turn.result?.tool_trace?.length" class="tool-trace">
                    <span v-for="item in turn.result.tool_trace" :key="`${turn.id}-${item.tool}`">
                      <span :title="item.tool">{{ agentToolLabel(item.tool) }}</span>
                      ·
                      <span :title="item.status">{{ statusLabel(item.status) }}</span>
                      · {{ item.count ?? 0 }}
                    </span>
                  </div>
                  <div v-if="turn.result?.citations?.length" class="message-sources">
                    <button
                      v-for="(citation, index) in turn.result.citations.slice(0, 3)"
                      :key="`${turn.id}-source-${index}`"
                      @click="openCitationSource(citation)"
                    >
                      证据 {{ index + 1 }} · {{ shortText(citation.document_name, 22) }}
                    </button>
                  </div>
                  <div v-if="turn.result?.case_id" class="case-chip">工单 {{ turn.result.case_id }}</div>
                  <div v-if="turn.result?.status" :class="['qa-status', turn.result.status]">
                    {{ agentStatusText(turn.result.status) }}
                  </div>
                </div>
              </article>

              <article v-if="qaAsking" class="chat-message-row assistant">
                <div class="chat-avatar">AI</div>
                <div class="chat-bubble thinking">
                  <span></span><span></span><span></span>
                  <em>正在检索已核验证据...</em>
                </div>
              </article>
            </div>

            <div v-if="!isLoggedIn" class="qa-login-box chat-login-box">
              <div class="qa-login-title">登录后使用内置 AI 问答</div>
              <p>地图和条目可公开浏览；合规问答需要登录，后端固定只读取已核验知识库、规格库和本地原文切片。</p>
              <button class="agent-action" @click="openLogin">去登录</button>
            </div>

            <div v-if="qaError" class="qa-error">{{ qaError }}</div>

            <form class="chat-composer" @submit.prevent="askScreenQuestion">
              <textarea
                id="screen-agent-question"
                name="screen-agent-question"
                v-model="qaQuestion"
                :disabled="!isLoggedIn || qaAsking"
                placeholder="问网安合规问题，例如：美国对交换机产品有哪些强制和自愿要求？"
                @keydown.enter.exact.prevent="askScreenQuestion"
                @keydown.meta.enter.prevent="askScreenQuestion"
                @keydown.ctrl.enter.prevent="askScreenQuestion"
              />
              <button type="submit" :disabled="!qaCanAsk">{{ qaAsking ? '检索中' : '发送' }}</button>
            </form>
            <div class="chat-footnote">仅处理网络安全合规问题 · 不联网补证 · 不读取候选/待复核/已隔离数据</div>
          </div>
        </template>

        <template v-else>
          <div class="evidence-panel">
            <div class="panel-title">证据工作台</div>
            <div class="qa-scope-card">
              <div><span>当前辖区/市场</span><b>{{ qaScopeCountryName }}</b></div>
              <div><span>当前文档</span><b>{{ qaScopeDocumentLabel }}</b></div>
            </div>

            <div class="section-title">依据片段</div>
            <div v-if="latestCitations.length" class="qa-citation-list">
              <button
                v-for="(citation, index) in latestCitations"
                :key="`${citation.document_id}-${index}`"
                class="qa-citation-card"
                @click="openCitationSource(citation)"
              >
                <span class="citation-index">证据 {{ index + 1 }}</span>
                <strong>{{ citation.document_name }}</strong>
                <em>{{ citationLocation(citation) }}</em>
                <p>{{ citation.excerpt }}</p>
              </button>
            </div>
            <div v-else class="qa-empty">暂无问答引用。完成一次问答后，这里会展示依据片段和来源。</div>

            <div class="section-title related-title">关联来源</div>
            <div v-if="latestRelatedRecords.length" class="related-source-list">
              <button v-for="record in latestRelatedRecords" :key="record.id" class="related-source" @click="openItemDetail(record.id)">
                <span>{{ record.country_code }}</span>
                <b>{{ record.name }}</b>
              </button>
            </div>
            <div v-else class="qa-empty">暂无关联结构化记录。</div>
          </div>
        </template>
      </aside>
    </div>

    <div v-if="itemDetail || itemLoading" class="detail-modal-mask" @click.self="closeItemDetail">
      <div class="detail-modal">
        <button class="modal-close" @click="closeItemDetail">×</button>
        <div v-if="itemLoading" class="loading-txt">加载条目详情...</div>
        <template v-else-if="itemDetail">
          <div class="modal-kicker">{{ itemDetail.country_name }} · {{ typeText(itemDetail.entry_type) }} · {{ mandatoryText(itemDetail.mandatory) }} · {{ scopeOriginText(itemDetail) }}</div>
          <div class="modal-title">{{ displayText(itemDetail, 'name') }}</div>
          <div v-if="originalText(itemDetail, 'name')" class="modal-original">原文：{{ originalText(itemDetail, 'name') }}</div>
	          <div class="modal-grid">
	            <div><span>发布机构</span><b>{{ displayText(itemDetail, 'issuing_body') || '—' }}</b></div>
	            <div><span>制度分类</span><b>{{ regimeCategoryText(itemDetail.regime_category) }}</b></div>
	            <div><span>适用层级</span><b>{{ scopeOriginText(itemDetail) }}</b></div>
	            <div><span>主适用日期</span><b>{{ itemDetail.effective_date || '—' }}</b></div>
	            <div><span>发布日期</span><b>{{ itemDetail.published_date || '—' }}</b></div>
	            <div><span>审核时间</span><b>{{ itemDetail.checked_at || '—' }}</b></div>
          </div>
          <div class="modal-section" v-if="itemDetail.lifecycle_milestones?.length">
            <div class="modal-section-title">法规生命周期节点</div>
            <div class="milestone-list">
              <div
                v-for="milestone in itemDetail.lifecycle_milestones"
                :key="milestone.milestone_key"
                class="milestone-item"
              >
                <span>{{ milestone.milestone_date }}</span>
                <div>
                  <strong>{{ milestone.milestone_label_zh || milestone.milestone_key }}</strong>
                  <p v-if="milestone.obligation_scope">{{ milestone.obligation_scope }}</p>
                  <em v-if="milestone.legal_basis">{{ milestone.legal_basis }}</em>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-section" v-if="itemDetail.summary">
            <div class="modal-section-title">摘要</div>
            <p>{{ displayText(itemDetail, 'summary') }}</p>
            <p v-if="originalText(itemDetail, 'summary')" class="original-text">原文：{{ originalText(itemDetail, 'summary') }}</p>
          </div>
          <div class="modal-section" v-if="itemDetail.scope_description">
            <div class="modal-section-title">适用范围</div>
            <p>{{ displayText(itemDetail, 'scope_description') }}</p>
            <p v-if="originalText(itemDetail, 'scope_description')" class="original-text">原文：{{ originalText(itemDetail, 'scope_description') }}</p>
          </div>
          <div class="modal-section" v-if="arrayText(itemDetail.technical_standards)">
            <div class="modal-section-title">技术标准</div>
            <p>{{ arrayText(itemDetail.technical_standards) }}</p>
          </div>
          <div class="modal-section" v-if="itemDetail.evidence_note">
            <div class="modal-section-title">真实性证据</div>
            <p>{{ displayText(itemDetail, 'evidence_note') }}</p>
            <p v-if="originalText(itemDetail, 'evidence_note')" class="original-text">原文：{{ originalText(itemDetail, 'evidence_note') }}</p>
          </div>
          <div class="modal-actions">
            <button class="modal-ai-btn" :disabled="itemDetail.error" @click="askFromItemDetail">基于此条目提问</button>
            <a v-if="itemDetail.official_url" :href="itemDetail.official_url" target="_blank" rel="noreferrer">打开官方来源</a>
            <span v-if="itemDetail.document_id">文档ID {{ itemDetail.document_id }}</span>
            <span v-else>暂无可限定文档，将按当前辖区范围问答</span>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'
import * as topojson from 'topojson-client'
import { api, agentApi } from '@/api'
import { agentToolLabel, sourceTypeLabel, statusLabel } from '@/utils/labels'

// ---- 状态 ----
const mapSvg = ref(null)
const stats = ref({ total:0, countries:0, mandatory:0, certifications:0, top_countries:[] })
const allCountries = ref([])
const recentChanges = ref([])
const selectedCountry = ref(null)
const selectedCodes = ref(new Set())  // 高亮的所有代码
const countryDetail = ref(null)
const detailLoading = ref(false)
const itemDetail = ref(null)
const itemLoading = ref(false)
const hoveredCountry = ref(null)
const tooltipPos = ref(null)
const currentTime = ref('')
const searchQuery = ref('')
const searchResults = ref([])
const countryNameMap = ref({})
const countryDataMap = ref({})  // code -> {total, priority}
const activePanel = ref('overview')
const authToken = ref(localStorage.getItem('token') || '')
const qaQuestion = ref('')
const qaAsking = ref(false)
const qaTurns = ref([])
const latestQaResult = ref(null)
const qaError = ref('')
const chatScroll = ref(null)

// D3 投影状态
let projection, pathGenerator, worldData
const svgW = ref(900), svgH = ref(700)
const cx = computed(() => svgW.value / 2)
const cy = computed(() => svgH.value / 2)
const radius = computed(() => Math.min(svgW.value, svgH.value) * 0.44)
const countryPaths = ref([])
const countryLabels = ref([])
const graticuleHtml = ref('')

// 拖拽状态
let isDragging = false
let dragStart = null
let rotateStart = [0, 0]

// ---- 计算属性 ----
const headerStats = computed(() => [
  { label: '已核验条目', value: stats.value.total },
  { label: '覆盖辖区', value: stats.value.countries },
  { label: '官方源辖区', value: stats.value.official_source_countries },
  { label: '查无制度', value: stats.value.no_specific_source_countries },
])

const topCountries = computed(() => stats.value.top_countries?.slice(0,8) || [])

const regionStats = computed(() => {
  const map = {}
  allCountries.value.forEach(c => {
    const r = c.region || '其他'
    if (c.coverage_status !== 'needs_source_research') {
      map[r] = (map[r] || 0) + 1
    }
  })
  const total = Object.values(map).reduce((a,b)=>a+b,0) || 1
  return Object.entries(map).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([region, cnt]) => ({
    region, cnt, pct: Math.round(cnt*100/total)
  }))
})

const detailStats = computed(() => {
  if (!countryDetail.value?.summary) return []
  const s = countryDetail.value.summary
	  return [
	    { label: '总条数', value: s.total, color: '#00ccff' },
	    { label: '官方源', value: s.official_sources || 0, color: '#ffd060' },
	    { label: '产品制度', value: s.product_regime || 0, color: '#00e5a0' },
	    { label: '通用法规', value: s.general_cyber_law || 0, color: '#95a8bc' },
	  ]
	})

const isLoggedIn = computed(() => Boolean(authToken.value))

const qaScopeCountry = computed(() => selectedCountry.value || itemDetail.value?.country_code || '')

const qaScopeDocument = computed(() => itemDetail.value?.document_id || '')

const qaScopeItemName = computed(() => {
  if (!itemDetail.value || itemDetail.value.error) return ''
  return displayText(itemDetail.value, 'name')
})

const qaScopeCountryName = computed(() => {
  const code = qaScopeCountry.value
  if (!code) return '全球已核验语料'
  return countryDetail.value?.country?.name_zh || countryNameMap.value[code] || code
})

const qaScopeDocumentLabel = computed(() => {
  if (qaScopeDocument.value) return shortText(qaScopeItemName.value || qaScopeDocument.value, 34)
  return '不限定单文档'
})

const qaCanAsk = computed(() => isLoggedIn.value && !qaAsking.value && qaQuestion.value.trim().length >= 2)

const latestCitations = computed(() => latestQaResult.value?.citations || [])

const latestRelatedRecords = computed(() => latestQaResult.value?.related_records || [])

const localComplianceItems = computed(() =>
  orderedComplianceItems(countryDetail.value?.items || [])
    .filter(item => item.scope_origin !== 'inherited')
)

const inheritedComplianceItems = computed(() =>
  orderedComplianceItems(countryDetail.value?.items || [])
    .filter(item => item.scope_origin === 'inherited')
)

const countryScopeSummary = computed(() => ({
  total: countryDetail.value?.items?.length || 0,
  local: localComplianceItems.value.length,
  inherited: inheritedComplianceItems.value.length,
}))

const tooltipWidth = computed(() => {
  const name = countryNameMap.value[hoveredCountry.value] || hoveredCountry.value || ''
  return Math.max(100, name.length * 14 + 60)
})

function getCountryCnt(code) {
  return countryDataMap.value[code]?.verified_record_count || countryDataMap.value[code]?.total || 0
}

function coverageStatusText(status) {
  return {
    verified_records_available: '已有已核验正式记录',
    official_sources_seeded: '已找到官方源，待工件/审核闭环',
    researched_no_specific_source: '已查无独立产品级制度',
    needs_source_research: '待查官方源',
  }[status] || '待查官方源'
}

function productCoverageText(status) {
  return {
    product_regime_verified: '已有产品级法规/认证/标准',
    general_cyber_law_verified: '已有通用网络安全法规',
    no_product_regime_found_verified: '未发现独立产品制度',
    pending_source_research: '待确认',
  }[status] || '待确认'
}

function citationLocation(citation) {
  const rawClause = String(citation?.clause_ref || '').trim()
  const clause = rawClause && rawClause !== 'verified read model' ? rawClause : '结构化记录'
  if (citation?.page_from === null || citation?.page_from === undefined || citation?.page_from === '') {
    return clause
  }
  const pageTo = citation.page_to
  const range = pageTo && pageTo !== citation.page_from ? `${citation.page_from}-${pageTo}` : citation.page_from
  return `${clause} · 第 ${range} 页`
}

function countryCoverageLabel(country) {
  if (!country) return '—'
  const localCount = Number(country.verified_record_count || country.total || 0)
  const inheritedCount = Number(country.inherited_verified_count || 0)
  if (localCount || inheritedCount) {
    if (inheritedCount) return `${localCount}本地+${inheritedCount}区域`
    return `${localCount}条`
  }
  if (country.official_source_count) return `${country.official_source_count}源`
  if (country.coverage_status === 'researched_no_specific_source') return '无'
  return '待查'
}

function getCountryCoverageText(code) {
  const c = countryDataMap.value[code]
  if (!c) return '待查'
  return countryCoverageLabel(c)
}

function coverageClass(status) {
  return {
    verified_records_available: 'verified',
    official_sources_seeded: 'source',
    researched_no_specific_source: 'none',
    needs_source_research: 'pending',
  }[status] || 'pending'
}

function typeText(value) {
  return { regulation: '法规', certification: '认证', standard: '标准' }[value] || value || '—'
}

function mandatoryText(value) {
  return value === 'mandatory' ? '强制' : value === 'voluntary' ? '自愿' : value === 'recommended' ? '推荐' : '—'
}

function jurisdictionTypeText(value) {
  return {
    country: '国家',
    regional_bloc: '区域组织',
    special_region: '特殊地区',
    territory: '地区',
  }[value] || '辖区'
}

function regimeCategoryText(value) {
  return value === 'product_regime' ? '产品制度' : value === 'general_cyber_law' ? '通用法规' : '未分类'
}

function scopeOriginText(item) {
  if (!item) return '—'
  if (item.scope_origin === 'inherited') {
    const source = item.source_jurisdiction_name || countryNameMap.value[item.inherited_from_code] || item.inherited_from_code || item.source_jurisdiction_code || '上级辖区'
    const target = item.selected_country_name || countryNameMap.value[item.selected_country_code] || ''
    return target ? `来自${source}，适用于${target}` : `${source}层面适用`
  }
  return '本地辖区'
}

function complianceScopeLabel(item) {
  const source = item?.source_jurisdiction_name || countryNameMap.value[item?.inherited_from_code] || item?.inherited_from_code || item?.source_jurisdiction_code || '上级辖区'
  return `${source}适用`
}

function sourceScopeText(source) {
  const sourceCode = source?.source_jurisdiction_code || '上级辖区'
  const sourceName = countryNameMap.value[sourceCode] || sourceCode
  return `${sourceName}适用`
}

function arrayText(value) {
  if (!value) return ''
  return Array.isArray(value) ? value.filter(Boolean).join('、') : String(value)
}

function displayText(record, field) {
  if (!record) return ''
  return record[`${field}_zh`] || record.translations?.[field] || record[field] || ''
}

function originalText(record, field) {
  if (!record) return ''
  const original = record[field]
  const translated = record[`${field}_zh`] || record.translations?.[field]
  if (!original || !translated || String(original) === String(translated)) return ''
  return original
}

function shortText(value, maxLength) {
  const text = String(value || '')
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}

function complianceImportanceRank(item) {
  const name = `${item?.name || ''} ${item?.name_zh || ''}`.toLowerCase()
  let score = 0
  if (item?.regime_category === 'product_regime') score -= 200
  if (item?.mandatory === 'mandatory') score -= 160
  if (item?.entry_type === 'regulation') score -= 60
  if (item?.scope_origin === 'inherited') score -= 20
  if (name.includes('cyber resilience act') || name.includes('2024/2847') || name.includes('cra')) score -= 100
  if (name.includes('red delegated') || name.includes('2022/30')) score -= 80
  if (name.includes('nis 2') || name.includes('2022/2555')) score -= 70
  if (name.includes('eucc')) score -= 40
  return score
}

function orderedComplianceItems(items = []) {
  return [...items].sort((a, b) => {
    const rankDiff = complianceImportanceRank(a) - complianceImportanceRank(b)
    if (rankDiff) return rankDiff
    return String(displayText(a, 'name')).localeCompare(String(displayText(b, 'name')), 'zh-Hans-CN')
  })
}

function priorityComplianceItems(items = []) {
  return orderedComplianceItems(items)
    .filter(item => item.regime_category === 'product_regime' && item.mandatory === 'mandatory')
    .slice(0, 3)
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_match, label, url) => {
      const safeUrl = escapeHtml(url)
      return `<a href="${safeUrl}" target="_blank" rel="noreferrer">${label}</a>`
    })
}

function renderAgentMarkdown(value) {
  const text = String(value || '').replace(/\r\n/g, '\n').trim()
  if (!text) return ''

  const lines = text.split('\n')
  const html = []
  let listType = null
  let inCode = false
  let codeLines = []
  let paragraph = []

  const closeParagraph = () => {
    if (!paragraph.length) return
    html.push(`<p>${paragraph.map(renderInlineMarkdown).join('<br>')}</p>`)
    paragraph = []
  }
  const closeList = () => {
    if (!listType) return
    html.push(`</${listType}>`)
    listType = null
  }
  const openList = type => {
    closeParagraph()
    if (listType === type) return
    closeList()
    listType = type
    html.push(`<${type}>`)
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        inCode = false
      } else {
        closeParagraph()
        closeList()
        inCode = true
        codeLines = []
      }
      continue
    }

    if (inCode) {
      codeLines.push(rawLine)
      continue
    }

    if (!trimmed) {
      closeParagraph()
      closeList()
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      closeParagraph()
      closeList()
      const level = Math.min(heading[1].length + 2, 5)
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

	    if (/^(结论|依据|后续动作|来源|依据片段|强制类|自愿\/推荐类|其他\/未标明强制性|产品级强制类|产品级自愿\/推荐类|产品级其他\/未标明强制性|通用网络安全背景（不直接等同于产品准入\/认证要求）)：?$/.test(trimmed)) {
      closeParagraph()
      closeList()
      html.push(`<h4>${renderInlineMarkdown(trimmed.replace(/：$/, ''))}</h4>`)
      continue
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      openList('ul')
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`)
      continue
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (ordered) {
      openList('ol')
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`)
      continue
    }

    paragraph.push(trimmed)
  }

  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }
  closeParagraph()
  closeList()
  return html.join('')
}

function cleanSourcePrefix(value) {
  return String(value || '')
    .replace(/^Curated Official Evidence\s*-\s*/i, '')
    .replace(/^精选官方证据\s*-\s*/, '')
}

function sourceDisplayName(source) {
  return cleanSourcePrefix(displayText(source, 'name'))
}

function refreshAuthToken() {
  authToken.value = localStorage.getItem('token') || ''
}

function openLogin() {
  localStorage.setItem('screen_return_to', window.location.pathname + window.location.search)
  window.location.href = '/login'
}

function buildQaTurn(role, content, result = null) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role,
    content,
    result,
    createdAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  }
}

async function scrollChatToBottom() {
  await nextTick()
  const el = chatScroll.value
  if (el) el.scrollTop = el.scrollHeight
}

function agentStatusText(status) {
  return {
    answered: '已基于证据回答',
    case_created: '已创建补源/审核任务',
    needs_clarification: '需要补充条件',
    insufficient_evidence: '证据不足',
    out_of_scope: '已过滤无关问题',
    blocked: '已拦截越权指令',
    error: '调用异常',
  }[status] || '调用异常'
}

function buildQaHistory() {
  return qaTurns.value
    .slice(-8)
    .map(turn => ({ role: turn.role, content: turn.content }))
    .filter(item => item.content?.trim())
}

function fillScreenPrompt(prompt) {
  qaQuestion.value = prompt
  activePanel.value = 'ask'
}

function askCountryPreset() {
  const country = qaScopeCountryName.value
  fillScreenPrompt(`${country} 当前已核验的产品网络安全法规、认证和标准有哪些？请按强制/自愿分类，并给出依据。`)
}

function askItemPreset() {
  const name = qaScopeItemName.value || '当前选中的法规/认证'
  fillScreenPrompt(`${name} 对网络安全合规的核心要求有哪些？请只基于原文证据回答。`)
}

function askProductPreset() {
  const country = qaScopeCountryName.value
  fillScreenPrompt(`${country} 对交换机/路由器/网关等产品有哪些网络安全合规要求？请按强制/自愿分类，并给出依据。`)
}

function askAlertPreset() {
  const country = qaScopeCountryName.value
  fillScreenPrompt(`${country} 未来90天有哪些即将进入适用阶段的网络安全合规要求？请给出具体节点日期、节点含义和依据。`)
}

function askEvidencePreset() {
  const scope = qaScopeItemName.value || qaScopeCountryName.value
  fillScreenPrompt(`${scope} 当前已核验记录有哪些官方来源、证据链和原文依据？`)
}

async function askFromItemDetail() {
  if (!itemDetail.value || itemDetail.value.error) return
  activePanel.value = 'ask'
  askItemPreset()
  if (!isLoggedIn.value) {
    qaError.value = '登录后使用内置 AI 问答'
    return
  }
  await askScreenQuestion()
}

async function askScreenQuestion() {
  refreshAuthToken()
  if (!isLoggedIn.value) {
    qaError.value = '登录后使用内置 AI 问答'
    return
  }
  const question = qaQuestion.value.trim()
  if (!question || qaAsking.value) return

  qaError.value = ''
  const history = buildQaHistory()
  qaTurns.value.push(buildQaTurn('user', question))
  await scrollChatToBottom()
  qaAsking.value = true
  try {
    const response = await agentApi.ask({
      question,
      country_code: qaScopeCountry.value || null,
      product_code: null,
      document_id: qaScopeDocument.value || null,
      alert_window_days: 90,
      verified_only: true,
      history,
    })
    latestQaResult.value = response
    qaTurns.value.push(buildQaTurn('assistant', response.answer, response))
    qaQuestion.value = ''
    await scrollChatToBottom()
  } catch (e) {
    const message = String(e)
    qaError.value = message
    const errorResult = {
      status: 'error',
      answer: `本次内置 AI 问答没有完成：${message}`,
      citations: [],
      related_records: [],
    }
    latestQaResult.value = errorResult
    qaTurns.value.push(buildQaTurn('assistant', errorResult.answer, errorResult))
    await scrollChatToBottom()
  } finally {
    qaAsking.value = false
    await scrollChatToBottom()
  }
}

async function openCitationSource(citation) {
  if (!citation) return
  const related = latestRelatedRecords.value.find(row => (
    row.id || row.compliance_id
  ) && (
    row.name === citation.document_name || row.country_code === citation.country_code
  ))
  if (related?.id || related?.compliance_id) {
    await openItemDetail(related.id || related.compliance_id)
    activePanel.value = 'overview'
    return
  }
  if (citation.country_code) {
    await selectCountryByCode(citation.country_code)
    activePanel.value = 'overview'
  }
}

function resetScreenQa() {
  qaQuestion.value = ''
  qaTurns.value = []
  latestQaResult.value = null
  qaError.value = ''
}

// ---- 数据加载 ----
async function fetchData() {
  try {
    const [s, c, r] = await Promise.all([
      fetch('/api/public/stats').then(r=>r.json()),
      fetch('/api/public/countries').then(r=>r.json()),
      fetch('/api/public/recent-changes').then(r=>r.json()),
    ])
    stats.value = s
    allCountries.value = c
    recentChanges.value = r.items || []
    const nm = {}, dm = {}
    c.forEach(cc => {
      nm[cc.code] = cc.name_zh
      dm[cc.code] = { ...cc }
    })
    // 台湾地区：显示为P1（和中国同色），名称标注归属
    if (dm['TW']) {
      dm['TW'].priority = 'P1'
      nm['TW'] = '中国台湾'
    } else {
      // 即使无数据也显示为P1颜色
      dm['TW'] = { total: 0, priority: 'P1' }
      nm['TW'] = '中国台湾'
    }
    countryNameMap.value = nm
    countryDataMap.value = dm
    if (worldData) renderMap()
  } catch(e) { console.error(e) }
}

// 主要国家中心经纬度 [lng, lat]
const COUNTRY_CENTER = {
  'CN':[104,35],'US':[-98,38],'GB':[-2,54],'JP':[138,36],'KR':[128,37],
  'DE':[10,51],'FR':[2,46],'RU':[100,60],'BR':[-55,-10],'IN':[78,21],
  'AU':[134,-25],'CA':[-96,56],'MX':[-102,24],'ID':[120,-5],'SA':[45,25],
  'NG':[8,10],'ZA':[25,-29],'TR':[35,39],'AR':[-64,-34],'EG':[30,27],
  'EU':[10,51],'PK':[74,31],'BD':[90,24],'PH':[122,12],'VN':[108,16],
  'TH':[101,15],'MY':[112,2],'SG':[104,1],'IL':[35,31],'AE':[54,24],
  'PL':[20,52],'NL':[5,52],'SE':[15,62],'NO':[10,62],'CH':[8,47],
  'TW':[121,24],'HK':[114,22],'MA':[(-6),32],'KE':[38,(-1)],'TZ':[35,(-6)],
  'UZ':[63,42],'KZ':[68,48],'UA':[32,49],'GH':[-2,8],'ET':[40,9],
}

function flyToCountry(code) {
  const center = COUNTRY_CENTER[code]
  if (!center || !projection) return
  const [lng, lat] = center
  // 当前旋转
  const current = projection.rotate()
  const targetRotate = [-lng, -lat, 0]
  // 简单动画：分20步旋转过去
  let step = 0
  const steps = 20
  const dr = [
    (targetRotate[0] - current[0]) / steps,
    (targetRotate[1] - current[1]) / steps,
  ]
  const timer = setInterval(() => {
    step++
    const r = projection.rotate()
    projection.rotate([r[0]+dr[0], r[1]+dr[1], 0])
    renderMap()
    if (step >= steps) clearInterval(timer)
  }, 20)
}

async function selectCountryByCode(code) {
  activePanel.value = 'overview'
  // 台湾地区归属中国（代码已归并为CN，此分支保留兼容）
  if (code === 'CN-TW') {
    selectedCountry.value = 'TW'
    detailLoading.value = false
    countryDetail.value = {
      country: { name_zh: '中国台湾', region: '亚太', code: 'TW' },
      items: [],
      upcoming: [],
      changes: [],
      summary: { total: 0, mandatory: 0, voluntary: 0, certifications: 0, regulations: 0 },
      _note: true
    }
    // 同时加载TW的合规数据
    try {
      const data = await fetch('/api/public/country/TW').then(r=>r.json())
      if (data && data.items) {
        countryDetail.value = { ...data, country: { ...data.country, name_zh: '中国台湾' } }
      }
    } catch(e) {}
    return
  }
  // 旋转地球到目标国家
  flyToCountry(code === 'TW' ? 'TW' : code)

  // 中国和台湾地区同时高亮
  if (code === 'CN' || code === 'TW') {
    selectedCodes.value = new Set(['CN', 'TW'])
  } else {
    selectedCodes.value = new Set([code])
  }
  selectedCountry.value = code
  detailLoading.value = true
  countryDetail.value = null
  itemDetail.value = null
  try {
    const data = await fetch(`/api/public/country/${code}`).then(r=>r.json())
    // 台湾地区标注归属
    if (code === 'TW' && data?.country) {
      data.country.name_zh = '中国台湾'
    }
    countryDetail.value = data
  } catch(e) { console.error(e) }
  detailLoading.value = false
}

async function openItemDetail(id) {
  if (!id) return
  itemLoading.value = true
  itemDetail.value = null
  activePanel.value = 'overview'
  try {
    const data = await fetch(`/api/public/item/${id}`).then(r=>r.json())
    if (data?.error) {
      itemDetail.value = { error: true, name: data.error, country_name: selectedCountry.value, entry_type: '', mandatory: '' }
    } else {
      const contextItem = countryDetail.value?.items?.find(item => String(item.id) === String(id))
      itemDetail.value = contextItem
        ? {
            ...data,
            scope_origin: contextItem.scope_origin,
            source_jurisdiction_code: contextItem.source_jurisdiction_code,
            source_jurisdiction_name: contextItem.source_jurisdiction_name,
            inherited_from_code: contextItem.inherited_from_code,
            inheritance_reason: contextItem.inheritance_reason,
            selected_country_code: selectedCountry.value,
            selected_country_name: countryDetail.value?.country?.name_zh,
          }
        : data
    }
  } catch(e) {
    console.error(e)
  }
  itemLoading.value = false
}

function closeItemDetail() {
  itemDetail.value = null
  itemLoading.value = false
}

// ---- 搜索 ----
function onSearch() {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) { searchResults.value = []; return }
  searchResults.value = allCountries.value
    .filter(c => c.name_zh.includes(searchQuery.value) || c.code.toLowerCase().includes(q) || (c.name_en||'').toLowerCase().includes(q))
    .slice(0, 8)
}

// ---- D3 地图 ----
async function initMap() {
  await nextTick()
  const el = mapSvg.value
  if (!el) return
  svgW.value = el.clientWidth || 900
  svgH.value = el.clientHeight || 700

  // 加载世界地图 TopoJSON（使用 CDN）
  try {
    worldData = await d3.json('/world-110m.json')
    setupProjection()
    renderMap()
    setupDrag()
  } catch(e) {
    console.error('地图加载失败:', e)
  }
}

function setupProjection() {
  projection = d3.geoOrthographic()
    .scale(radius.value)
    .center([0, 0])
    .rotate([0, -20, 0])
    .translate([cx.value, cy.value])
    .clipAngle(90)

  pathGenerator = d3.geoPath().projection(projection)
}

// ISO 数字代码 → ISO 2位字母代码映射（常用国家）
const numToAlpha = {
  '004':'AF','008':'AL','010':'AQ','012':'DZ','016':'AS','020':'AD','024':'AO','028':'AG',
  '031':'AZ','032':'AR','036':'AU','040':'AT','044':'BS','048':'BH','050':'BD','051':'AM',
  '052':'BB','056':'BE','060':'BM','064':'BT','068':'BO','070':'BA','072':'BW','076':'BR',
  '084':'BZ','090':'SB','096':'BN','100':'BG','104':'MM','108':'BI','112':'BY','116':'KH',
  '120':'CM','124':'CA','132':'CV','136':'KY','140':'CF','144':'LK','148':'TD','152':'CL',
  '156':'CN','158':'TW','170':'CO','174':'KM','178':'CG','180':'CD','188':'CR','191':'HR',
  '192':'CU','196':'CY','203':'CZ','204':'BJ','208':'DK','212':'DM','214':'DO','218':'EC',
  '222':'SV','226':'GQ','231':'ET','232':'ER','233':'EE','242':'FJ','246':'FI','250':'FR',
  '262':'DJ','266':'GA','268':'GE','270':'GM','275':'PS','276':'DE','288':'GH','296':'KI',
  '300':'GR','308':'GD','320':'GT','324':'GN','328':'GY','332':'HT','336':'VA','340':'HN','344':'HK',
  '348':'HU','352':'IS','356':'IN','360':'ID','364':'IR','368':'IQ','372':'IE','376':'IL',
  '380':'IT','384':'CI','388':'JM','392':'JP','398':'KZ','400':'JO','404':'KE','408':'KP',
  '410':'KR','414':'KW','417':'KG','418':'LA','422':'LB','426':'LS','428':'LV','430':'LR',
  '434':'LY','438':'LI','440':'LT','442':'LU','450':'MG','454':'MW','458':'MY','462':'MV',
  '466':'ML','470':'MT','478':'MR','480':'MU','484':'MX','492':'MC','496':'MN','498':'MD',
  '499':'ME','504':'MA','508':'MZ','512':'OM','516':'NA','520':'NR','524':'NP','528':'NL',
  '548':'VU','554':'NZ','558':'NI','562':'NE','566':'NG','578':'NO','583':'FM','584':'MH',
  '585':'PW','586':'PK','591':'PA','598':'PG','600':'PY','604':'PE','608':'PH','616':'PL',
  '620':'PT','624':'GW','626':'TL','630':'PR','634':'QA','642':'RO','643':'RU','646':'RW',
  '659':'KN','662':'LC','670':'VC','674':'SM','678':'ST','682':'SA','686':'SN','688':'RS',
  '690':'SC','694':'SL','702':'SG','703':'SK','704':'VN','705':'SI','706':'SO','710':'ZA',
  '716':'ZW','724':'ES','728':'SS','729':'SD','740':'SR','748':'SZ','752':'SE','756':'CH',
  '760':'SY','762':'TJ','764':'TH','768':'TG','776':'TO','780':'TT','784':'AE','788':'TN',
  '792':'TR','795':'TM','798':'TV','800':'UG','804':'UA','807':'MK','818':'EG','826':'GB',
  '834':'TZ','840':'US','854':'BF','858':'UY','860':'UZ','862':'VE','882':'WS','887':'YE',
  '894':'ZM','383':'XK',
}

function renderMap() {
  if (!worldData || !projection) return

  const countries = topojson.feature(worldData, worldData.objects.countries)
  const graticule = d3.geoGraticule()

  // 网格线
  graticuleHtml.value = `<path d="${pathGenerator(graticule())}" fill="none" stroke="#0d2a4a" stroke-width="0.5" opacity="0.6"/>`

  // 国家路径
  const paths = []
  const labels = []

  countries.features.forEach(f => {
    const numCode = f.id?.toString().padStart(3,'0')
    const code = numToAlpha[numCode] || null
    const countryData = code ? countryDataMap.value[code] : null
    const hasData = !!countryData && countryData.coverage_status !== 'needs_source_research'
    const d = pathGenerator(f)
    if (!d) return

    let level = 'no-data'
    if (hasData) {
      level = coverageClass(countryData.coverage_status)
    }

    paths.push({ code: code || numCode, d, hasData, level })

    // 标签：只显示有数据的主要国家
    if (hasData && ['CN','US','GB','JP','KR','DE','FR','AU','BR','IN','RU','CA','SA','NG','ZA','MX','ID','TR','AR'].includes(code)) {
      const centroid = pathGenerator.centroid(f)
      if (centroid && !isNaN(centroid[0])) {
        const labelNames = {
          'CN':'China','US':'United States','GB':'UK','JP':'Japan',
          'KR':'Korea','DE':'Germany','FR':'France','AU':'Australia',
          'BR':'Brazil','IN':'India','RU':'Russia','CA':'Canada',
          'SA':'Saudi Arabia','NG':'Nigeria','ZA':'S.Africa',
          'MX':'Mexico','ID':'Indonesia','TR':'Turkey','AR':'Argentina'
        }
        labels.push({ code, x: centroid[0], y: centroid[1], label: labelNames[code] || code })
      }
    }
  })

  countryPaths.value = paths
  countryLabels.value = labels
}

// ---- 鼠标交互 ----
function setupDrag() {
  const el = mapSvg.value
  el.addEventListener('mousedown', onMouseDown)
  el.addEventListener('mousemove', onMouseMove)
  el.addEventListener('mouseup', onMouseUp)
  el.addEventListener('mouseleave', () => { isDragging = false; hoveredCountry.value = null; tooltipPos.value = null })
}

function onMouseDown(e) {
  if (e.target.tagName === 'path' || e.target.tagName === 'circle') {
    isDragging = false
    dragStart = { x: e.clientX, y: e.clientY }
    rotateStart = [...projection.rotate()]
  }
}

function onMouseMove(e) {
  if (dragStart) {
    const dx = e.clientX - dragStart.x
    const dy = e.clientY - dragStart.y
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      isDragging = true
      const r = projection.rotate()
      projection.rotate([
        rotateStart[0] + dx * 0.3,
        rotateStart[1] - dy * 0.2,
        r[2]
      ])
      renderMap()
    }
  }
  // tooltip 位置
  const rect = mapSvg.value.getBoundingClientRect()
  tooltipPos.value = { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function onMouseUp(e) {
  if (!isDragging && dragStart) {
    // 点击事件由 path 的 @click 处理
  }
  isDragging = false
  dragStart = null
}

function onWheel(e) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newScale = Math.max(100, Math.min(2000, projection.scale() * delta))
  projection.scale(newScale)
  renderMap()
}

// 时钟
let clockTimer, refreshTimer
function updateTime() {
  currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

// 响应窗口变化
function onResize() {
  if (!mapSvg.value) return
  svgW.value = mapSvg.value.clientWidth
  svgH.value = mapSvg.value.clientHeight
  if (projection) {
    projection.translate([cx.value, cy.value]).scale(radius.value)
    renderMap()
  }
}

onMounted(async () => {
  refreshAuthToken()
  updateTime()
  clockTimer = setInterval(updateTime, 1000)
  await fetchData()
  await initMap()
  refreshTimer = setInterval(fetchData, 60000)
  window.addEventListener('resize', onResize)
  window.addEventListener('storage', refreshAuthToken)
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('storage', refreshAuthToken)
  const el = mapSvg.value
  if (el) {
    el.removeEventListener('mousedown', onMouseDown)
    el.removeEventListener('mousemove', onMouseMove)
    el.removeEventListener('mouseup', onMouseUp)
  }
})
</script>

<style scoped>
.screen-wrap {
  width:100vw; height:100vh; background:#020812;
  display:flex; flex-direction:column; overflow:hidden;
  font-family:'IBM Plex Mono','SF Mono',monospace; color:#c8d8e8;
  background-image:
    radial-gradient(ellipse at 20% 50%, rgba(0,50,150,.12) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 20%, rgba(0,100,200,.06) 0%, transparent 50%);
}
.screen-header {
  height:58px; flex-shrink:0; display:flex; align-items:center;
  justify-content:space-between; padding:0 24px;
  border-bottom:1px solid rgba(0,180,255,.12);
  background:rgba(0,6,20,.9); backdrop-filter:blur(10px);
}
.header-left { display:flex; align-items:center; gap:12px; }
.logo-dot { width:9px; height:9px; border-radius:50%; background:#00ccff; box-shadow:0 0 10px #00ccff; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.header-title { font-size:15px; font-weight:700; color:#e0f0ff; letter-spacing:1px; }
.header-sub { font-size:9px; color:#334466; letter-spacing:2px; }
.header-stats { display:flex; gap:28px; }
.stat-item { text-align:center; }
.stat-num { font-size:20px; font-weight:700; color:#00ccff; }
.stat-lbl { font-size:8px; color:#334466; letter-spacing:1px; }
.header-right { display:flex; align-items:center; gap:8px; }
.live-dot { width:6px; height:6px; border-radius:50%; background:#00e5a0; box-shadow:0 0 6px #00e5a0; animation:pulse 1.5s infinite; }
.header-time { font-size:11px; color:#334466; }
.screen-body { flex:1; display:flex; min-height:0; }
.side-panel { width:260px; flex-shrink:0; padding:14px; overflow-y:auto; }
.left-panel { border-right:1px solid rgba(0,180,255,.08); background:rgba(0,4,16,.5); }
.right-panel { border-left:1px solid rgba(0,180,255,.08); background:rgba(0,4,16,.5); }
.agent-side { width:340px; display:flex; flex-direction:column; gap:10px; transition:width .24s ease,padding .24s ease; }
.agent-side.chat-mode { width:min(520px,38vw); overflow:hidden; }
.agent-tabs { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; padding:4px; border:1px solid rgba(0,180,255,.12); border-radius:16px; background:rgba(0,10,28,.56); }
.agent-tabs button { border:0; border-radius:12px; background:transparent; color:#536984; font-size:10px; letter-spacing:1px; padding:7px 4px; cursor:pointer; }
.agent-tabs button.active { color:#06101c; background:linear-gradient(135deg,#00ccff,#00e5a0); box-shadow:0 0 18px rgba(0,204,255,.22); font-weight:700; }
.builtin-ai-strip { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 10px; border:1px solid rgba(0,204,255,.16); border-radius:8px; background:linear-gradient(135deg,rgba(0,80,150,.18),rgba(0,20,40,.66)); }
.builtin-ai-strip div { display:flex; align-items:center; gap:7px; min-width:0; }
.builtin-ai-strip strong { font-size:10px; color:#bfeeff; letter-spacing:.5px; }
.ai-dot { width:7px; height:7px; border-radius:50%; background:#00e5a0; box-shadow:0 0 9px rgba(0,229,160,.8); flex-shrink:0; }
.login-chip { border:1px solid rgba(255,208,96,.35); background:rgba(255,208,96,.08); color:#ffd060; border-radius:14px; font-size:9px; padding:4px 8px; cursor:pointer; white-space:nowrap; }
.overview-actions,.qa-actions,.starter-actions { display:flex; gap:7px; flex-wrap:wrap; }
.agent-action,.starter-btn,.modal-ai-btn { border:1px solid rgba(0,204,255,.24); background:rgba(0,95,135,.18); color:#c8f4ff; border-radius:16px; padding:7px 11px; font-size:10px; cursor:pointer; transition:all .16s; }
.agent-action:hover,.starter-btn:hover,.modal-ai-btn:hover { border-color:rgba(0,229,160,.55); background:rgba(0,150,170,.22); color:#fff; }
.agent-action:disabled,.starter-btn:disabled,.modal-ai-btn:disabled { opacity:.38; cursor:not-allowed; }
.agent-action.ghost { border-color:rgba(110,140,175,.18); background:rgba(40,60,80,.18); color:#7b91a8; }
.qa-panel,.evidence-panel { display:flex; flex-direction:column; gap:10px; min-height:0; }
.chatgpt-panel { flex:1; min-height:0; gap:10px; }
.chat-header { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:10px 4px 2px; }
.chat-kicker { color:#00ccff; font-size:9px; letter-spacing:2px; text-transform:uppercase; }
.chat-title { color:#e7f4ff; font-size:18px; font-weight:800; letter-spacing:.5px; margin-top:3px; }
.chat-clear { border:1px solid rgba(110,140,175,.18); background:rgba(40,60,80,.18); color:#7b91a8; border-radius:16px; padding:6px 10px; font-size:10px; cursor:pointer; }
.chat-clear:hover:not(:disabled) { color:#dcefff; border-color:rgba(0,204,255,.34); }
.chat-clear:disabled { opacity:.35; cursor:not-allowed; }
.chat-scope-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; padding:8px; border:1px solid rgba(0,204,255,.13); border-radius:14px; background:rgba(0,15,40,.42); }
.chat-scope-grid div { min-width:0; border-radius:10px; padding:7px; background:rgba(0,10,28,.55); }
.chat-scope-grid span { display:block; color:#52677f; font-size:9px; letter-spacing:.8px; margin-bottom:5px; }
.chat-scope-grid b { display:block; color:#d7e9fa; font-size:10px; line-height:1.35; word-break:break-word; }
.chat-thread { flex:1; min-height:240px; overflow:auto; display:flex; flex-direction:column; gap:14px; padding:10px 4px 2px; scroll-behavior:smooth; }
.chat-welcome { margin:auto 0; border:1px solid rgba(0,204,255,.16); border-radius:22px; padding:22px; background:
  radial-gradient(circle at 20% 0%, rgba(0,204,255,.20), transparent 38%),
  linear-gradient(145deg, rgba(2,26,54,.88), rgba(0,8,24,.72)); box-shadow:0 22px 60px rgba(0,0,0,.22); }
.welcome-orb { width:36px; height:36px; border-radius:14px; background:linear-gradient(135deg,#00ccff,#00e5a0); box-shadow:0 0 32px rgba(0,204,255,.35); margin-bottom:16px; }
.chat-welcome h3 { margin:0 0 8px; font-size:18px; color:#e8f5ff; letter-spacing:.5px; }
.chat-welcome p { margin:0; font-size:12px; line-height:1.7; color:#8ea4ba; }
.welcome-prompts { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:18px; }
.welcome-prompts button { border:1px solid rgba(0,204,255,.20); background:rgba(0,18,42,.68); color:#c8f4ff; border-radius:14px; padding:10px; text-align:left; font-size:11px; line-height:1.35; cursor:pointer; }
.welcome-prompts button:hover:not(:disabled) { border-color:rgba(0,229,160,.55); background:rgba(0,95,135,.20); }
.welcome-prompts button:disabled { opacity:.36; cursor:not-allowed; }
.chat-message-row { display:flex; gap:10px; align-items:flex-start; }
.chat-message-row.user { flex-direction:row-reverse; }
.chat-avatar { width:30px; height:30px; flex:0 0 30px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:800; border:1px solid rgba(0,204,255,.22); background:rgba(0,18,42,.8); color:#00ccff; box-shadow:0 0 18px rgba(0,204,255,.08); }
.chat-message-row.user .chat-avatar { color:#06101c; background:linear-gradient(135deg,#dcefff,#8ddfff); border:0; }
.chat-bubble { max-width:calc(100% - 44px); border:1px solid rgba(0,80,160,.16); border-radius:18px; padding:12px; background:rgba(0,15,40,.58); box-shadow:0 14px 34px rgba(0,0,0,.16); }
.chat-message-row.user .chat-bubble { background:linear-gradient(135deg,rgba(0,114,180,.28),rgba(0,58,110,.22)); border-color:rgba(0,204,255,.26); }
.chat-message-row.assistant .chat-bubble { background:rgba(2,18,42,.76); border-color:rgba(0,229,160,.16); }
.chat-meta { display:flex; justify-content:space-between; gap:12px; color:#58708a; font-size:9px; margin-bottom:8px; letter-spacing:.7px; }
.chat-content { color:#d2e4f4; font-size:12px; line-height:1.78; white-space:pre-wrap; word-break:break-word; }
.markdown-body { white-space:normal; }
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5) { margin:14px 0 8px; color:#9eefff; font-size:12px; letter-spacing:.8px; text-transform:uppercase; }
.markdown-body :deep(h3:first-child),
.markdown-body :deep(h4:first-child),
.markdown-body :deep(h5:first-child) { margin-top:0; }
.markdown-body :deep(p) { margin:8px 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin:8px 0 10px; padding-left:18px; }
.markdown-body :deep(li) { margin:6px 0; padding-left:2px; }
.markdown-body :deep(strong) { color:#ffffff; font-weight:800; }
.markdown-body :deep(code) { color:#ffd060; background:rgba(255,208,96,.10); border:1px solid rgba(255,208,96,.16); border-radius:5px; padding:1px 5px; font-family:'IBM Plex Mono','SF Mono',monospace; font-size:11px; }
.markdown-body :deep(pre) { margin:10px 0; padding:10px; overflow:auto; border:1px solid rgba(0,204,255,.16); border-radius:12px; background:rgba(0,8,22,.72); }
.markdown-body :deep(pre code) { padding:0; border:0; background:transparent; color:#cfe8ff; }
.markdown-body :deep(a) { color:#00ccff; text-decoration:none; border-bottom:1px solid rgba(0,204,255,.35); }
.markdown-body :deep(a:hover) { color:#68e7ff; border-bottom-color:#68e7ff; }
.message-sources { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.message-sources button { border:1px solid rgba(255,208,96,.20); background:rgba(255,208,96,.08); color:#ffd060; border-radius:999px; padding:4px 8px; font-size:9px; cursor:pointer; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.message-sources button:hover { border-color:rgba(255,208,96,.55); background:rgba(255,208,96,.14); }
.chat-bubble.thinking { display:flex; align-items:center; gap:5px; color:#7f9bb8; }
.chat-bubble.thinking span { width:6px; height:6px; border-radius:50%; background:#00ccff; animation:typingBlink 1s infinite ease-in-out; }
.chat-bubble.thinking span:nth-child(2) { animation-delay:.15s; }
.chat-bubble.thinking span:nth-child(3) { animation-delay:.3s; }
.chat-bubble.thinking em { margin-left:6px; font-style:normal; font-size:10px; }
@keyframes typingBlink { 0%,80%,100%{opacity:.25; transform:translateY(0)} 40%{opacity:1; transform:translateY(-2px)} }
.chat-login-box { flex-shrink:0; }
.chat-composer { display:grid; grid-template-columns:1fr auto; gap:8px; align-items:end; border:1px solid rgba(0,204,255,.20); border-radius:20px; padding:8px; background:rgba(0,10,28,.88); box-shadow:0 -18px 50px rgba(0,8,20,.30), inset 0 1px 0 rgba(255,255,255,.03); }
.chat-composer textarea { min-height:48px; max-height:128px; resize:vertical; border:0; outline:none; background:transparent; color:#e4f3ff; font-size:12px; line-height:1.6; font-family:inherit; padding:5px 4px; }
.chat-composer textarea::placeholder { color:#53677f; }
.chat-composer textarea:disabled { opacity:.55; cursor:not-allowed; }
.chat-composer button { width:58px; height:38px; border:0; border-radius:14px; cursor:pointer; color:#06101c; background:linear-gradient(135deg,#00ccff,#00e5a0); font-size:11px; font-weight:800; box-shadow:0 10px 24px rgba(0,204,255,.20); }
.chat-composer button:disabled { opacity:.38; cursor:not-allowed; filter:grayscale(.4); }
.chat-footnote { color:#485d75; font-size:9px; text-align:center; line-height:1.4; }
.qa-scope-card { display:grid; gap:6px; padding:10px; border:1px solid rgba(0,80,160,.16); border-radius:8px; background:rgba(0,15,40,.55); }
.qa-scope-card div { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; font-size:10px; }
.qa-scope-card span { color:#50657d; white-space:nowrap; }
.qa-scope-card b { color:#c8d8e8; font-weight:600; text-align:right; line-height:1.35; word-break:break-word; }
.qa-input { width:100%; min-height:92px; resize:vertical; border:1px solid rgba(0,180,255,.18); border-radius:9px; background:rgba(0,10,28,.76); color:#dcefff; outline:none; padding:10px; font-size:12px; line-height:1.6; box-sizing:border-box; }
.qa-input:focus { border-color:rgba(0,204,255,.5); box-shadow:0 0 0 3px rgba(0,204,255,.06); }
.qa-login-box { padding:11px; border:1px solid rgba(255,208,96,.22); border-radius:9px; background:rgba(120,82,10,.12); }
.qa-login-title { color:#ffd060; font-size:11px; font-weight:700; margin-bottom:5px; }
.qa-login-box p { margin:0 0 9px; color:#7f8fa3; font-size:10px; line-height:1.55; }
.qa-error { border:1px solid rgba(255,77,106,.24); background:rgba(255,77,106,.08); color:#ff8da0; border-radius:7px; padding:8px; font-size:10px; line-height:1.5; }
.qa-turns { display:flex; flex-direction:column; gap:8px; min-height:0; overflow:auto; padding-right:2px; }
.qa-empty { color:#5f7288; font-size:10px; line-height:1.6; padding:10px; border:1px dashed rgba(0,120,200,.16); border-radius:8px; background:rgba(0,15,40,.32); }
.qa-turn { border:1px solid rgba(0,80,160,.14); border-radius:9px; padding:9px; background:rgba(0,15,40,.52); }
.qa-turn.user { border-color:rgba(0,204,255,.20); background:rgba(0,75,120,.14); }
.qa-turn.assistant { border-color:rgba(0,229,160,.16); }
.qa-turn-meta { display:flex; justify-content:space-between; color:#52667f; font-size:9px; margin-bottom:6px; letter-spacing:.8px; }
.qa-turn-content { color:#c4d6e7; font-size:11px; line-height:1.65; white-space:pre-wrap; }
.qa-status { display:inline-block; margin-top:8px; border-radius:12px; padding:3px 7px; font-size:9px; }
.qa-status.answered { background:rgba(0,229,160,.10); color:#00e5a0; }
.qa-status.case_created { background:rgba(255,208,96,.10); color:#ffd060; }
.qa-status.needs_clarification { background:rgba(0,204,255,.10); color:#00ccff; }
.qa-status.insufficient_evidence { background:rgba(255,208,96,.10); color:#ffd060; }
.qa-status.error { background:rgba(255,77,106,.10); color:#ff7890; }
.qa-status.out_of_scope { background:rgba(110,140,175,.12); color:#95a8bc; }
.qa-status.blocked { background:rgba(255,77,106,.10); color:#ff8da0; }
.tool-trace { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
.tool-trace span,.case-chip { display:inline-block; border:1px solid rgba(0,204,255,.16); background:rgba(0,18,42,.55); color:#7f9bb8; border-radius:999px; padding:3px 7px; font-size:9px; }
.case-chip { margin-top:8px; color:#ffd060; border-color:rgba(255,208,96,.22); }
.qa-citation-list,.related-source-list { display:flex; flex-direction:column; gap:8px; }
.qa-citation-card,.related-source { width:100%; text-align:left; cursor:pointer; border:1px solid rgba(0,120,200,.18); border-radius:9px; background:rgba(0,15,40,.58); padding:10px; color:#b9ccdd; }
.qa-citation-card:hover,.related-source:hover { border-color:rgba(0,204,255,.45); background:rgba(0,95,135,.18); }
.citation-index { display:inline-block; font-size:8px; color:#06101c; background:#00ccff; border-radius:9px; padding:2px 6px; margin-bottom:6px; font-weight:700; }
.qa-citation-card strong { display:block; color:#e0f0ff; font-size:11px; line-height:1.4; margin-bottom:4px; }
.qa-citation-card em { display:block; color:#ffd060; font-size:9px; font-style:normal; margin-bottom:7px; }
.qa-citation-card p { margin:0; color:#7f91a5; font-size:10px; line-height:1.55; }
.related-title { margin-top:4px; }
.related-source { display:flex; gap:8px; align-items:flex-start; }
.related-source span { color:#00ccff; font-size:9px; font-family:monospace; min-width:28px; }
.related-source b { color:#9fb1c3; font-size:10px; line-height:1.4; font-weight:600; }
.panel-title { font-size:10px; color:#00ccff; letter-spacing:2px; text-transform:uppercase; margin-bottom:10px; }
.region-item { display:flex; align-items:center; gap:6px; margin-bottom:7px; font-size:11px; }
.region-name { width:60px; color:#667799; }
.region-bar-wrap { flex:1; height:3px; background:rgba(0,100,200,.15); border-radius:2px; }
.region-bar { height:100%; background:linear-gradient(90deg,#003388,#00ccff); border-radius:2px; transition:width .6s; }
.region-cnt { width:24px; text-align:right; color:#00ccff; font-size:10px; }
.top-item { display:flex; align-items:center; gap:6px; padding:5px 0; border-bottom:1px solid rgba(0,50,100,.2); font-size:11px; transition:background .15s; }
.top-item:hover { background:rgba(0,100,200,.08); padding-left:4px; }
.top-rank { width:16px; color:#223344; font-size:9px; }
.top-name { flex:1; color:#99aacc; }
.top-cnt { color:#00ccff; font-size:10px; }
.globe-wrap { flex:1; position:relative; min-width:0; }
.map-svg { width:100%; height:100%; cursor:grab; }
.map-svg:active { cursor:grabbing; }

/* 搜索 */
.search-bar { position:absolute; top:12px; left:50%; transform:translateX(-50%); z-index:10; width:260px; }
.search-input {
  width:100%; padding:8px 14px; background:rgba(0,10,30,.85);
  border:1px solid rgba(0,180,255,.25); border-radius:20px;
  color:#c8d8e8; font-size:12px; outline:none; backdrop-filter:blur(8px);
  transition:border .2s;
}
.search-input:focus { border-color:rgba(0,204,255,.6); }
.search-dropdown {
  position:absolute; top:38px; left:0; right:0;
  background:rgba(0,10,30,.95); border:1px solid rgba(0,180,255,.2);
  border-radius:6px; overflow:hidden; backdrop-filter:blur(10px);
}
.search-item { display:flex; align-items:center; gap:8px; padding:8px 12px; cursor:pointer; font-size:12px; transition:background .15s; }
.search-item:hover { background:rgba(0,100,200,.2); }
.search-code { font-family:monospace; color:#00ccff; width:28px; }
.search-name { flex:1; color:#aabbcc; }
.search-cnt { color:#334466; font-size:10px; }

/* 地图 */
:deep(.country-path) { stroke:#0a2040; stroke-width:0.4; transition:fill .2s,opacity .2s; cursor:default; }
:deep(.country-path.no-data) { fill:#061428; opacity:0.7; }
:deep(.country-path.verified) { fill:#0a4770; cursor:pointer; }
:deep(.country-path.verified:hover) { fill:#1685bc; }
:deep(.country-path.source) { fill:#143052; cursor:pointer; }
:deep(.country-path.source:hover) { fill:#23537c; }
:deep(.country-path.none) { fill:#2b3342; cursor:pointer; }
:deep(.country-path.none:hover) { fill:#46505f; }
:deep(.country-path.pending) { fill:#102033; cursor:pointer; }
:deep(.country-path.pending:hover) { fill:#203852; }
:deep(.country-path.selected) { fill:#0055aa !important; stroke:#00ccff !important; stroke-width:1.2 !important; }
:deep(.country-label) { font-size:9px; fill:#446688; pointer-events:none; text-anchor:middle; dominant-baseline:middle; }
:deep(.country-label.selected) { fill:#00ccff; }
.tooltip-text { font-size:11px; fill:#c8d8e8; }
.map-hint { position:absolute; bottom:12px; left:50%; transform:translateX(-50%); font-size:9px; color:#223344; letter-spacing:2px; pointer-events:none; display:flex; gap:8px; }
.hint-sep { color:#112233; }

/* 右侧动态 */
.change-list { display:flex; flex-direction:column; gap:6px; }
.change-item { display:flex; gap:7px; align-items:flex-start; padding:7px; background:rgba(0,15,40,.5); border-radius:3px; border:1px solid rgba(0,80,160,.1); }
.change-type { font-size:9px; padding:2px 5px; border-radius:2px; white-space:nowrap; flex-shrink:0; margin-top:1px; }
.change-type.created   { background:rgba(0,229,160,.12); color:#00e5a0; }
.change-type.updated   { background:rgba(0,204,255,.1);  color:#00ccff; }
.change-type.deprecated{ background:rgba(255,77,106,.1); color:#ff4d6a; }
.change-name { font-size:10px; color:#8899aa; line-height:1.4; }
.change-meta { font-size:9px; color:#334455; margin-top:2px; }

/* 国家详情 */
.country-detail { display:flex; flex-direction:column; gap:12px; min-height:100%; }
.country-header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.back-btn { background:none; border:1px solid rgba(0,180,255,.2); color:#446688; font-size:10px; padding:3px 8px; border-radius:12px; cursor:pointer; transition:all .15s; }
.back-btn:hover { color:#00ccff; border-color:#00ccff; }
.country-name-big { font-size:17px; font-weight:700; color:#e0f0ff; }
.country-region { font-size:10px; color:#334455; }
.country-code-tag { font-size:10px; color:#00ccff; background:rgba(0,204,255,.08); padding:2px 8px; border-radius:10px; border:1px solid rgba(0,204,255,.15); }
.loading-txt { color:#334466; font-size:12px; text-align:center; padding:30px; }
.detail-stats { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
.ds-item { background:rgba(0,15,40,.6); border:1px solid rgba(0,80,160,.12); border-radius:3px; padding:8px; text-align:center; }
.ds-num { font-size:20px; font-weight:700; }
.ds-lbl { font-size:9px; color:#334455; margin-top:1px; letter-spacing:1px; }
.coverage-card { padding:9px; border-radius:4px; border:1px solid rgba(0,80,160,.16); background:rgba(0,15,40,.55); }
.coverage-card.verified { border-color:rgba(0,204,255,.28); background:rgba(0,95,135,.12); }
.coverage-card.source { border-color:rgba(255,208,96,.24); background:rgba(140,105,20,.10); }
.coverage-card.none { border-color:rgba(160,170,185,.18); background:rgba(90,100,115,.08); }
.coverage-row { display:flex; justify-content:space-between; gap:10px; font-size:10px; margin-bottom:5px; }
.coverage-label { color:#44556a; }
.coverage-value { color:#c8d8e8; text-align:right; }
.coverage-note { font-size:10px; color:#66788f; line-height:1.5; border-top:1px solid rgba(0,80,160,.12); padding-top:6px; margin-top:6px; }
.scope-summary-card {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:6px;
  padding:8px;
  border:1px solid rgba(0,204,255,.16);
  border-radius:8px;
  background:linear-gradient(135deg,rgba(0,45,88,.28),rgba(0,12,30,.62));
}
.scope-summary-card div { display:flex; justify-content:space-between; gap:8px; padding:7px; border-radius:6px; background:rgba(0,10,28,.55); }
.scope-summary-card span { color:#60758c; font-size:9px; letter-spacing:.8px; }
.scope-summary-card b { color:#e1f4ff; font-size:12px; }
.scope-summary-card p { grid-column:1 / -1; margin:2px 1px 0; color:#7f94aa; font-size:10px; line-height:1.6; }
.section-title { font-size:9px; color:#00ccff; letter-spacing:2px; margin-bottom:6px; }
.upcoming-item { display:flex; align-items:center; gap:6px; margin-bottom:5px; font-size:10px; cursor:pointer; }
.upcoming-item:hover .upcoming-name { color:#00ccff; }
.days-badge { font-size:9px; padding:1px 5px; background:rgba(255,208,96,.12); color:#ffd060; border-radius:2px; white-space:nowrap; }
.days-badge.urgent { background:rgba(255,77,106,.12); color:#ff4d6a; }
.upcoming-name { color:#778899; }
.mini-change { display:flex; align-items:center; gap:6px; margin-bottom:4px; font-size:10px; }
.mini-type { font-size:9px; padding:1px 4px; border-radius:2px; }
.mini-type.created  { background:rgba(0,229,160,.1); color:#00e5a0; }
.mini-type.updated  { background:rgba(0,204,255,.1); color:#00ccff; }
.mini-type.deprecated{ background:rgba(255,77,106,.1); color:#ff4d6a; }
.mini-name { color:#667788; }
.priority-regimes { display:flex; flex-direction:column; gap:6px; }
.priority-regime-card {
  width:100%;
  text-align:left;
  cursor:pointer;
  padding:9px;
  border:1px solid rgba(0,204,255,.22);
  border-radius:7px;
  background:
    radial-gradient(circle at 0% 0%, rgba(0,204,255,.18), transparent 42%),
    rgba(0,15,40,.64);
  transition:border .16s, background .16s, transform .16s;
}
.priority-regime-card:hover {
  border-color:rgba(0,229,160,.45);
  background:
    radial-gradient(circle at 0% 0%, rgba(0,229,160,.18), transparent 42%),
    rgba(0,38,64,.68);
  transform:translateY(-1px);
}
.priority-regime-meta {
  display:block;
  margin-bottom:5px;
  color:#ffd060;
  font-size:9px;
  letter-spacing:.7px;
}
.priority-regime-card strong {
  display:block;
  color:#e1f4ff;
  font-size:11px;
  line-height:1.45;
}
.compliance-list { flex:0 0 auto; overflow:visible; }
.compliance-group-title { color:#758aa1; font-size:9px; letter-spacing:1.2px; margin:8px 0 4px; padding-left:2px; }
.compliance-group-title.inherited { color:#9eefff; }
.comp-item { display:flex; align-items:center; gap:4px; padding:5px 0; border-bottom:1px solid rgba(0,30,60,.3); font-size:10px; cursor:pointer; transition:background .15s,padding-left .15s; }
.comp-item.inherited { border-left:2px solid rgba(0,204,255,.22); padding-left:5px; }
.comp-item:hover { background:rgba(0,100,200,.08); padding-left:4px; }
.comp-item.inherited:hover { padding-left:8px; }
.comp-type { font-size:8px; padding:1px 4px; border-radius:2px; white-space:nowrap; flex-shrink:0; }
.comp-type.regulation   { background:rgba(0,204,255,.1); color:#00ccff; }
.comp-type.certification{ background:rgba(255,208,96,.1); color:#ffd060; }
.comp-type.standard     { background:rgba(255,140,66,.1); color:#ff8c42; }
.comp-mand { font-size:8px; padding:1px 4px; border-radius:2px; white-space:nowrap; flex-shrink:0; }
.comp-mand.mandatory { background:rgba(255,77,106,.1); color:#ff4d6a; }
.comp-mand.voluntary,.comp-mand.recommended { background:rgba(0,229,160,.07); color:#00e5a0; }
.comp-regime { font-size:8px; padding:1px 4px; border-radius:2px; white-space:nowrap; flex-shrink:0; border:1px solid rgba(110,140,175,.18); }
.comp-regime.product_regime { background:rgba(0,229,160,.08); color:#00e5a0; border-color:rgba(0,229,160,.22); }
.comp-regime.general_cyber_law { background:rgba(110,140,175,.08); color:#95a8bc; }
.comp-scope { font-size:8px; padding:1px 4px; border-radius:2px; white-space:nowrap; flex-shrink:0; color:#9eefff; background:rgba(0,204,255,.08); border:1px solid rgba(0,204,255,.18); }
.comp-scope.local { color:#95a8bc; background:rgba(110,140,175,.08); border-color:rgba(110,140,175,.16); }
.comp-scope.inherited { color:#06101c; background:linear-gradient(135deg,#00ccff,#00e5a0); border-color:transparent; font-weight:700; }
.comp-name { color:#778899; line-height:1.3; }
.empty-list { font-size:10px; color:#55677d; line-height:1.5; padding:8px 0; }
.source-list { display:flex; flex-direction:column; gap:5px; padding-bottom:20px; }
.source-item { display:flex; align-items:center; gap:6px; padding:6px; background:rgba(0,15,40,.45); border:1px solid rgba(0,80,160,.12); border-radius:3px; text-decoration:none; }
.source-item:hover { border-color:rgba(0,204,255,.35); background:rgba(0,100,200,.10); }
.source-type { font-size:8px; color:#ffd060; background:rgba(255,208,96,.08); padding:1px 4px; border-radius:2px; white-space:nowrap; }
.source-scope { font-size:8px; color:#9eefff; background:rgba(0,204,255,.08); border:1px solid rgba(0,204,255,.16); padding:1px 4px; border-radius:2px; white-space:nowrap; }
.source-name { color:#8899aa; font-size:10px; line-height:1.3; }
.detail-modal-mask { position:fixed; inset:0; z-index:50; background:rgba(0,5,15,.72); backdrop-filter:blur(8px); display:flex; align-items:center; justify-content:center; padding:24px; }
.detail-modal { width:min(760px,92vw); max-height:82vh; overflow:auto; position:relative; border:1px solid rgba(0,204,255,.22); border-radius:10px; background:linear-gradient(145deg,rgba(3,15,36,.98),rgba(2,8,18,.98)); box-shadow:0 24px 80px rgba(0,0,0,.55),0 0 40px rgba(0,150,255,.12); padding:22px; }
.modal-close { position:absolute; top:10px; right:12px; width:28px; height:28px; border-radius:50%; border:1px solid rgba(0,180,255,.22); background:rgba(0,15,40,.8); color:#89a4bd; cursor:pointer; font-size:18px; line-height:24px; }
.modal-close:hover { color:#00ccff; border-color:#00ccff; }
.modal-kicker { font-size:10px; color:#00ccff; letter-spacing:2px; text-transform:uppercase; margin-bottom:8px; padding-right:34px; }
.modal-title { font-size:20px; line-height:1.35; color:#e0f0ff; font-weight:700; margin-bottom:8px; padding-right:34px; }
.modal-original { color:#60758a; font-size:11px; line-height:1.5; margin-bottom:16px; padding-right:34px; }
.modal-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-bottom:16px; }
.modal-grid div { background:rgba(0,15,40,.55); border:1px solid rgba(0,80,160,.14); border-radius:4px; padding:9px; min-width:0; }
.modal-grid span { display:block; color:#44556a; font-size:9px; letter-spacing:1px; margin-bottom:5px; }
.modal-grid b { display:block; color:#c8d8e8; font-size:11px; font-weight:600; word-break:break-word; }
.modal-section { border-top:1px solid rgba(0,80,160,.14); padding-top:12px; margin-top:12px; }
.modal-section-title { font-size:10px; color:#00ccff; letter-spacing:2px; margin-bottom:6px; }
.modal-section p { margin:0; font-size:12px; line-height:1.7; color:#9aacbd; white-space:pre-wrap; }
.modal-section p.original-text { margin-top:8px; color:#5d7187; font-size:11px; border-left:2px solid rgba(0,120,200,.25); padding-left:8px; }
.milestone-list { display:flex; flex-direction:column; gap:8px; }
.milestone-item { display:grid; grid-template-columns:92px 1fr; gap:10px; padding:9px; border:1px solid rgba(0,204,255,.14); border-radius:7px; background:rgba(0,15,40,.48); }
.milestone-item > span { color:#ffd060; font-size:11px; font-family:'IBM Plex Mono','SF Mono',monospace; }
.milestone-item strong { display:block; color:#e0f0ff; font-size:12px; line-height:1.4; }
.milestone-item p { margin-top:4px; color:#8da2b7; font-size:11px; }
.milestone-item em { display:block; margin-top:5px; color:#5d7187; font-size:10px; font-style:normal; }
.modal-actions { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:18px; padding-top:12px; border-top:1px solid rgba(0,80,160,.14); }
.modal-actions a { color:#00ccff; text-decoration:none; border:1px solid rgba(0,204,255,.25); border-radius:16px; padding:6px 12px; font-size:11px; }
.modal-actions a:hover { background:rgba(0,204,255,.1); }
.modal-actions span { color:#55677d; font-size:10px; font-family:monospace; }
@media (max-width: 1100px) {
  .side-panel { width:230px; }
  .modal-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
