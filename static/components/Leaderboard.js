const BADGE_META = {
  streak_7:   { emoji: '🔥', name: '坚持7天' },
  reader:     { emoji: '📚', name: '阅读达人' },
  athlete:    { emoji: '🏃', name: '运动健将' },
  musician:   { emoji: '🎵', name: '音乐达人' },
  perfect_day:{ emoji: '⭐', name: '全勤王' },
  overachiever:{ emoji: '🚀', name: '超额完成' },
};
const ALL_BADGES = Object.keys(BADGE_META);

const LEVEL_META = [
  { min: 0,    level: 1, title: '暑假新星',  next: 200 },
  { min: 200,  level: 2, title: '学习小达人', next: 500 },
  { min: 500,  level: 3, title: '知识探索者', next: 1000 },
  { min: 1000, level: 4, title: '暑期冠军',  next: 2000 },
  { min: 2000, level: 5, title: '传奇学霸',  next: null },
];

function levelInfo(xp) {
  let cur = LEVEL_META[0];
  for (const l of LEVEL_META) { if (xp >= l.min) cur = l; }
  const pct = cur.next ? Math.min(100, ((xp - cur.min) / (cur.next - cur.min)) * 100) : 100;
  return { ...cur, pct };
}

const LeaderboardPage = {
  props: ['children'],
  emits: ['reload-children', 'toast'],
  template: `
<div class="page">
  <div class="page-header">
    <span class="page-title">🏆 积分榜</span>
  </div>

  <div style="display:flex;gap:16px;flex-wrap:wrap">
    <div v-for="(c, idx) in sorted" :key="c.id" class="card" style="flex:1;min-width:220px;cursor:pointer;transition:border-color .15s"
      :style="{borderColor: idx===0 ? 'var(--warn)' : idx===1 ? '#94a3b8' : idx===2 ? '#b45309' : 'var(--bg3)'}"
      @click="openDetail(c)">
      <div style="text-align:center;margin-bottom:12px">
        <div style="font-size:48px">{{c.avatar_emoji}}</div>
        <div style="font-weight:700;font-size:16px;margin-top:4px">{{c.name}}</div>
        <div style="font-size:12px;color:var(--text2);margin-top:2px">
          {{ idx===0 ? '🥇 第1名' : idx===1 ? '🥈 第2名' : idx===2 ? '🥉 第3名' : '第'+(idx+1)+'名' }}
        </div>
      </div>

      <!-- Level -->
      <div :style="{background:'var(--bg)',border:'1px solid var(--bg3)',borderRadius:'8px',padding:'10px 12px',marginBottom:'12px'}">
        <div style="font-size:12px;font-weight:600;color:var(--accent2)">Lv.{{levelInfo(c.total_xp).level}} {{levelInfo(c.total_xp).title}}</div>
        <div style="background:var(--bg3);border-radius:4px;height:6px;margin-top:6px;overflow:hidden">
          <div :style="{background:'linear-gradient(90deg,var(--accent),var(--accent2))',width:levelInfo(c.total_xp).pct+'%',height:'100%',borderRadius:'4px',transition:'width .5s'}"></div>
        </div>
        <div style="font-size:11px;color:var(--text3);margin-top:4px">
          {{c.total_xp}} XP
          <span v-if="levelInfo(c.total_xp).next"> → Lv.{{levelInfo(c.total_xp).level+1}} 需 {{levelInfo(c.total_xp).next}} XP</span>
          <span v-else>（满级）</span>
        </div>
      </div>

      <!-- Points -->
      <div style="text-align:center;margin-bottom:12px">
        <div style="font-size:28px;font-weight:700;color:var(--warn)">{{c.available_points}}</div>
        <div style="font-size:11px;color:var(--text2)">可用积分</div>
      </div>

      <!-- Badges -->
      <div style="display:flex;justify-content:center;gap:6px;flex-wrap:wrap">
        <span v-for="b in ALL_BADGES" :key="b"
          :title="BADGE_META[b].name"
          :style="{fontSize:'20px', opacity: earnedBadges(c).includes(b) ? 1 : 0.2}">
          {{BADGE_META[b].emoji}}
        </span>
      </div>
    </div>
  </div>

  <!-- Detail modal -->
  <div class="modal-overlay" v-if="detail.open" @click.self="detail.open=false">
    <div class="modal" style="width:520px;max-height:80vh;overflow:auto">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h3>{{detail.child?.avatar_emoji}} {{detail.child?.name}} — 积分明细</h3>
        <button class="btn btn-ghost" @click="detail.open=false">✕</button>
      </div>
      <div v-if="detail.loading" style="text-align:center;color:var(--text2);padding:20px">加载中...</div>
      <div v-else>
        <div v-for="t in detail.txns" :key="t.id" style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--bg3)">
          <div style="font-size:13px">{{t.reason}}</div>
          <div style="font-weight:700" :style="{color: t.delta>0 ? 'var(--success)' : 'var(--danger)'}">
            {{t.delta > 0 ? '+' : ''}}{{t.delta}}
          </div>
        </div>
        <div v-if="!detail.txns.length" style="text-align:center;color:var(--text2);padding:20px">还没有积分记录</div>
      </div>
    </div>
  </div>
</div>`,

  setup(props, { emit }) {
    const { ref, computed } = Vue;

    const badgeCache = ref({});
    const detail = ref({ open: false, child: null, txns: [], loading: false });

    const sorted = computed(() => [...props.children].sort((a, b) => b.total_xp - a.total_xp));

    function earnedBadges(child) {
      return badgeCache.value[child.id] || [];
    }

    async function loadBadges(child) {
      if (badgeCache.value[child.id]) return;
      const res = await fetch(`/api/points/${child.id}`);
      const data = await res.json();
      // Badges come from the child stats endpoint; for now we get them via completions
      // We'll fetch via a simple endpoint
    }

    async function openDetail(child) {
      detail.value = { open: true, child, txns: [], loading: true };
      const res = await fetch(`/api/points/${child.id}?limit=50`);
      const data = await res.json();
      detail.value.txns = data.transactions || [];
      detail.value.loading = false;
    }

    return { sorted, detail, ALL_BADGES, BADGE_META, levelInfo, earnedBadges, openDetail };
  }
};
