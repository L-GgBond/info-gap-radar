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
              <button class="primary" @click="generateReport" :disabled="reportLoading">AI 分析</button>
            </div>
            <a :href="selectedItem.url" target="_blank" rel="noreferrer">打开来源</a>
            <pre>{{ reportText || selectedItem.ai_report || "点击 AI 分析生成报告。" }}</pre>
          </template>
          <div v-else class="empty">
            <h2>选择一条热点查看分析</h2>
            <p>第一版会先用本地规则生成报告；接入大模型 API 后，这里会显示更深入的趋势、风险和机会分析。</p>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

const apiBase = new URLSearchParams(window.location.search).get("api") || "http://127.0.0.1:8765";
const categories = ["全部", "开源项目", "科技", "全球新闻", "自定义站点"];
const selectedCategory = ref("全部");
const customUrl = ref("");
const items = ref([]);
const loading = ref(false);
const reportLoading = ref(false);
const selectedItem = ref(null);
const reportText = ref("");
const statusText = ref("本地数据库准备就绪，点击刷新开始采集。");

const filteredItems = computed(() => {
  if (selectedCategory.value === "全部") return items.value;
  return items.value.filter((item) => item.category === selectedCategory.value);
});

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function loadItems() {
  const data = await api("/items");
  items.value = data.items;
}

async function refresh(source) {
  loading.value = true;
  statusText.value = "正在采集热点...";
  try {
    const data = await api("/crawl", {
      method: "POST",
      body: JSON.stringify({ source })
    });
    await loadItems();
    statusText.value = `已更新 ${data.saved} 条热点。`;
  } catch (error) {
    statusText.value = "采集失败，请检查网络或后端服务。";
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
  } finally {
    loading.value = false;
  }
}

function selectItem(item) {
  selectedItem.value = item;
  reportText.value = item.ai_report || "";
}

async function generateReport() {
  if (!selectedItem.value?.id) return;
  reportLoading.value = true;
  const data = await api(`/items/${selectedItem.value.id}/report`, { method: "POST" });
  reportText.value = data.report;
  reportLoading.value = false;
}

onMounted(loadItems);
</script>
