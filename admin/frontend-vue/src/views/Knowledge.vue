<template>
  <div>
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <input class="input" style="width:280px" v-model="filters.keyword" placeholder="搜索法规名称..." @input="debounceLoad" />
      <select class="select" style="width:130px" v-model="filters.country_code" @change="reload">
        <option value="">全部国家</option>
        <option v-for="c in meta.countries" :key="c.code" :value="c.code">{{ c.name_zh }} ({{ c.code }})</option>
      </select>
      <select class="select" style="width:120px" v-model="filters.entry_type" @change="reload">
        <option value="">全部类型</option>
        <option value="regulation">法规</option>
        <option value="standard">标准</option>
        <option value="certification">认证</option>
      </select>
      <select class="select" style="width:110px" v-model="filters.mandatory" @change="reload">
        <option value="">强制/自愿</option>
        <option value="mandatory">强制</option>
        <option value="voluntary">自愿</option>
      </select>
      <select class="select" style="width:120px" v-model="filters.product_code" @change="reload">
        <option value="">全部产品</option>
        <option v-for="p in meta.products" :key="p.code" :value="p.code">{{ p.name_zh }}</option>
      </select>
      <select v-if="auth.isAdmin" class="select" style="width:130px" v-model="filters.authenticity_status" @change="reload">
        <option value="">全部真实性</option>
        <option value="verified">已核验</option>
        <option value="suspicious">待复核</option>
        <option value="quarantined">已隔离</option>
      </select>
      <button v-if="auth.isAdmin" class="btn btn-primary" @click="openCreate">+ 新增条目</button>
      <button class="btn btn-outline" @click="handleExport">⬇ 导出Excel</button>
      <button v-if="auth.isAdmin" class="btn btn-outline" style="color:var(--yellow);border-color:rgba(255,208,96,.4)" @click="showReview=true">🔍 人工抽查</button>
      <span style="margin-left:auto;font-size:12px;color:var(--text3)">共 {{ total }} 条</span>
    </div>

    <!-- 表格 -->
    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <SortableHeader label="法规/认证名称" field="name" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" :thStyle="{width:'320px'}" />
              <SortableHeader label="类型" field="entry_type" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <SortableHeader label="强制性" field="mandatory" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <SortableHeader label="国家" field="country_code" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <th>真实性</th>
              <th>证据风险</th>
              <SortableHeader label="生效日期" field="effective_date" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <SortableHeader label="状态" field="status" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <th>证据</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!items.length"><td colspan="10" class="empty">暂无数据</td></tr>
            <tr v-for="row in items" :key="row.id" @click="openDetail(row)" style="cursor:pointer">
              <td>
                <div style="font-size:12px;font-weight:500;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="row.name">
                  {{ row.name }}
                </div>
                <div style="font-size:11px;color:var(--text3);margin-top:2px">{{ row.issuing_body }}</div>
              </td>
              <td><span :class="['badge', `badge-${row.entry_type}`]">{{ typeLabel[row.entry_type] }}</span></td>
              <td><span :class="['badge', `badge-${row.mandatory}`]">{{ mandatoryLabel[row.mandatory] }}</span></td>
              <td><span class="tag">{{ row.country_code }}</span></td>
              <td>
                <span
                  :class="['badge', row.authenticity_status === 'verified' ? 'badge-active' : row.authenticity_status === 'quarantined' ? 'badge-deprecated' : 'badge-certification']"
                >
                  {{ authenticityLabel(row.authenticity_status) }}
                </span>
              </td>
              <td>
                <span
                  :style="{color: (row.authenticity_risk_score ?? 0) >= 80 ? 'var(--red)' : (row.authenticity_risk_score ?? 0) >= 40 ? 'var(--yellow)' : 'var(--green)', fontFamily:'var(--mono)', fontSize:'12px'}"
                >
                  {{ row.authenticity_risk_score ?? '—' }}
                </span>
              </td>
              <td style="font-family:var(--mono);font-size:12px;white-space:nowrap">
                <span v-if="row.effective_date" :style="{color: getDaysColor(row.effective_date)}">{{ row.effective_date }}</span>
                <span v-else style="color:var(--text3)">—</span>
              </td>
              <td><span :class="['badge', `badge-${row.status}`]">{{ statusLabel[row.status] }}</span></td>
              <td>
                <span v-if="row.source_document_id || row.source_artifact_id" style="color:var(--green);font-size:11px">📄 已挂证据</span>
                <span v-else-if="row.official_url" style="color:var(--yellow);font-size:11px">🔗 仅官方链接</span>
                <span v-else style="color:var(--text3);font-size:11px">—</span>
              </td>
              <td>
                <div v-if="auth.isAdmin" style="display:flex;gap:6px">
                  <button class="btn btn-sm btn-outline" @click.stop="openEdit(row)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click.stop="handleDelete(row)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <span class="page-info">{{ total }} 条 / 第 {{ page }}/{{ totalPages || 1 }} 页</span>
      <button class="btn btn-sm btn-outline" :disabled="page<=1" @click="page--;load()">上一页</button>
      <button class="btn btn-sm btn-outline" :disabled="page>=totalPages" @click="page++;load()">下一页</button>
    </div>

    <!-- 人工抽查弹窗 -->
    <div v-if="showReview && auth.isAdmin" class="modal-overlay" @click.self="showReview=false">
      <div class="modal" style="width:900px">
        <div class="modal-header">
          <span>🔍 人工抽查 — 待核实条目（置信度低或AI生成）</span>
          <button class="close-btn" @click="showReview=false">×</button>
        </div>
        <div style="padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center">
          <select class="select" style="width:220px" v-model="reviewBucket" @change="loadReview">
            <option value="">全部待复核</option>
            <option value="official_url_missing">缺少官方链接</option>
            <option value="domain_mismatch">官方域名不匹配</option>
            <option value="404_like">404 / 门户回退</option>
            <option value="local_adoption_unverified">本地采纳未证实</option>
          </select>
          <span style="font-size:12px;color:var(--text3)">“已核验”只能通过人工补源和官方证据闭环完成</span>
        </div>
        <div class="modal-body" style="padding:0">
          <div v-if="reviewLoading" class="loading">加载中...</div>
          <div v-else-if="!reviewItems.length" class="empty">🎉 暂无待核实条目</div>
          <div v-else class="table-wrap">
            <table>
              <thead><tr><th style="width:300px">条目名称</th><th>国家</th><th>类型</th><th>生效日期</th><th>置信度</th><th>数据来源</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="item in reviewItems" :key="item.id"
                  :style="{background: item.confidence_score < 60 ? 'rgba(255,77,106,.05)' : item.confidence_score < 80 ? 'rgba(255,208,96,.05)' : 'transparent'}">
                  <td>
                    <div style="font-size:12px;font-weight:500;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.name">{{ item.name }}</div>
                    <div style="font-size:11px;color:var(--text3)">{{ item.issuing_body }}</div>
                  </td>
                  <td><span class="tag">{{ item.country_code }}</span></td>
                  <td><span :class="['badge',`badge-${item.entry_type}`]">{{ {regulation:'法规',standard:'标准',certification:'认证'}[item.entry_type] }}</span></td>
                  <td style="font-family:var(--mono);font-size:12px">{{ item.effective_date || '—' }}</td>
                  <td>
                    <span :style="{color: item.confidence_score>=80?'var(--green)':item.confidence_score>=60?'var(--yellow)':'var(--red)', fontFamily:'var(--mono)', fontSize:13, fontWeight:600}">
                      {{ item.confidence_score ?? '—' }}
                    </span>
                  </td>
                  <td style="font-size:11px;color:var(--text3);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ item.data_source }}</td>
                  <td>
                    <div style="display:flex;gap:6px">
                      <button class="btn btn-sm btn-outline" style="color:var(--yellow);border-color:rgba(255,208,96,.4)" @click="openReviewAction(item, 'suspicious')">标为待复核</button>
                      <button class="btn btn-sm btn-danger" @click="openReviewAction(item, 'quarantined')">隔离</button>
                      <button class="btn btn-sm btn-primary" @click="openManualSource(item);showReview=false">人工补源</button>
                      <button class="btn btn-sm btn-outline" @click="openEdit(item);showReview=false">编辑</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <span style="font-size:12px;color:var(--text3)">共 {{ reviewItems.length }} 条待核实</span>
          <button class="btn btn-outline" @click="showReview=false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 详情弹窗（只读） -->
    <div v-if="showDetail && detailRow" class="modal-overlay" @click.self="showDetail=false">
      <div class="modal" style="width:780px">
        <div class="modal-header">
          <span>📋 {{ detailRow.name }}</span>
          <button class="close-btn" @click="showDetail=false">×</button>
        </div>
        <div v-if="detailLoading" class="loading">详情加载中...</div>
        <div v-else class="modal-body" style="display:grid;gap:14px">
          <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px">
            <div style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
              <div class="form-label">真实性状态</div>
              <div style="margin-top:6px">
                <span :class="['badge', detailRow.authenticity_status === 'verified' ? 'badge-active' : detailRow.authenticity_status === 'quarantined' ? 'badge-deprecated' : 'badge-certification']">
                  {{ authenticityLabel(detailRow.authenticity_status) }}
                </span>
              </div>
            </div>
            <div style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
              <div class="form-label">证据风险分</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono)" :style="{color: (detailRow.authenticity_risk_score ?? 0)>=80?'var(--red)':(detailRow.authenticity_risk_score ?? 0)>=40?'var(--yellow)':'var(--green)'}">
                {{ detailRow.authenticity_risk_score ?? '—' }}
              </div>
            </div>
            <div style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
              <div class="form-label">证据工件</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono);color:var(--accent)">
                {{ detailRow.source_artifacts?.length || 0 }}
              </div>
            </div>
            <div style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
              <div class="form-label">审核事件</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono);color:var(--accent)">
                {{ detailRow.evidence_events?.length || 0 }}
              </div>
            </div>
          </div>
          <div class="form-row">
            <div><span class="form-label">国家/地区</span><div>{{ detailRow.country_name }} ({{ detailRow.country_code }})</div></div>
            <div><span class="form-label">类型</span><div>{{ {regulation:'法规',standard:'标准',certification:'认证'}[detailRow.entry_type] }}</div></div>
            <div><span class="form-label">强制性</span><div>{{ {mandatory:'强制',voluntary:'自愿',recommended:'推荐'}[detailRow.mandatory] }}</div></div>
          </div>
          <div class="form-row">
            <div><span class="form-label">生效日期</span><div style="font-family:var(--mono)">{{ detailRow.effective_date || '—' }}</div></div>
            <div><span class="form-label">过渡期截止</span><div style="font-family:var(--mono)">{{ detailRow.transition_end_date || '—' }}</div></div>
            <div><span class="form-label">证据风险分</span>
              <div style="display:flex;align-items:center;gap:8px">
                <span :style="{color: (detailRow.authenticity_risk_score ?? 0)>=80?'var(--red)':(detailRow.authenticity_risk_score ?? 0)>=40?'var(--yellow)':'var(--green)', fontWeight:600}">
                  {{ detailRow.authenticity_risk_score ?? '—' }}
                </span>
                <span :class="['badge', detailRow.authenticity_status === 'verified' ? 'badge-active' : detailRow.authenticity_status === 'quarantined' ? 'badge-deprecated' : 'badge-certification']">
                  {{ authenticityLabel(detailRow.authenticity_status) }}
                </span>
              </div>
            </div>
          </div>
          <div><span class="form-label">发布机构</span><div>{{ detailRow.issuing_body || '—' }}</div></div>
          <div><span class="form-label">适用产品</span>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
              <span v-for="p in (detailRow.applicable_products||[])" :key="p" class="tag">{{ p }}</span>
            </div>
          </div>
          <div><span class="form-label">适用范围</span><div style="font-size:13px;color:var(--text2)">{{ detailRow.scope_description || '—' }}</div></div>
          <div v-if="detailRow.requirements?.key_requirements?.length">
            <span class="form-label">核心要求</span>
            <ul style="margin-top:6px;padding-left:16px;font-size:13px;color:var(--text2)">
              <li v-for="(r,i) in detailRow.requirements.key_requirements" :key="i" style="margin-bottom:4px">{{ r }}</li>
            </ul>
          </div>
          <div><span class="form-label">官方链接</span>
            <div><a v-if="detailRow.official_url" :href="detailRow.official_url" target="_blank" style="color:var(--accent);font-size:13px">{{ detailRow.official_url }}</a><span v-else>—</span></div>
          </div>
          <div class="form-row">
            <div><span class="form-label">真实性状态</span><div>{{ authenticityLabel(detailRow.authenticity_status) }}</div></div>
            <div><span class="form-label">原文抓取</span><div>{{ downloadStatusLabel(detailRow.review_case?.source_download_status || detailRow.source_download_status) }}</div></div>
            <div><span class="form-label">证据文档</span><div>{{ detailRow.source_document_id || detailRow.document_id || '—' }}</div></div>
          </div>
          <div v-if="detailRow.review_case">
            <span class="form-label">人工审核结论</span>
            <div style="font-size:13px;color:var(--text2);line-height:1.8">{{ detailRow.review_case.evidence_note || '—' }}</div>
            <div v-if="detailRow.review_case.reasons?.length" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">
              <span v-for="reason in detailRow.review_case.reasons" :key="reason" class="tag">{{ reason }}</span>
            </div>
          </div>
          <div v-if="detailRow.source_artifact_url"><span class="form-label">原文工件</span>
            <div><a :href="detailRow.source_artifact_url" target="_blank" style="color:var(--accent);font-size:13px">{{ detailRow.source_artifact_url }}</a></div>
          </div>
          <div v-if="detailRow.source_artifacts?.length">
            <span class="form-label">证据工件</span>
            <div style="display:grid;gap:8px">
              <div v-for="artifact in detailRow.source_artifacts" :key="artifact.id" style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
                <div style="display:flex;justify-content:space-between;gap:12px;font-size:12px">
                  <span style="color:var(--accent)" :title="artifact.artifact_type">{{ artifactTypeLabel(artifact.artifact_type) }}</span>
                  <span style="color:var(--text3)" :title="artifact.download_status">{{ downloadStatusLabel(artifact.download_status) }}</span>
                </div>
                <div style="margin-top:6px">
                  <a v-if="artifact.artifact_url" :href="artifact.artifact_url" target="_blank" style="color:var(--text2);font-size:12px;word-break:break-all">{{ artifact.artifact_url }}</a>
                  <div v-else style="color:var(--text3);font-size:12px">暂无可打开工件</div>
                </div>
                <div v-if="artifact.official_url" style="margin-top:6px">
                  <a :href="artifact.official_url" target="_blank" style="color:var(--accent);font-size:12px;word-break:break-all">{{ artifact.official_url }}</a>
                </div>
                <div v-if="artifact.download_error" style="margin-top:6px;color:var(--red);font-size:12px">
                  {{ artifact.download_error }}
                </div>
              </div>
            </div>
          </div>
          <div v-if="detailRow.evidence_events?.length">
            <span class="form-label">审核事件</span>
            <div style="display:grid;gap:8px">
              <div v-for="event in detailRow.evidence_events.slice(0, 6)" :key="event.id" style="padding:10px 12px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
                <div style="display:flex;justify-content:space-between;gap:12px;font-size:12px">
                  <span style="color:var(--yellow)">{{ event.event_type }}</span>
                  <span style="color:var(--text3)">{{ event.created_at }}</span>
                </div>
                <div style="margin-top:6px;color:var(--text3);font-size:12px">
                  {{ event.from_status ? authenticityLabel(event.from_status) : '—' }} → {{ event.to_status ? authenticityLabel(event.to_status) : '—' }}
                </div>
              </div>
            </div>
          </div>
          <div v-if="detailRow.remarks"><span class="form-label">备注</span><div style="font-size:12px;color:var(--text3)">{{ detailRow.remarks }}</div></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showDetail=false">关闭</button>
          <button v-if="detailRow.source_document_id || detailRow.document_id" class="btn btn-outline" @click="openDocumentWorkspace(detailRow)">查看原文</button>
          <button v-if="detailRow.source_document_id || detailRow.document_id" class="btn btn-outline" @click="openResearchWorkspace(detailRow)">去问答</button>
          <button v-if="auth.isAdmin" class="btn btn-outline" style="color:var(--yellow);border-color:rgba(255,208,96,.4)" @click="openManualSource(detailRow)">人工补源</button>
          <button v-if="auth.isAdmin" class="btn btn-primary" @click="openEdit(detailRow);showDetail=false">编辑</button>
        </div>
      </div>
    </div>

    <div v-if="showManualSource && manualSourceRow && auth.isAdmin" class="modal-overlay" @click.self="showManualSource=false">
      <div class="modal" style="width:640px">
        <div class="modal-header">
          <span>🔗 人工补源 · {{ manualSourceRow.name }}</span>
          <button class="close-btn" @click="showManualSource=false">×</button>
        </div>
        <div class="modal-body" style="display:grid;gap:12px">
          <div class="form-group">
            <label class="form-label">官方正文页 *</label>
            <input class="input" v-model="manualSourceForm.official_url" placeholder="https://官方域名/..." />
          </div>
          <div class="form-group">
            <label class="form-label">官方 PDF/工件链接</label>
            <input class="input" v-model="manualSourceForm.artifact_url" placeholder="可选，优先填官方 PDF" />
          </div>
          <div class="form-group">
            <label class="form-label">本机上传源文件</label>
            <input class="input" type="file" accept=".pdf,.html,.htm,text/html,application/pdf" @change="handleManualSourceFileChange" />
            <div style="margin-top:6px;font-size:12px;color:var(--text3)">
              {{ manualSourceFile ? `已选择：${manualSourceFile.name}` : '服务器抓不到时，可直接上传本机已确认的官方 PDF 或正文页 HTML。' }}
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">证据备注 *</label>
            <textarea class="textarea" v-model="manualSourceForm.evidence_note" rows="3" placeholder="如：人工联网确认该链接为官方正文页" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showManualSource=false">取消</button>
          <button class="btn btn-primary" :disabled="manualSourceSaving" @click="handleManualSource">
            {{ manualSourceSaving ? '提交中...' : '确认补源并核实' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showManualReview && manualReviewRow && auth.isAdmin" class="modal-overlay" @click.self="showManualReview=false">
      <div class="modal" style="width:680px">
        <div class="modal-header">
          <span>🧾 人工审核 · {{ manualReviewRow.name }}</span>
          <button class="close-btn" @click="showManualReview=false">×</button>
        </div>
        <div class="modal-body" style="display:grid;gap:12px">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">审核结论</label>
              <select class="select" v-model="manualReviewForm.authenticity_status">
                <option value="suspicious">待复核</option>
                <option value="quarantined">已隔离</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">证据风险分</label>
              <input class="input" type="number" min="0" max="100" v-model.number="manualReviewForm.risk_score" />
            </div>
            <div class="form-group">
              <label class="form-label">原文抓取状态</label>
              <select class="select" v-model="manualReviewForm.source_download_status">
                <option value="">不改</option>
                <option value="pending">待抓取</option>
                <option value="downloaded">已抓取</option>
                <option value="failed">抓取失败</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">原因列表（每行一个）</label>
            <textarea class="textarea" v-model="manualReviewForm.reasons_text" rows="4" placeholder="官方域名不匹配&#10;官方页面返回 404" />
          </div>
          <div class="form-group">
            <label class="form-label">证据备注 *</label>
            <textarea class="textarea" v-model="manualReviewForm.evidence_note" rows="4" placeholder="访问日期 + 官方来源 + 关键结论 + 为什么不能更进一步" />
          </div>
          <div class="form-group">
            <label class="form-label">抓取错误备注</label>
            <textarea class="textarea" v-model="manualReviewForm.source_download_error" rows="3" placeholder="如：目标页面返回 404" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showManualReview=false">取消</button>
          <button class="btn btn-primary" :disabled="manualReviewSaving" @click="handleManualReview">
            {{ manualReviewSaving ? '提交中...' : '确认写回人工结论' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <div v-if="showModal && auth.isAdmin" class="modal-overlay" @click.self="showModal=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editingId ? '编辑条目' : '新增条目' }}</span>
          <button class="close-btn" @click="showModal=false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group" style="grid-column:1/-1">
              <label class="form-label">法规/认证名称 *</label>
              <input class="input" v-model="form.name" placeholder="完整英文名称" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">本地语言名称</label>
              <input class="input" v-model="form.name_local" />
            </div>
            <div class="form-group">
              <label class="form-label">国家/地区 *</label>
              <select class="select" v-model="form.country_code">
                <option v-for="c in meta.countries" :key="c.code" :value="c.code">{{ c.name_zh }} ({{ c.code }})</option>
              </select>
            </div>
          </div>
          <div class="form-row-3">
            <div class="form-group">
              <label class="form-label">条目类型</label>
              <select class="select" v-model="form.entry_type">
                <option value="regulation">法规</option>
                <option value="standard">标准</option>
                <option value="certification">认证</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">强制性</label>
              <select class="select" v-model="form.mandatory">
                <option value="mandatory">强制</option>
                <option value="voluntary">自愿</option>
                <option value="recommended">推荐</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">状态</label>
              <select class="select" v-model="form.status">
                <option value="active">有效</option>
                <option value="deprecated">废止</option>
                <option value="draft">草案</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">生效日期</label>
              <input class="input" type="date" v-model="form.effective_date" />
            </div>
            <div class="form-group">
              <label class="form-label">过渡期截止</label>
              <input class="input" type="date" v-model="form.transition_end_date" />
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">认证机构</label>
            <input class="input" v-model="form.issuing_body" />
          </div>
          <div class="form-group">
            <label class="form-label">适用产品</label>
            <div class="tag-selector">
              <span v-for="p in meta.products" :key="p.code"
                :class="['tag-option', {active: form.applicable_products?.includes(p.code)}]"
                @click="toggleProduct(p.code)">{{ p.name_zh }}</span>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">官方链接</label>
            <input class="input" v-model="form.official_url" placeholder="https://..." />
          </div>
          <div class="form-group">
            <label class="form-label">备注</label>
            <textarea class="textarea" v-model="form.remarks" rows="3" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showModal=false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import SortableHeader from '@/components/SortableHeader.vue'
import { complianceApi, api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { artifactTypeLabel, authenticityLabel, downloadStatusLabel } from '@/utils/labels'

const toast = inject('toast')
const router = useRouter()
const auth = useAuthStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const saving = ref(false)
const showModal = ref(false)
const editingId = ref(null)
const meta = ref({ countries: [], products: [] })
const PAGE_SIZE = 20

const filters = reactive({ keyword: '', country_code: '', entry_type: '', mandatory: '', product_code: '', authenticity_status: '' })
const sortField = ref('updated_at')
const sortOrder = ref('desc')
function handleSort(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'asc'
  }
  reload()
}
const showReview = ref(false)
const showDetail = ref(false)
const detailRow = ref(null)
const detailLoading = ref(false)
const showManualSource = ref(false)
const manualSourceRow = ref(null)
const manualSourceSaving = ref(false)
const manualSourceForm = ref({ official_url: '', artifact_url: '', evidence_note: '' })
const manualSourceFile = ref(null)
const showManualReview = ref(false)
const manualReviewRow = ref(null)
const manualReviewSaving = ref(false)
const manualReviewForm = ref(defaultReviewForm())
const reviewItems = ref([])
const reviewLoading = ref(false)
const reviewBucket = ref('')
const form = ref(defaultForm())

const typeLabel = { regulation: '法规', standard: '标准', certification: '认证' }
const mandatoryLabel = { mandatory: '强制', voluntary: '自愿', recommended: '推荐' }
const statusLabel = { active: '有效', deprecated: '废止', draft: '草案', superseded: '替代' }
const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))

function defaultForm() {
  return { name:'', name_local:'', country_code:'EU', entry_type:'regulation', mandatory:'mandatory',
    status:'active', issuing_body:'', effective_date:'', transition_end_date:'',
    official_url:'', remarks:'', applicable_products:[] }
}

function defaultReviewForm(status = 'suspicious') {
  return {
    authenticity_status: status,
    risk_score: status === 'quarantined' ? 95 : 70,
    reasons_text: '',
    evidence_note: '',
    source_download_status: 'failed',
    source_download_error: '',
  }
}

function getDaysColor(dateStr) {
  if (!dateStr) return 'var(--text3)'
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000)
  if (days < 0) return 'var(--text3)'
  if (days <= 30) return 'var(--red)'
  if (days <= 90) return 'var(--yellow)'
  return 'var(--text2)'
}

let debounceTimer
function debounceLoad() { clearTimeout(debounceTimer); debounceTimer = setTimeout(reload, 400) }
function reload() { page.value = 1; load() }

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: PAGE_SIZE, sort_by: sortField.value, sort_order: sortOrder.value }
    if (filters.keyword)      params.keyword = filters.keyword
    if (filters.country_code) params.country_code = filters.country_code
    if (filters.entry_type)   params.entry_type = filters.entry_type
    if (filters.mandatory)    params.mandatory = filters.mandatory
    if (filters.product_code) params.product_code = filters.product_code
    if (filters.authenticity_status) params.authenticity_status = filters.authenticity_status
    const data = await complianceApi.list(params)
    items.value = data.items
    total.value = data.total
  } catch(e) { toast(String(e), 'error') }
  loading.value = false
}

async function loadMeta() {
  try { const d = await complianceApi.meta(); meta.value = d } catch(e) {}
}

function openCreate() { editingId.value = null; form.value = defaultForm(); showModal.value = true }
function openEdit(row) {
  editingId.value = row.id
  form.value = { ...defaultForm(), ...row,
    effective_date: row.effective_date?.slice(0,10) || '',
    transition_end_date: row.transition_end_date?.slice(0,10) || '',
    applicable_products: row.applicable_products || [],
  }
  showModal.value = true
}

function toggleProduct(code) {
  const arr = form.value.applicable_products || []
  form.value.applicable_products = arr.includes(code) ? arr.filter(x=>x!==code) : [...arr, code]
}

async function handleSave() {
  if (!form.value.name) { toast('请填写法规名称', 'error'); return }
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.effective_date) delete payload.effective_date
    if (!payload.transition_end_date) delete payload.transition_end_date
    if (editingId.value) { await complianceApi.update(editingId.value, payload); toast('更新成功') }
    else { await complianceApi.create(payload); toast('创建成功') }
    showModal.value = false; load()
  } catch(e) { toast(String(e), 'error') }
  saving.value = false
}

async function handleDelete(row) {
  if (!confirm(`确认删除：${row.name}？`)) return
  try { await complianceApi.remove(row.id); toast('已删除'); load() }
  catch(e) { toast(String(e), 'error') }
}

async function handleExport() {
  const params = new URLSearchParams()
  if (filters.keyword)      params.set('keyword', filters.keyword)
  if (filters.country_code) params.set('country_code', filters.country_code)
  if (filters.entry_type)   params.set('entry_type', filters.entry_type)
  if (filters.mandatory)    params.set('mandatory', filters.mandatory)
  if (filters.product_code) params.set('product_code', filters.product_code)
  params.set('status', 'active')
  const token = localStorage.getItem('token')
  const url = `/api/compliance/export/excel?${params}`
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!resp.ok) { toast('导出失败', 'error'); return }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `compliance_${new Date().toISOString().slice(0,10)}.xlsx`
  a.click()
  toast('导出成功')
}

async function openDetail(row) {
  showDetail.value = true
  detailLoading.value = true
  detailRow.value = { ...row, source_artifacts: [], evidence_events: [] }
  try {
    const [detail, evidence] = await Promise.all([
      complianceApi.get(row.id),
      complianceApi.evidence(row.id),
    ])
    detailRow.value = {
      ...detail,
      review_case: evidence?.review_case || detail.review_case || null,
      source_artifacts: detail.source_artifacts || evidence?.artifacts || [],
      evidence_events: detail.evidence_events || evidence?.events || [],
    }
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    detailLoading.value = false
  }
}

function openManualSource(row) {
  manualSourceRow.value = row
  manualSourceForm.value = {
    official_url: row.official_url || '',
    artifact_url: row.source_artifact_url || '',
    evidence_note: row.authenticity_evidence || '',
  }
  manualSourceFile.value = null
  showManualSource.value = true
}

function handleManualSourceFileChange(event) {
  const [file] = event?.target?.files || []
  manualSourceFile.value = file || null
}

function openReviewAction(row, status = 'suspicious') {
  manualReviewRow.value = row
  manualReviewForm.value = {
    ...defaultReviewForm(status),
    evidence_note: row.authenticity_evidence || '',
    source_download_status: row.source_download_status || 'failed',
    source_download_error: row.source_download_error || '',
    reasons_text: Array.isArray(row.authenticity_reasons) ? row.authenticity_reasons.join('\n') : '',
  }
  showManualReview.value = true
}

async function handleManualSource() {
  if (!manualSourceRow.value) return
  if (!manualSourceForm.value.official_url || !manualSourceForm.value.evidence_note) {
    toast('请填写官方链接和证据备注', 'error')
    return
  }
  manualSourceSaving.value = true
  try {
    if (manualSourceFile.value) {
      const formData = new FormData()
      formData.append('official_url', manualSourceForm.value.official_url)
      formData.append('evidence_note', manualSourceForm.value.evidence_note)
      formData.append('auto_parse', 'true')
      formData.append('file', manualSourceFile.value)
      await complianceApi.manualSourceUpload(manualSourceRow.value.id, formData)
    } else {
      await complianceApi.manualSource(manualSourceRow.value.id, {
        official_url: manualSourceForm.value.official_url,
        artifact_url: manualSourceForm.value.artifact_url || null,
        evidence_note: manualSourceForm.value.evidence_note,
      })
    }
    toast('人工补源成功，条目已标记为已核验')
    showManualSource.value = false
    manualSourceFile.value = null
    showDetail.value = false
    load()
  } catch (e) {
    toast(String(e), 'error')
  }
  manualSourceSaving.value = false
}

async function loadReview() {
  reviewLoading.value = true
  try {
    const params = { limit: 100 }
    if (reviewBucket.value) params.review_bucket = reviewBucket.value
    const data = await api.get('/compliance/review/pending', { params })
    reviewItems.value = data.items || []
  } catch(e) { toast(String(e), 'error') }
  reviewLoading.value = false
}

async function handleManualReview() {
  if (!manualReviewRow.value) return
  const reasons = manualReviewForm.value.reasons_text
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
  if (!reasons.length || !manualReviewForm.value.evidence_note.trim()) {
    toast('请填写原因列表和证据备注', 'error')
    return
  }
  manualReviewSaving.value = true
  try {
    await complianceApi.review(manualReviewRow.value.id, {
      authenticity_status: manualReviewForm.value.authenticity_status,
      risk_score: manualReviewForm.value.risk_score,
      reasons,
      evidence_note: manualReviewForm.value.evidence_note,
      source_download_status: manualReviewForm.value.source_download_status || null,
      source_download_error: manualReviewForm.value.source_download_error || null,
    })
    toast('人工审核结果已写回')
    showManualReview.value = false
    if (showReview.value) await loadReview()
    load()
  } catch(e) { toast(String(e), 'error') }
  manualReviewSaving.value = false
}

function openDocumentWorkspace(row) {
  const docId = row.source_document_id || row.document_id
  if (!docId) return
  showDetail.value = false
  router.push({ path: '/documents' })
  toast(`文档 ${docId} 已可在“法规原文”页查看`, 'info')
}

function openResearchWorkspace(row) {
  const docId = row.source_document_id || row.document_id
  showDetail.value = false
  router.push({
    path: '/research',
    query: {
      document: docId || '',
      country: row.country_code || '',
      question: `${row.name} 的核心合规要求有哪些？`,
    },
  })
}

watch(showReview, (val) => { if (val) loadReview() })

onMounted(() => { loadMeta(); load() })
</script>
