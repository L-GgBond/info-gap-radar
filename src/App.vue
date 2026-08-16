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
          {{ category }}
        </button>
      </nav>

      <section class="custom-crawl">
        <label for="site-url">自定义站点</label>
        <div class="input-row">
          <input id="site-url" v-model="customUrl" placeholder="https://github.com/trending" />
          <button @click="crawlCustom" :disabled="loading || !customUrl">抓取</button>
        </div>
      </section>

      <section class="ai-settings">
        <div class="ai-status" :class="{ ok: aiConfigured }">
          {{ aiConfigured ? `AI 已配置：${settings.model || "自定义模型"}` : "AI 未配置（报告为本地模板）" }}
        </div>
        <button @click="openSettings">AI 设置</button>
      </section>
    </aside>

    <section class="content">
      <header class="toolbar">
        <div>
          <h2>热点雷达</h2>
          <p>{{ statusText }}</p>
        </div>
        <div class="actions">
          <button @click="refresh('github')" :disabled="loading">GitHub</button>
          <button @click="refresh('hn')" :disabled="loading">Hacker News</button>
          <button class="primary" @click="refresh('all')" :disabled="loading">刷新全部</button>
        </div>
      </header>

      <div class="range-row">
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
        <section class="list">
          <article
            v-for="item in filteredItems"
            :key="item.id || item.url"
            :class="{ selected: selectedItem?.url === item.url }"
            @click="selectItem(item)"
          >
            <div class="item-meta">
              <span>{{ item.category }}</span>
              <span>{{ item.source }}</span>
              <strong v-if="item.hot_value">{{ item.hot_value }}</strong>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary }}</p>
          </article>
        </section>

        <section class="report">
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

        <div class="modal-actions">
          <button @click="showSettings = false">取消</button>
          <button class="primary" @click="saveSettings" :disabled="savingSettings">保存</button>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";

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
const items = ref([]);
const loading = ref(false);
const reportLoading = ref(false);
const selectedItem = ref(null);
const reportHtml = ref("");
const reportError = ref("");
const statusText = ref("本地数据库准备就绪，点击刷新开始采集。");

const showSettings = ref(false);
const savingSettings = ref(false);
const providers = ref([]);
const settings = reactive({ provider: "dashscope", base_url: "", model: "", api_key_set: false, api_key_masked: "", configured: false });
const draft = reactive({ provider: "dashscope", api_key: "", base_url: "", model: "" });

const contentState = reactive({ loading: false, error: "", content: "", translated: "", language: "", fallback: false, fallback_reason: "" });
const contentTab = ref("original");
const contentLoading = computed(() => contentState.loading);
const contentError = computed(() => contentState.error);

const aiConfigured = computed(() => settings.configured);

const filteredItems = computed(() => {
  if (selectedCategory.value === "全部") return items.value;
  return items.value.filter((item) => item.category === selectedCategory.value);
});

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

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(markdown) {
  const lines = escapeHtml(markdown).split("\n");
  const html = [];
  let inList = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("### ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h4>${inline(trimmed.slice(4))}</h4>`);
    } else if (trimmed.startsWith("## ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h3>${inline(trimmed.slice(3))}</h3>`);
    } else if (trimmed.startsWith("# ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<h2>${inline(trimmed.slice(2))}</h2>`);
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${inline(trimmed.slice(2))}</li>`);
    } else if (trimmed === "") {
      if (inList) { html.push("</ul>"); inList = false; }
    } else {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push(`<p>${inline(trimmed)}</p>`);
    }
  }
  if (inList) html.push("</ul>");
  return html.join("");

  function inline(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
  }
}

function applySettingsMeta(data) {
  Object.assign(settings, data.settings);
  providers.value = data.providers || [];
}

async function loadSettings() {
  try {
    applySettingsMeta(await api("/settings"));
  } catch {
    statusText.value = "无法连接后端设置接口，请确认后端服务已启动。";
  }
}

function openSettings() {
  draft.provider = settings.provider || "dashscope";
  draft.api_key = "";
  draft.base_url = settings.base_url || "";
  draft.model = settings.model || "";
  showSettings.value = true;
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
      model: draft.model
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
}

async function refresh(source) {
  loading.value = true;
  statusText.value = "正在采集热点...";
  try {
    const data = await api("/crawl", {
      method: "POST",
      body: JSON.stringify({ source, range: selectedRange.value })
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
    reportHtml.value = renderMarkdown(data.report);
    selectedItem.value.ai_report = data.report;
    if (data.engine === "local") {
      statusText.value = "未配置 AI Key，当前为本地模板报告；到「AI 设置」配置后可获得真实分析。";
    }
  } catch (error) {
    reportError.value = error.message;
  } finally {
    reportLoading.value = false;
  }
}

onMounted(() => {
  loadSettings();
  loadItems().catch(() => {
    statusText.value = "无法连接后端，请先启动后端服务（python main.py --port 8765）。";
  });
});
</script>
