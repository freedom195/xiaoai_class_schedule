const LogsPage = {
  template: `
<div class="page">
  <div class="page-header">
    <span class="page-title">📋 事件日志</span>
    <div style="display:flex;gap:8px;align-items:center">
      <select v-model="selectedDate" @change="load" style="background:var(--bg2);border:1px solid var(--bg3);color:var(--text);padding:6px 10px;border-radius:7px;font-size:13px">
        <option v-for="d in dates" :key="d" :value="d">{{d}}</option>
        <option v-if="!dates.length" value="">暂无日志</option>
      </select>
      <button class="btn btn-primary" @click="load">刷新</button>
    </div>
  </div>

  <div v-if="loading" style="text-align:center;padding:40px;color:var(--text2)">加载中...</div>
  <div v-else-if="!lines.length" class="card" style="text-align:center;padding:30px;color:var(--text2)">
    暂无事件记录
  </div>
  <div v-else class="card" style="padding:12px 16px;font-family:monospace;font-size:12px;line-height:1.8;max-height:calc(100vh - 160px);overflow-y:auto">
    <div v-for="(line, i) in lines" :key="i" style="white-space:pre-wrap;word-break:break-all"
      :style="{color: lineColor(line)}">{{ line }}</div>
  </div>
</div>`,

  setup() {
    const { ref, onMounted } = Vue;

    const dates = ref([]);
    const selectedDate = ref('');
    const lines = ref([]);
    const loading = ref(false);

    function lineColor(line) {
      if (line.includes('COMPLETION')) return 'var(--success)';
      if (line.includes('VOICE')) return 'var(--accent2)';
      if (line.includes('SCHEDULE')) return 'var(--warn)';
      if (line.includes('CHILD')) return 'var(--accent)';
      if (line.includes('REDEMPTION')) return '#ec4899';
      return 'var(--text2)';
    }

    async function loadDates() {
      const res = await fetch('/api/logs/dates');
      const data = await res.json();
      dates.value = data.dates;
      if (data.dates.length && !selectedDate.value) {
        selectedDate.value = data.dates[0];
      }
    }

    async function load() {
      if (!selectedDate.value) return;
      loading.value = true;
      const res = await fetch('/api/logs?date=' + selectedDate.value);
      const data = await res.json();
      lines.value = data.lines || [];
      loading.value = false;
    }

    onMounted(async () => {
      await loadDates();
      if (selectedDate.value) await load();
    });

    return { dates, selectedDate, lines, loading, load, lineColor };
  }
};
