<template>
  <main class="shell">
    <aside class="sidebar">
      <div>
        <p class="eyebrow">Info Gap Radar</p>
        <h1>信息差雷达</h1>
      </div>

      <nav class="filters">
        <button
          v-for="category in categories"
          :key="category"
          :class="{ active: selectedCategory === category }"
          @click="selectedCategory = category"
        >
          <span class="label">{{ category }}</span>
          <span class="count" v-if="category === '全部'">{{ items.length }}</span>
          <span class="count" v-else-if="categoryCounts[category]">{{ categoryCounts[category] }}</span>
        </button>
      </nav>

      <section class="custom-crawl">
        <label for="site-url">自定义站点</label>
        <div class="input-row">
          <input id="site-url" v-model="customUrl" placeholder="https://example.com" />
          <button @click="crawlCustom" :disabled="loading || !customUrl">抓取</button>
        </div>
        <ul class="site-list" v-if="customSites.length">
          <li v-for="site in customSites" :key="site.id" :title="site.url">
            <button class="site-name" @click="recrawlSite(site)">{{ site.title || site.url }}</button>
            <button class="site-del" @click="removeSite(site)" title="删除">×</button>
          </li>
        </ul>
      </section>

      <button class="gap-signal" @click="openInsightFromSidebar">
        <span class="gap-label">信息差信号</span>
        <span class="gap-badge" :class="{ off: !gapSummary.candidates }">
          {{ gapSummary.candidates || 0 }}
        </span>
      </button>

      <section class="ai-settings">
        <button class="theme-toggle" @click="toggleTheme">{{ theme === 'dark' ? '切换浅色' : '切换深色' }}</button>
        <div class="ai-status" :class="{ ok: aiConfigured }">
          {{ aiConfigured ? `AI 已配置：${settings.model || "自定义模型"}` : "AI 未配置（报告为本地模板）" }}
        </div>
        <button @click="openSettings">AI 设置</button>
      </section>

      <section class="cruise">
        <div class="cruise-head">
          <span class="cruise-title">自动巡航</span>
          <button class="switch" :class="{ on: autoCruise }" @click="toggleAutoCruise" role="switch" :aria-checked="autoCruise">
            <i></i>
          </button>
        </div>
        <p class="cruise-hint" v-if="autoCruise">
          每 {{ cruiseInterval }} 分钟自动采集；距下次 <b>{{ cruiseCountdown }}</b> 秒
        </p>
        <p class="cruise-hint" v-else>开启后雷达后台定时扫源</p>
        <div class="cruise-intervals" v-if="autoCruise">
          <button
            v-for="m in CRUISE_OPTIONS"
            :key="m"
            :class="{ active: cruiseInterval === m }"
            @click="setCruiseInterval(m)"
          >{{ m }}分</button>
        </div>
      </section>
    </aside>

    <section class="content">
      <header class="toolbar">
        <div class="toolbar-left">
          <div>
            <h2>热点雷达</h2>
            <p>{{ statusText }}</p>
          </div>
          <div class="view-switch">
            <button :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">热点列表</button>
            <button :class="{ active: viewMode === 'insight' }" @click="viewMode = 'insight'">信息差洞察</button>
          </div>
        </div>
        <div class="actions">
          <button @click="refresh('github')" :disabled="loading">GitHub</button>
          <button @click="refresh('hn')" :disabled="loading">Hacker News</button>
          <button class="primary" @click="refresh('all')" :disabled="loading">
            {{ loading ? "采集中..." : "刷新全部" }}
          </button>
        </div>
      </header>

      <div class="search-row" v-if="viewMode === 'list'">
        <input v-model="searchQuery" type="search" placeholder="搜索标题 / 摘要，支持中英文全文检索…" />
        <button v-if="searchQuery" class="ghost" @click="clearSearch">清除</button>
        <button
          class="ghost"
          :class="{ active: favoriteOnly }"
          @click="favoriteOnly = !favoriteOnly"
        >★ 只看收藏</button>
        <button class="ghost" @click="batchAnalyze" :disabled="batchLoading || !filteredItems.length">
          {{ batchLoading ? `批量分析中 ${batchProgress.done}/${batchProgress.total}` : "批量分析前 10 条" }}
        </button>
        <span class="result-count">{{ filteredItems.length }} 条</span>
      </div>

        <div class="crawl-report" v-if="lastCrawl && lastCrawl.failed.length && viewMode === 'list'">
          <span class="cr-text">
            ⚠ 采集完成：<b>{{ lastCrawl.ok }}</b> 源成功 / <b>{{ lastCrawl.failed.length }}</b> 源失败
            <template v-if="lastCrawl.prefetch">，后台预抓 {{ lastCrawl.prefetch }} 条全文</template>
          </span>
          <span class="cr-failed" :title="lastCrawl.failed.join('、')">
            {{ lastCrawl.failed.slice(0, 6).join("、") }}{{ lastCrawl.failed.length > 6 ? "…" : "" }}
          </span>
          <button class="ghost-sm" @click="lastCrawl = null">关闭</button>
        </div>

        <div class="range-row" v-if="viewMode === 'list'">
        <span>时间范围：</span>
        <button
          v-for="r in timeRanges"
          :key="r.id"
          :class="{ active: selectedRange === r.id }"
          @click="selectedRange = r.id"
        >
          {{ r.label }}
        </button>
      </div>

      <div class="workspace">
        <section class="list" v-if="viewMode === 'list'">
          <div class="list-empty" v-if="!filteredItems.length && !loading">
            <div class="list-empty-icon">📡</div>
            <h3>{{ searchQuery ? "没有匹配的热点" : "暂无热点数据" }}</h3>
            <p>{{ searchQuery ? "换个关键词试试，或清除搜索查看全部。" : "点击右上角「刷新全部」，雷达会并发扫描 50+ 信息源。" }}</p>
          </div>
          <article
            v-for="item in filteredItems"
            :key="item.id || item.url"
            :class="{ selected: selectedItem?.id === item.id, read: item.read, analyzed: item.analyzed }"
            :style="{ '--cat': CATEGORY_COLORS[item.category] || '#0f5c58' }"
            @click="selectItem(item)"
          >
            <div class="item-meta">
              <span class="cat"><i class="dot"></i>{{ item.category }}</span>
              <span class="src">{{ item.source }}</span>
              <span class="time">{{ timeAgo(item.item_date) }}</span>
              <strong v-if="item.hot_value" :title="`原始热度 ${item.hot_value} / 归一化 ${item.hot_score}`">
                {{ Math.round(item.hot_score || 0) }}
              </strong>
              <button
                class="star"
                :class="{ on: item.favorite }"
                :title="item.favorite ? '取消收藏' : '收藏'"
                @click.stop="toggleFlag(item, 'favorite')"
              >{{ item.favorite ? "★" : "☆" }}</button>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary }}</p>
          </article>
          <div class="list-more" v-if="hasMore && viewMode === 'list'">
            <button class="ghost" @click="loadItems({ append: true })" :disabled="loadingMore">
              {{ loadingMore ? "加载中…" : "加载更多" }}
            </button>
          </div>
        </section>

        <section class="report" v-if="viewMode === 'list'">
          <template v-if="selectedItem">
            <div class="report-head">
              <div>
                <p class="eyebrow">
                  {{ selectedItem.source }}
                  <i class="analyzed-tag" v-if="selectedItem.analyzed">已分析</i>
                </p>
                <h2>{{ selectedItem.title }}</h2>
              </div>
              <div class="report-actions">
                <button class="ghost" @click="toggleFlag(selectedItem, 'favorite')">
                  {{ selectedItem.favorite ? "★ 已收藏" : "☆ 收藏" }}
                </button>
                <button class="ghost" @click="hideItem(selectedItem)" title="从列表隐藏">隐藏</button>
                <button class="ghost" v-if="reportHtml" @click="exportReport">导出 MD</button>
                <button class="ghost" v-if="reportHtml" @click="printReport">打印/PDF</button>
                <button class="primary" @click="generateReport" :disabled="reportLoading">
                  {{ reportLoading ? "分析中..." : streaming ? "生成中..." : "AI 分析" }}
                </button>
              </div>
            </div>
            <a :href="selectedItem.url" target="_blank" rel="noreferrer">打开来源</a>

            <div v-if="contentLoading" class="content-loading">正在抓取原文...</div>
            <div v-else-if="contentError" class="report-error">{{ contentError }}</div>
            <template v-else-if="contentState.content">
              <p v-if="contentState.fallback" class="translate-hint">{{ contentState.fallback_reason || "原文抓取失败，已展示本地摘要。" }}</p>
              <div class="content-tabs">
                <button
                  :class="{ active: contentTab === 'original' }"
                  @click="contentTab = 'original'"
                >
                  原文
                </button>
                <button
                  v-if="contentState.translated"
                  :class="{ active: contentTab === 'translated' }"
                  @click="contentTab = 'translated'"
                >
                  中文翻译
                </button>
              </div>
              <p v-if="!contentState.translated && contentState.language !== 'zh'" class="translate-hint">
                暂无可用翻译（需外网或配置 AI Key）
              </p>
              <div class="article-body">
                <pre v-if="contentTab === 'original' || !contentState.translated">{{ contentState.content }}</pre>
                <pre v-else>{{ contentState.translated }}</pre>
              </div>
            </template>
            <pre v-else class="article-empty">点击右侧条目后，这里展示原文内容。</pre>

            <p v-if="reportError" class="report-error">{{ reportError }}</p>
            <div v-if="reportHtml" class="markdown-body" v-html="reportHtml"></div>
            <pre v-else-if="!reportError">{{ "点击 AI 分析生成报告。" }}</pre>
          </template>
          <div v-else class="empty">
            <h2>选择一条热点查看分析</h2>
            <p>在左下角「AI 设置」里填入大模型 API Key 后，报告将由真实大模型生成（流式输出）；未配置时会先用本地模板占位。</p>
          </div>
        </section>

        <section class="insight" v-if="viewMode === 'insight'">
          <div class="insight-controls">
            <div class="insight-filter">
              <label>分类</label>
              <select v-model="insightCategory">
                <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="insight-filter">
              <label>时间范围</label>
              <div class="range-mini">
                <button
                  v-for="r in timeRanges"
                  :key="r.id"
                  :class="{ active: insightRange === r.id }"
                  @click="insightRange = r.id"
                >
                  {{ r.label }}
                </button>
              </div>
            </div>
            <button class="primary" @click="generateInsight" :disabled="insightLoading">
              {{ insightLoading ? "分析中..." : "生成信息差洞察" }}
            </button>
          </div>

          <div class="insight-stats" v-if="insightStats.total">
            <span class="stat"><b>{{ insightStats.total }}</b> 条目</span>
            <span class="stat"><b>{{ insightStats.categories }}</b> 分类</span>
            <span class="stat"><b>{{ insightStats.sources }}</b> 来源</span>
            <span class="stat accent"><b>{{ insightStats.foreign }}</b> 境外</span>
            <span class="stat warn"><b>{{ insightStats.pending }}</b> 待分析</span>
            <span class="engine-tag" :class="insightEngine">{{ insightEngine === 'llm' ? '大模型生成' : '本地聚合' }}</span>
          </div>

          <div class="insight-tabs">
            <button :class="{ active: insightTab === 'overview' }" @click="insightTab = 'overview'">总览洞察</button>
            <button :class="{ active: insightTab === 'events' }" @click="insightTab = 'events'">事件聚类</button>
          </div>

          <div v-if="insightTab === 'overview'">
            <div v-if="insightError" class="report-error">{{ insightError }}</div>
            <div v-else-if="insightHtml" class="markdown-body" v-html="insightHtml"></div>
            <div v-else class="insight-empty">
              <h2>生成一份信息差洞察</h2>
              <p>选择分类与时间范围，点击「生成信息差洞察」。系统会扫描已采集的热点，找出境外已热、境内待分析的信息差候选，并给出分类热度排行与跟进建议。</p>
              <p class="hint">本地聚合版离线可用；在「AI 设置」配置大模型 API Key 后，将自动改用真实模型撰写深度分析。</p>
            </div>
          </div>

          <div v-else-if="insightTab === 'events'" class="clusters">
            <div v-if="clustersLoading" class="hint">聚类分析中…</div>
            <div v-else-if="!clusters.length" class="insight-empty">
              <h2>跨源事件聚类</h2>
              <p>点击「刷新聚类」将同一事件的多源报道合并，标注境外 / 境内分布并量化信息差分。</p>
              <button class="primary" @click="loadClusters">刷新聚类</button>
            </div>
            <div v-else>
              <div class="clusters-head">
                <span>信息差事件（按信息差分排序）</span>
                <button class="ghost-sm" @click="loadClusters">刷新</button>
              </div>
              <div v-for="c in clusters" :key="c.representative" class="cluster-card">
                <div class="cluster-top">
                  <span class="cluster-score" :class="{ hot: c.score >= 100 }">{{ c.score }}</span>
                  <span class="cluster-title">{{ c.representative }}</span>
                </div>
                <div class="cluster-meta">
                  <span class="badge cov">跨源 {{ c.coverage }}</span>
                  <span class="badge os">境外 {{ c.overseas }}</span>
                  <span class="badge dom">境内 {{ c.domestic }}</span>
                  <span class="badge hot">热度 {{ c.total_hot }}</span>
                </div>
                <ul class="cluster-members">
                  <li v-for="m in c.members" :key="m.id" :class="{ foreign: m.foreign }">
                    <a :href="m.url" target="_blank" rel="noopener">{{ m.title }}</a>
                    <span class="m-src">{{ m.source }} · {{ m.hot_value }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div class="candidates" v-if="insightCandidates.length">
            <div class="candidates-head">
              <span>信息差候选（点击查看 / 分析）</span>
              <span class="candidates-count">{{ insightCandidates.length }}</span>
            </div>
            <button
              v-for="c in insightCandidates"
              :key="c.id"
              class="candidate"
              :class="{ done: c.analyzed }"
              @click="openCandidate(c)"
            >
              <span class="c-title">{{ c.title }}</span>
              <span class="c-meta">
                <i class="c-cat">{{ c.category }}</i>
                <i class="c-src">{{ c.source }}</i>
                <i class="c-state" :class="c.analyzed ? 'analyzed' : 'pending'">
                  {{ c.analyzed ? "已分析" : "待分析" }}
                </i>
                <i class="c-hot" v-if="c.hot_value">热度 {{ c.hot_value }}</i>
              </span>
            </button>
          </div>
        </section>
      </div>
    </section>

    <div v-if="showSettings" class="modal-mask" @click.self="showSettings = false">
      <div class="modal">
        <h2>AI 模型与监控设置</h2>
        <p class="modal-tip">API Key 只保存在本机用户目录，不会上传任何服务器。</p>

        <label class="field-label">服务商</label>
        <div class="provider-grid">
          <button
            v-for="provider in providers"
            :key="provider.id"
            :class="{ active: draft.provider === provider.id }"
            @click="chooseProvider(provider)"
          >
            {{ provider.label }}
          </button>
        </div>

        <label class="field-label" for="api-key">API Key</label>
        <input
          id="api-key"
          v-model="draft.api_key"
          type="password"
          :placeholder="settings.api_key_masked ? `已保存 ${settings.api_key_masked}，留空则不修改` : '填入你的 API Key'"
        />

        <label class="field-label" for="base-url">接口地址（Base URL）</label>
        <input id="base-url" v-model="draft.base_url" placeholder="https://api.example.com/v1" />

        <label class="field-label" for="model-name">模型名称</label>
        <input id="model-name" v-model="draft.model" placeholder="例如 qwen-plus / deepseek-chat / gpt-4o-mini" />

        <div class="settings-inline">
          <div>
            <label class="field-label" for="max-tokens">报告最大长度（tokens）</label>
            <input id="max-tokens" v-model.number="draft.max_tokens" type="number" min="256" max="32000" />
          </div>
          <div>
            <label class="field-label" for="cleanup-days">数据保留（天）</label>
            <input id="cleanup-days" v-model.number="draft.cleanup_days" type="number" min="7" max="3650" />
          </div>
        </div>

        <button class="ghost test-conn" @click="testConn" :disabled="testingConn">
          {{ testingConn ? "测试中…" : (connResult || "测试 AI 连接") }}
        </button>

        <div class="sources-block">
          <div class="sources-head">
            <label class="field-label">抓取来源（勾选要采集的源）</label>
            <div class="sources-bulk">
              <button class="ghost-sm" @click="setAllSources(true)">全选</button>
              <button class="ghost-sm" @click="setAllSources(false)">全不选</button>
            </div>
          </div>
          <p class="sources-count">已选 {{ draftEnabled.length }} / 共 {{ totalSourceCount }} 个来源</p>
          <div v-if="!sourcesLoaded" class="sources-hint">正在加载来源清单…</div>
          <div v-else class="source-groups">
            <div v-for="group in sourcesGroups" :key="group.category" class="source-group">
              <div class="source-group-head">
                <span>{{ group.category }}</span>
                <button class="ghost-sm" @click="setGroup(group, !groupAllOn(group))">
                  {{ groupAllOn(group) ? "全不选" : "全选" }}
                </button>
              </div>
              <div class="source-items">
                <label v-for="src in group.sources" :key="src.id" class="source-item">
                  <input
                    type="checkbox"
                    :checked="draftEnabled.includes(src.id)"
                    @change="toggleSource(src.id)"
                  />
                  <span>{{ src.name }}</span>
                  <button
                    v-if="src.custom"
                    class="feed-del"
                    title="删除该订阅源"
                    @click.prevent="removeFeed(src)"
                  >×</button>
                </label>
              </div>
            </div>
          </div>

          <div class="feeds-manager">
            <div class="feeds-add-row">
              <input v-model="feedDraft.name" placeholder="名称（可留空自动取域名）" class="feed-name" />
              <input v-model="feedDraft.url" placeholder="RSS 地址 https://…/feed" class="feed-url" />
              <select v-model="feedDraft.category">
                <option v-for="c in categories.filter(x => x !== '全部' && x !== '自定义站点')" :key="c" :value="c">{{ c }}</option>
              </select>
              <button class="ghost-sm" @click="addFeed" :disabled="!feedDraft.url">添加 RSS</button>
            </div>
            <div class="feeds-opml">
              <button class="ghost-sm" @click="importOpml">导入 OPML</button>
              <a class="ghost-sm" :href="`${apiBase}/feeds/export`" target="_blank" rel="noreferrer">导出 OPML</a>
              <span class="feeds-hint">支持从其他阅读器迁移订阅</span>
            </div>
            <div class="mirror-row">
              <label for="rsshub-mirror">RSSHub 镜像（被墙源自动兜底，可自建）</label>
              <input id="rsshub-mirror" v-model="draft.rsshub_mirror" placeholder="https://rsshub.app" />
            </div>
          </div>
        </div>

        <div class="keywords-block">
          <label class="field-label" for="watch-keywords">关键词监控（每行一个，采集到新命中时弹系统通知）</label>
          <textarea
            id="watch-keywords"
            v-model="draft.watch_keywords_text"
            rows="3"
            placeholder="例如：&#10;rust&#10;AI 芯片&#10;融资"
          ></textarea>
          <div class="keywords-actions">
            <button class="ghost-sm" @click="enableNotifications">开启通知权限</button>
            <span class="feeds-hint">{{ notifyState }}</span>
          </div>
        </div>

        <div class="modal-actions">
          <button @click="showSettings = false">取消</button>
          <button class="primary" @click="saveSettings" :disabled="savingSettings">保存</button>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import hljs from "highlight.js";
import "highlight.js/styles/atom-one-dark.css";

const apiBase = new URLSearchParams(window.location.search).get("api") || "http://127.0.0.1:8765";
const FALLBACK_CATEGORIES = [
  "全部",
  "人工智能",
  "编程开发",
  "开源项目",
  "科技",
  "全球新闻",
  "创业与商业",
  "设计与产品",
  "区块链与加密货币",
  "网络安全",
  "科学",
  "自定义站点"
];
const categories = ref([...FALLBACK_CATEGORIES]);
const CATEGORY_COLORS = {
  "人工智能": "#7c5cff",
  "编程开发": "#2f9e6e",
  "开源项目": "#0f5c58",
  "科技": "#1f7ae0",
  "全球新闻": "#d9822b",
  "创业与商业": "#c2417a",
  "设计与产品": "#e0633b",
  "区块链与加密货币": "#b8860b",
  "网络安全": "#c0392b",
  "科学": "#2f9e9e",
  "自定义站点": "#6b7280"
};

function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return "刚刚";
  if (s < 3600) return Math.floor(s / 60) + " 分钟前";
  if (s < 86400) return Math.floor(s / 3600) + " 小时前";
  if (s < 2592000) return Math.floor(s / 86400) + " 天前";
  if (s < 31536000) return Math.floor(s / 2592000) + " 个月前";
  return Math.floor(s / 31536000) + " 年前";
}
const timeRanges = [
  { id: "all", label: "全部时间" },
  { id: "week", label: "一周最热" },
  { id: "month", label: "一个月最热" },
  { id: "quarter", label: "三个月最热" },
  { id: "year", label: "一年最热" }
];
const selectedCategory = ref("全部");
const selectedRange = ref("all");
const customUrl = ref("");
const searchQuery = ref("");
const favoriteOnly = ref(false);
const items = ref([]);
const loading = ref(false);
const reportLoading = ref(false);
const streaming = ref(false);
const selectedItem = ref(null);
const reportHtml = ref("");
const reportRaw = ref("");
const reportError = ref("");
const statusText = ref("本地数据库准备就绪，点击刷新开始采集。");

const viewMode = ref("list"); // "list" | "insight"
const insightCategory = ref("全部");
const insightRange = ref("all");
const insightHtml = ref("");
const clusters = ref([]);
const insightTab = ref("events");
const clustersLoading = ref(false);
const insightLoading = ref(false);
const insightError = ref("");
const insightStats = reactive({ total: 0, categories: 0, sources: 0, foreign: 0, pending: 0 });
const insightEngine = ref("local");
const insightCandidates = ref([]);
const gapSummary = reactive({ total: 0, foreign: 0, pending: 0, candidates: 0 });

const showSettings = ref(false);
const savingSettings = ref(false);
const providers = ref([]);
const settings = reactive({
  provider: "dashscope", base_url: "", model: "", api_key_set: false, api_key_masked: "",
  configured: false, enabled_sources: [], watch_keywords: [], max_tokens: 2000, cleanup_days: 180,
  rsshub_mirror: "https://rsshub.app"
});
const draft = reactive({ provider: "dashscope", api_key: "", base_url: "", model: "", watch_keywords_text: "", max_tokens: 2000, cleanup_days: 180, rsshub_mirror: "" });
const testingConn = ref(false);
const connResult = ref("");

const sourcesGroups = ref([]);
const sourcesLoaded = ref(false);
const enabledSources = ref([]);
const draftEnabled = ref([]);
const totalSourceCount = computed(() => sourcesGroups.value.reduce((n, g) => n + g.sources.length, 0));
const feedDraft = reactive({ name: "", url: "", category: "科技" });

const customSites = ref([]);
const batchLoading = ref(false);
const batchProgress = reactive({ done: 0, total: 0 });
const lastCrawl = ref(null);
const hasMore = ref(false);
const loadingMore = ref(false);
const PAGE_SIZE = 500;

const contentState = reactive({ loading: false, error: "", content: "", translated: "", language: "", fallback: false, fallback_reason: "" });
const contentTab = ref("original");
const contentLoading = computed(() => contentState.loading);
const contentError = computed(() => contentState.error);

const aiConfigured = computed(() => settings.configured);

const filteredItems = computed(() => {
  let list = items.value;
  if (selectedCategory.value !== "全部") {
    list = list.filter((item) => item.category === selectedCategory.value);
  }
  const q = searchQuery.value.trim().toLowerCase();
  if (q && q.length < 2) {
    // 过短的关键词不做服务端搜索，退化为本地过滤
    list = list.filter((item) =>
      (item.title + " " + item.source + " " + item.category).toLowerCase().includes(q)
    );
  }
  return list;
});

const categoryCounts = computed(() => {
  const map = {};
  for (const it of items.value) map[it.category] = (map[it.category] || 0) + 1;
  return map;
});

const theme = ref(localStorage.getItem("igr-theme") || "light");
function applyTheme() {
  document.documentElement.setAttribute("data-theme", theme.value);
}
function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
  localStorage.setItem("igr-theme", theme.value);
  applyTheme();
}

// ===== 自动巡航（雷达后台定时采集）=====
const CRUISE_OPTIONS = [15, 30, 60, 120];
const autoCruise = ref(localStorage.getItem("igr-autocruise") === "1");
const cruiseInterval = ref(Number(localStorage.getItem("igr-cruise-interval")) || 30);
let cruiseTimer = null;
let cruiseCountdown = ref(0);
let cruiseTickTimer = null;

function applyAutoCruise() {
  if (cruiseTimer) { clearInterval(cruiseTimer); cruiseTimer = null; }
  if (cruiseTickTimer) { clearInterval(cruiseTickTimer); cruiseTickTimer = null; }
  localStorage.setItem("igr-autocruise", autoCruise.value ? "1" : "0");
  localStorage.setItem("igr-cruise-interval", String(cruiseInterval.value));
  if (!autoCruise.value) {
    cruiseCountdown.value = 0;
    return;
  }
  let remain = cruiseInterval.value * 60;
  cruiseCountdown.value = remain;
  cruiseTimer = setInterval(() => {
    if (loading.value || insightLoading.value) return; // 避免与手动/洞察请求叠加
    refresh("all");
  }, cruiseInterval.value * 60 * 1000);
  cruiseTickTimer = setInterval(() => {
    remain = Math.max(0, remain - 1);
    cruiseCountdown.value = remain;
  }, 1000);
}

function toggleAutoCruise() {
  autoCruise.value = !autoCruise.value;
  applyAutoCruise();
}

function setCruiseInterval(min) {
  cruiseInterval.value = min;
  applyAutoCruise();
}

watch(selectedRange, () => {
  loadItems().catch(() => {
    statusText.value = "无法连接后端，请先启动后端服务（python main.py --port 8765）。";
  });
});

watch(selectedCategory, () => {
  if (searchQuery.value && searchQuery.value.trim().length >= 2) return; // 搜索态由搜索逻辑接管
  loadItems().catch(() => {});
});

// 搜索防抖：2 字符以上走服务端 FTS 全文检索（覆盖全部库内数据）
let searchTimer = null;
watch(searchQuery, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const q = searchQuery.value.trim();
    if (q.length >= 2) {
      loadItems().catch(() => {});
    }
  }, 350);
});

function clearSearch() {
  searchQuery.value = "";
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      detail = JSON.parse(detail).detail || detail;
    } catch {
      // 保持原文本
    }
    throw new Error(detail || `请求失败（${response.status}）`);
  }
  return response.json();
}

function renderMarkdown(markdown) {
  if (!markdown) return "";
  const raw = marked.parse(markdown);
  return DOMPurify.sanitize(raw);
}

// 渲染 Markdown 到响应式 ref，并在插入 DOM 后对代码块做语法高亮
function setMarkdown(target, markdown) {
  target.value = renderMarkdown(markdown);
  nextTick(() => {
    document.querySelectorAll(".markdown-body pre code").forEach((el) => {
      if (el.dataset.hl) return;
      try {
        hljs.highlightElement(el);
        el.dataset.hl = "1";
      } catch {
        // 忽略个别代码块高亮失败
      }
    });
  });
}

function applySettingsMeta(data) {
  Object.assign(settings, data.settings);
  providers.value = data.providers || [];
  if (Array.isArray(data.settings?.enabled_sources)) {
    enabledSources.value = data.settings.enabled_sources;
  }
  if (Array.isArray(data.settings?.watch_keywords)) {
    settings.watch_keywords = data.settings.watch_keywords;
  }
  rebuildCategories();
}

// 分类词表以后端 /sources 为准，避免前后端各写一份导致漂移
function rebuildCategories() {
  const set = new Set(FALLBACK_CATEGORIES);
  for (const group of sourcesGroups.value) set.add(group.category);
  categories.value = [...set];
}

async function loadSettings() {
  try {
    applySettingsMeta(await api("/settings"));
  } catch {
    statusText.value = "无法连接后端设置接口，请确认后端服务已启动。";
  }
}

async function loadSources() {
  try {
    const data = await api("/sources");
    sourcesGroups.value = data.groups || [];
    sourcesLoaded.value = true;
    rebuildCategories();
  } catch {
    sourcesLoaded.value = false;
  }
}

async function loadCustomSites() {
  try {
    const data = await api("/custom-sites");
    customSites.value = data.sites || [];
  } catch {
    // 非关键数据，失败不提示
  }
}

function openSettings() {
  draft.provider = settings.provider || "dashscope";
  draft.api_key = "";
  draft.base_url = settings.base_url || "";
  draft.model = settings.model || "";
  draft.max_tokens = settings.max_tokens || 2000;
  draft.cleanup_days = settings.cleanup_days || 180;
  draft.rsshub_mirror = settings.rsshub_mirror || "";
  draft.watch_keywords_text = (settings.watch_keywords || []).join("\n");
  draftEnabled.value = [...enabledSources.value];
  connResult.value = "";
  showSettings.value = true;
}

function toggleSource(id) {
  const i = draftEnabled.value.indexOf(id);
  if (i >= 0) draftEnabled.value.splice(i, 1);
  else draftEnabled.value.push(id);
}

function setGroup(group, on) {
  const ids = group.sources.map((s) => s.id);
  if (on) {
    for (const id of ids) if (!draftEnabled.value.includes(id)) draftEnabled.value.push(id);
  } else {
    draftEnabled.value = draftEnabled.value.filter((id) => !ids.includes(id));
  }
}

function groupAllOn(group) {
  return group.sources.every((s) => draftEnabled.value.includes(s.id));
}

function setAllSources(on) {
  if (on) {
    const all = [];
    for (const g of sourcesGroups.value) for (const s of g.sources) all.push(s.id);
    draftEnabled.value = all;
  } else {
    draftEnabled.value = [];
  }
}

async function addFeed() {
  if (!feedDraft.url.trim()) return;
  try {
    const data = await api("/feeds", {
      method: "POST",
      body: JSON.stringify({
        name: feedDraft.name.trim() || new URL(feedDraft.url).hostname,
        url: feedDraft.url.trim(),
        category: feedDraft.category
      })
    });
    feedDraft.name = "";
    feedDraft.url = "";
    await refreshFeeds(data.feeds);
    statusText.value = "订阅源已添加，保存设置后参与采集。";
  } catch (error) {
    statusText.value = `添加订阅源失败：${error.message}`;
  }
}

async function removeFeed(src) {
  // src.id 形如 "feed:3"
  const feedId = Number(String(src.id).split(":")[1]);
  if (!feedId) return;
  try {
    const data = await api(`/feeds/${feedId}`, { method: "DELETE" });
    await refreshFeeds(data.feeds);
  } catch (error) {
    statusText.value = `删除订阅源失败：${error.message}`;
  }
}

async function refreshFeeds() {
  await loadSources();
}

async function importOpml() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".opml,.xml,text/xml";
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = await api("/feeds/import", { method: "POST", body: JSON.stringify({ opml: text }) });
      await loadSources();
      statusText.value = `OPML 导入完成：${data.imported} 个订阅源。`;
    } catch (error) {
      statusText.value = `OPML 导入失败：${error.message}`;
    }
  };
  input.click();
}

async function testConn() {
  testingConn.value = true;
  connResult.value = "";
  try {
    const result = await api("/settings/test", {
      method: "POST",
      body: JSON.stringify({
        base_url: draft.base_url,
        model: draft.model,
        api_key: draft.api_key || undefined
      })
    });
    connResult.value = `连接成功：${result.model}（${result.latency_ms}ms）`;
  } catch (error) {
    connResult.value = `连接失败：${error.message.slice(0, 120)}`;
  } finally {
    testingConn.value = false;
  }
}

const notifyState = computed(() => {
  if (typeof Notification === "undefined") return "当前环境不支持系统通知";
  if (Notification.permission === "granted") return "系统通知已开启";
  if (Notification.permission === "denied") return "通知被系统拒绝，请在系统设置中允许";
  return "尚未开启系统通知";
});

function enableNotifications() {
  if (typeof Notification === "undefined") return;
  Notification.requestPermission();
}

function chooseProvider(provider) {
  draft.provider = provider.id;
  if (provider.id !== "custom") {
    draft.base_url = provider.base_url;
    draft.model = provider.default_model;
  }
}

async function saveSettings() {
  savingSettings.value = true;
  try {
    const payload = {
      provider: draft.provider,
      base_url: draft.base_url,
      model: draft.model,
      max_tokens: draft.max_tokens,
      cleanup_days: draft.cleanup_days,
      rsshub_mirror: draft.rsshub_mirror.trim(),
      watch_keywords: draft.watch_keywords_text.split("\n").map((s) => s.trim()).filter(Boolean),
      enabled_sources: draftEnabled.value
    };
    if (draft.api_key) payload.api_key = draft.api_key;
    applySettingsMeta(await api("/settings", { method: "PUT", body: JSON.stringify(payload) }));
    showSettings.value = false;
    statusText.value = settings.configured ? "AI 模型已配置，可以生成真实分析报告。" : "AI 未配置，报告仍为本地模板。";
  } catch (error) {
    statusText.value = `保存设置失败：${error.message}`;
  } finally {
    savingSettings.value = false;
  }
}

async function loadItems({ append = false } = {}) {
  const query = new URLSearchParams({
    range: selectedRange.value,
    category: selectedCategory.value,
    favorite: favoriteOnly.value ? "true" : "false",
    limit: String(PAGE_SIZE),
    offset: String(append ? items.value.length : 0)
  });
  const q = searchQuery.value.trim();
  if (q.length >= 2) query.set("q", q);
  const data = await api(`/items?${query.toString()}`);
  items.value = append ? items.value.concat(data.items) : data.items;
  hasMore.value = data.items.length >= PAGE_SIZE;
  loadGapSummary();
  checkWatchKeywords(data.items);
}

// ===== 关键词监控：新采集命中关键词 → 系统通知 =====
function checkWatchKeywords(freshItems) {
  const keywords = settings.watch_keywords || [];
  if (!keywords.length || typeof Notification === "undefined" || Notification.permission !== "granted") {
    return;
  }
  const lastSeen = localStorage.getItem("igr-last-seen");
  const now = new Date().toISOString();
  if (!lastSeen) {
    localStorage.setItem("igr-last-seen", now);
    return; // 首次只建立基线，避免历史条目刷屏
  }
  const hits = [];
  for (const it of freshItems) {
    if ((it.crawl_time || "") <= lastSeen) continue;
    const haystack = `${it.title || ""} ${it.summary || ""}`;
    if (keywords.some((kw) => haystack.includes(kw))) hits.push(it);
  }
  localStorage.setItem("igr-last-seen", now);
  // 最多弹 3 条，避免打扰
  for (const hit of hits.slice(0, 3)) {
    try {
      new Notification(`关键词命中：${hit.source}`, {
        body: (hit.title || "").slice(0, 120),
        silent: false
      });
    } catch {
      // 通知失败不影响主流程
    }
  }
  if (hits.length > 3) {
    statusText.value = `关键词命中 ${hits.length} 条（仅弹出前 3 条），请在列表中查看。`;
  }
}

async function refresh(source) {
  loading.value = true;
  statusText.value = "正在并发采集热点...";
  try {
    const category = source === "all" && selectedCategory.value !== "全部" ? selectedCategory.value : null;
    const data = await api("/crawl", {
      method: "POST",
      body: JSON.stringify({ source, range: selectedRange.value, category })
    });
    await loadItems();
    lastCrawl.value = {
      ok: data.ok_sources,
      failed: data.failed_sources || [],
      prefetch: data.prefetch || 0
    };
    const failed = data.failed_sources || [];
    const failNote = failed.length ? `，失败 ${failed.length} 源` : "";
    statusText.value = `采集完成：${data.ok_sources} 源成功 / ${data.saved} 条热点${failNote}` +
      (data.prefetch ? `，后台预抓 ${data.prefetch} 条全文` : "");
  } catch (error) {
    statusText.value = `采集失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function crawlCustom() {
  loading.value = true;
  statusText.value = "正在分析自定义站点...";
  try {
    const data = await api("/crawl/custom", {
      method: "POST",
      body: JSON.stringify({ url: customUrl.value })
    });
    selectedCategory.value = "自定义站点";
    await loadItems();
    await loadCustomSites();
    customUrl.value = "";
    statusText.value = `「${data.site_title}」已提取 ${data.saved} 条候选内容。`;
  } catch (error) {
    statusText.value = `抓取失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function recrawlSite(site) {
  loading.value = true;
  statusText.value = `重新抓取 ${site.title || site.url} ...`;
  try {
    const data = await api("/crawl/custom", {
      method: "POST",
      body: JSON.stringify({ url: site.url })
    });
    selectedCategory.value = "自定义站点";
    await loadItems();
    statusText.value = `「${data.site_title}」更新 ${data.saved} 条。`;
  } catch (error) {
    statusText.value = `抓取失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

async function removeSite(site) {
  try {
    await api(`/custom-sites/${site.id}`, { method: "DELETE" });
    await loadCustomSites();
  } catch (error) {
    statusText.value = `删除站点失败：${error.message}`;
  }
}

async function toggleFlag(item, flag) {
  try {
    await api(`/items/${item.id}/flags`, {
      method: "PATCH",
      body: JSON.stringify({ [flag]: !item[flag] })
    });
    item[flag] = item[flag] ? 0 : 1;
    if (selectedItem.value?.id === item.id) selectedItem.value[flag] = item[flag];
    if (flag === "favorite" && favoriteOnly.value) await loadItems();
  } catch (error) {
    statusText.value = `操作失败：${error.message}`;
  }
}

async function hideItem(item) {
  try {
    await api(`/items/${item.id}/flags`, {
      method: "PATCH",
      body: JSON.stringify({ hidden: true })
    });
    items.value = items.value.filter((it) => it.id !== item.id);
    if (selectedItem.value?.id === item.id) selectedItem.value = null;
    statusText.value = "已隐藏该条目（可在数据库中恢复，收藏不受影响）。";
  } catch (error) {
    statusText.value = `隐藏失败：${error.message}`;
  }
}

async function selectItem(item) {
  selectedItem.value = item;
  reportError.value = "";
  reportHtml.value = "";
  reportRaw.value = "";
  contentTab.value = "original";
  contentState.content = "";
  contentState.translated = "";
  contentState.error = "";
  contentState.fallback = false;
  contentState.fallback_reason = "";
  // 拉完整条目（含已缓存报告），并标记已读
  try {
    const full = await api(`/items/${item.id}`);
    Object.assign(item, {
      ai_report: full.ai_report,
      analyzed: !!(full.ai_report && full.ai_report.length)
    });
    if (full.ai_report) {
      reportRaw.value = full.ai_report;
      setMarkdown(reportHtml, full.ai_report);
    }
  } catch {
    // 详情拉取失败不阻塞
  }
  if (!item.read) {
    item.read = 1;
    api(`/items/${item.id}/flags`, { method: "PATCH", body: JSON.stringify({ read: true }) }).catch(() => {});
  }
  loadContent(item.id);
}

async function loadContent(itemId) {
  contentState.loading = true;
  contentState.error = "";
  try {
    const data = await api(`/items/${itemId}/content`);
    contentState.content = data.content || "";
    contentState.translated = data.translated || "";
    contentState.language = data.language || "";
    contentState.fallback = !!data.fallback;
    contentState.fallback_reason = data.fallback_reason || "";
    if (!contentState.translated) contentTab.value = "original";
  } catch (error) {
    contentState.error = error.message;
  } finally {
    contentState.loading = false;
  }
}

async function generateReport() {
  if (!selectedItem.value?.id) return;
  const itemId = selectedItem.value.id;
  reportLoading.value = true;
  streaming.value = false;
  reportError.value = "";
  reportHtml.value = "";
  reportRaw.value = "";
  let streamed = false;
  try {
    // 优先流式：逐块渲染，边生成边看
    const response = await fetch(`${apiBase}/items/${itemId}/report/stream`, { method: "POST" });
    if (response.ok) {
      streaming.value = true;
      streamed = true;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      let lastPaint = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        const now = Date.now();
        if (now - lastPaint > 120) {
          // 节流渲染，避免高频重绘
          lastPaint = now;
          reportRaw.value = acc;
          setMarkdown(reportHtml, acc);
        }
      }
      reportRaw.value = acc;
      setMarkdown(reportHtml, acc);
      selectedItem.value.ai_report = acc;
      selectedItem.value.analyzed = true;
    } else {
      // 未配置（400）或其他错误 → 回退非流式接口（本地模板也在那里）
      await generateReportFallback(itemId);
    }
  } catch (error) {
    if (!streamed) {
      try {
        await generateReportFallback(itemId);
      } catch (fallbackError) {
        reportError.value = fallbackError.message;
      }
    } else {
      reportError.value = `流式中断：${error.message}`;
    }
  } finally {
    streaming.value = false;
    reportLoading.value = false;
  }
}

async function generateReportFallback(itemId) {
  const data = await api(`/items/${itemId}/report`, { method: "POST" });
  reportRaw.value = data.report;
  setMarkdown(reportHtml, data.report);
  const target = items.value.find((it) => it.id === itemId);
  if (target) {
    target.ai_report = data.report;
    target.analyzed = true;
  }
  if (selectedItem.value?.id === itemId) {
    selectedItem.value.ai_report = data.report;
    selectedItem.value.analyzed = true;
  }
  await loadGapSummary();
  if (data.engine === "local") {
    statusText.value = "未配置 AI Key，当前为本地模板报告；到「AI 设置」配置后可获得真实分析。";
  }
}

async function batchAnalyze() {
  const pending = filteredItems.value.filter((it) => !it.analyzed).slice(0, 10);
  if (!pending.length) {
    statusText.value = "当前列表没有待分析条目。";
    return;
  }
  batchLoading.value = true;
  batchProgress.total = pending.length;
  batchProgress.done = 0;
  statusText.value = `批量分析中（共 ${pending.length} 条）…`;
  let ok = 0;
  for (const item of pending) {
    try {
      const data = await api(`/items/${item.id}/report`, { method: "POST" });
      item.ai_report = data.report;
      item.analyzed = true;
      ok += 1;
    } catch {
      // 单条失败继续下一条
    }
    batchProgress.done += 1;
    statusText.value = `批量分析进度 ${batchProgress.done}/${batchProgress.total}`;
  }
  batchLoading.value = false;
  await loadGapSummary();
  statusText.value = `批量分析完成：成功 ${ok} / 共 ${pending.length} 条。`;
}

function exportReport() {
  if (!reportRaw.value) return;
  const blob = new Blob([reportRaw.value], { type: "text/markdown;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `报告-${(selectedItem.value?.title || "info-gap").slice(0, 40).replace(/[\\/:*?"<>|]/g, "_")}.md`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function printReport() {
  document.body.classList.add("printing-report");
  window.print();
  setTimeout(() => document.body.classList.remove("printing-report"), 500);
}

async function generateInsight() {
  insightLoading.value = true;
  insightError.value = "";
  try {
    const data = await api("/report", {
      method: "POST",
      body: JSON.stringify({ category: insightCategory.value, range: insightRange.value })
    });
    setMarkdown(insightHtml, data.report);
    Object.assign(insightStats, data.stats || {});
    insightEngine.value = data.engine || "local";
    insightCandidates.value = data.candidates || [];
    loadClusters();
    statusText.value = insightEngine.value === "llm"
      ? "已生成大模型版信息差洞察。"
      : "已生成本地聚合洞察；配置 AI Key 后可获得大模型深度分析。";
  } catch (error) {
    insightError.value = error.message;
  } finally {
    insightLoading.value = false;
  }
}

async function loadGapSummary() {
  try {
    const data = await api("/insight/summary");
    Object.assign(gapSummary, data);
  } catch {
    // 侧栏信号加载失败不阻塞主流程
  }
}

function openInsightFromSidebar() {
  viewMode.value = "insight";
  if (insightTab.value === "events" && !clusters.value.length) loadClusters();
  if (!insightHtml.value) generateInsight();
}

function openCandidate(c) {
  viewMode.value = "list";
  selectedCategory.value = c.category || "全部";
  // 候选条目来自全库查询，先切换分类再选中
  loadItems().then(() => {
    const target = items.value.find((it) => it.id === c.id);
    if (target) selectItem(target);
  });
}

async function loadClusters() {
  clustersLoading.value = true;
  try {
    const qs = new URLSearchParams({ category: insightCategory.value, range: insightRange.value });
    const data = await api(`/clusters?${qs.toString()}`);
    clusters.value = data.clusters || [];
  } catch {
    // 聚类加载失败不阻塞主流程
  } finally {
    clustersLoading.value = false;
  }
}

watch(favoriteOnly, () => {
  loadItems().catch(() => {});
});

onMounted(() => {
  applyTheme();
  loadSettings();
  loadSources();
  loadCustomSites();
  loadGapSummary();
  applyAutoCruise();
  loadItems().catch(() => {
    statusText.value = "无法连接后端，请先启动后端服务（python main.py --port 8765）。";
  });
});
</script>
