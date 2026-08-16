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
          <input id="site-url" v-model="customUrl" placeholder="https://github.com/trending" />
          <button @click="crawlCustom" :disabled="loading || !customUrl">抓取</button>
        </div>
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
          <button class="primary" @click="refresh('all')" :disabled="loading">刷新全部</button>
        </div>
      </header>

      <div class="search-row" v-if="viewMode === 'list'">
        <input v-model="searchQuery" type="search" placeholder="搜索标题 / 来源 / 分类…" />
        <button v-if="searchQuery" class="ghost" @click="searchQuery = ''">清除</button>
        <span class="result-count">{{ filteredItems.length }} 条</span>
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
          <article
            v-for="item in filteredItems"
            :key="item.id || item.url"
            :class="{ selected: selectedItem?.url === item.url }"
            :style="{ '--cat': CATEGORY_COLORS[item.category] || '#0f5c58' }"
            @click="selectItem(item)"
          >
            <div class="item-meta">
              <span class="cat"><i class="dot"></i>{{ item.category }}</span>
              <span class="src">{{ item.source }}</span>
              <span class="time">{{ timeAgo(item.item_date) }}</span>
              <strong v-if="item.hot_value">{{ item.hot_value }}</strong>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary }}</p>
          </article>
        </section>

        <section class="report" v-if="viewMode === 'list'">
          <template v-if="selectedItem">
            <div class="report-head">
              <div>
                <p class="eyebrow">{{ selectedItem.source }}</p>
                <h2>{{ selectedItem.title }}</h2>
              </div>
              <button class="primary" @click="generateReport" :disabled="reportLoading">
                {{ reportLoading ? "分析中..." : "AI 分析" }}
              </button>
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
            <p>在左下角「AI 设置」里填入大模型 API Key 后，报告将由真实大模型生成；未配置时会先用本地模板占位。</p>
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
        <h2>AI 模型设置</h2>
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
                </label>
              </div>
            </div>
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
const categories = [
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
const items = ref([]);
const loading = ref(false);
const reportLoading = ref(false);
const selectedItem = ref(null);
const reportHtml = ref("");
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
const settings = reactive({ provider: "dashscope", base_url: "", model: "", api_key_set: false, api_key_masked: "", configured: false, enabled_sources: [] });
const draft = reactive({ provider: "dashscope", api_key: "", base_url: "", model: "" });

const sourcesGroups = ref([]);
const sourcesLoaded = ref(false);
const enabledSources = ref([]);
const draftEnabled = ref([]);
const totalSourceCount = computed(() => sourcesGroups.value.reduce((n, g) => n + g.sources.length, 0));

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
  if (q) {
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
  } catch {
    sourcesLoaded.value = false;
  }
}

function openSettings() {
  draft.provider = settings.provider || "dashscope";
  draft.api_key = "";
  draft.base_url = settings.base_url || "";
  draft.model = settings.model || "";
  draftEnabled.value = [...enabledSources.value];
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

async function loadItems() {
  const query = new URLSearchParams({ range: selectedRange.value, category: selectedCategory.value });
  const data = await api(`/items?${query.toString()}`);
  items.value = data.items;
  loadGapSummary();
}

async function refresh(source) {
  loading.value = true;
  statusText.value = "正在采集热点...";
  try {
    const category = source === "all" && selectedCategory.value !== "全部" ? selectedCategory.value : null;
    const data = await api("/crawl", {
      method: "POST",
      body: JSON.stringify({ source, range: selectedRange.value, category })
    });
    await loadItems();
    statusText.value = `已更新 ${data.saved} 条热点。`;
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
    statusText.value = `自定义站点已提取 ${data.saved} 条候选内容。`;
  } catch (error) {
    statusText.value = `抓取失败：${error.message}`;
  } finally {
    loading.value = false;
  }
}

function selectItem(item) {
  selectedItem.value = item;
  reportError.value = "";
  reportHtml.value = item.ai_report ? renderMarkdown(item.ai_report) : "";
  contentTab.value = "original";
  contentState.content = "";
  contentState.translated = "";
  contentState.error = "";
  contentState.fallback = false;
  contentState.fallback_reason = "";
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
  reportLoading.value = true;
  reportError.value = "";
  try {
    const data = await api(`/items/${selectedItem.value.id}/report`, { method: "POST" });
    setMarkdown(reportHtml, data.report);
    selectedItem.value.ai_report = data.report;
    await loadGapSummary();
    if (data.engine === "local") {
      statusText.value = "未配置 AI Key，当前为本地模板报告；到「AI 设置」配置后可获得真实分析。";
    }
  } catch (error) {
    reportError.value = error.message;
  } finally {
    reportLoading.value = false;
  }
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
  selectItem(c);
  viewMode.value = "list";
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

onMounted(() => {
  applyTheme();
  loadSettings();
  loadSources();
  loadGapSummary();
  applyAutoCruise();
  loadItems().catch(() => {
    statusText.value = "无法连接后端，请先启动后端服务（python main.py --port 8765）。";
  });
});
</script>
