const StatsPage = {
  props: ['children'],
  template: `
<div class="page">
  <div class="page-header">
    <span class="page-title">📊 统计</span>
    <div style="display:flex;gap:8px;align-items:center">
      <button class="btn btn-ghost" @click="setRange(7)">近7天</button>
      <button class="btn btn-ghost" @click="setRange(30)">近30天</button>
      <select v-model="childId" style="background:var(--bg2);border:1px solid var(--bg3);color:var(--text);padding:6px 10px;border-radius:7px;font-size:13px">
        <option value="">所有孩子</option>
        <option v-for="c in children" :key="c.id" :value="c.id">{{c.avatar_emoji}} {{c.name}}</option>
      </select>
      <button class="btn btn-primary" @click="load">刷新</button>
    </div>
  </div>

  <div v-if="loading" style="text-align:center;padding:40px;color:var(--text2)">加载中...</div>
  <div v-else>
    <!-- Summary cards -->
    <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap">
      <div v-for="s in stats" :key="s.child_id" class="card" style="flex:1;min-width:160px;text-align:center">
        <div style="font-size:24px">{{s.avatar_emoji}}</div>
        <div style="font-weight:600;margin:4px 0">{{s.child_name}}</div>
        <div style="font-size:22px;font-weight:700;color:var(--success)">{{s.total_completed}}</div>
        <div style="font-size:11px;color:var(--text2)">完成 / {{s.total_scheduled}} 计划</div>
        <div style="font-size:13px;color:var(--warn);margin-top:6px">+{{s.total_points_earned}} 分</div>
        <div style="font-size:11px;color:var(--text2)">最长连续 {{s.longest_streak}} 天</div>
      </div>
    </div>

    <!-- Charts -->
    <div class="card" style="margin-bottom:16px">
      <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:12px">每日完成率</div>
      <canvas id="rate-chart" height="80"></canvas>
    </div>
  </div>
</div>`,

  setup(props) {
    const { ref, onMounted, watch } = Vue;

    const stats = ref([]);
    const loading = ref(false);
    const childId = ref('');
    let start = ref('');
    let end = ref('');
    let chart = null;

    function setRange(days) {
      const e = new Date();
      const s = new Date(e.getTime() - days * 86400000);
      end.value = e.toISOString().slice(0,10);
      start.value = s.toISOString().slice(0,10);
      load();
    }

    async function load() {
      loading.value = true;
      const params = new URLSearchParams();
      if (childId.value) params.set('child_id', childId.value);
      if (start.value) params.set('start', start.value);
      if (end.value) params.set('end', end.value);
      const res = await fetch('/api/stats?' + params);
      stats.value = await res.json();
      loading.value = false;
      drawChart();
    }

    function drawChart() {
      const ctx = document.getElementById('rate-chart');
      if (!ctx) return;
      if (chart) chart.destroy();

      const colors = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6'];
      const allDates = [...new Set(stats.value.flatMap(s => s.daily.map(d => d.date)))].sort();

      chart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: allDates,
          datasets: stats.value.map((s, i) => ({
            label: s.child_name,
            data: allDates.map(d => {
              const day = s.daily.find(x => x.date === d);
              return day ? Math.round(day.rate * 100) : null;
            }),
            borderColor: colors[i % colors.length],
            backgroundColor: colors[i % colors.length] + '22',
            tension: 0.3,
            fill: true,
            spanGaps: true,
          })),
        },
        options: {
          responsive: true,
          scales: {
            y: { min: 0, max: 100, ticks: { callback: v => v + '%', color: '#94a3b8' }, grid: { color: '#334155' } },
            x: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
          },
          plugins: { legend: { labels: { color: '#e2e8f0' } } },
        },
      });
    }

    onMounted(() => setRange(30));
    watch(childId, load);

    return { stats, loading, childId, setRange, load };
  }
};
