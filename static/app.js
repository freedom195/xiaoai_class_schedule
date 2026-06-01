const { createApp, ref, onMounted } = Vue;

const app = createApp({
  setup() {
    const page = ref('calendar');
    const children = ref([]);
    const toasts = ref([]);
    const pendingCount = ref(0);
    const wsConnected = ref(false);
    const xiaomiConnected = ref(false);
    const xiaomiConfigured = ref(false);

    let toastId = 0;
    function showToast(msg, type = 'success') {
      const id = ++toastId;
      toasts.value.push({ id, msg, type });
      setTimeout(() => {
        toasts.value = toasts.value.filter(t => t.id !== id);
      }, 4000);
    }

    async function loadChildren() {
      const res = await fetch('/api/children');
      children.value = await res.json();
    }

    async function loadRedemptions() {
      const res = await fetch('/api/redemptions?status=pending');
      const data = await res.json();
      pendingCount.value = data.length;
    }

    async function checkXiaomiStatus() {
      try {
        const res = await fetch('/api/config/xiaomi/status');
        const data = await res.json();
        xiaomiConfigured.value = data.configured;
        xiaomiConnected.value = data.connected;
      } catch (e) {
        xiaomiConnected.value = false;
      }
    }

    function connectWS() {
      const ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onopen = () => { wsConnected.value = true; };
      ws.onclose = () => {
        wsConnected.value = false;
        setTimeout(connectWS, 3000);
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'completion') {
          const badges = msg.new_badges.map(b => ({
            streak_7:'🔥坚持7天', reader:'📚阅读达人', athlete:'🏃运动健将',
            musician:'🎵音乐达人', perfect_day:'⭐全勤王', overachiever:'🚀超额完成'
          }[b] || b)).join(' ');
          showToast(`🎉 完成「${msg.task_title}」+${msg.points_awarded}分！${badges}`, 'success');
          loadChildren();
          loadRedemptions();
        }
        if (msg.type === 'new_redemption') {
          pendingCount.value++;
          showToast('🎁 有新的兑换申请待审批', 'warn');
        }
        if (msg.type === 'xiaomi_status') {
          xiaomiConnected.value = msg.connected;
        }
      };
    }

    onMounted(() => {
      loadChildren();
      loadRedemptions();
      checkXiaomiStatus();
      connectWS();
      // Re-check Xiaomi status every 30s
      setInterval(checkXiaomiStatus, 30000);
    });

    return { page, children, toasts, pendingCount, wsConnected, xiaomiConnected, xiaomiConfigured, showToast, loadChildren, loadRedemptions, checkXiaomiStatus };
  }
});

app.component('calendar-page', CalendarPage);
app.component('leaderboard-page', LeaderboardPage);
app.component('stats-page', StatsPage);
app.component('redemption-page', RedemptionPage);
app.component('settings-page', SettingsPage);

app.mount('#app');
