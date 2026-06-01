const RedemptionPage = {
  props: ['children'],
  emits: ['pending-count', 'toast'],
  template: `
<div class="page">
  <div class="page-header">
    <span class="page-title">🎁 兑换中心</span>
    <button class="btn btn-primary" @click="modal.open=true">申请兑换</button>
  </div>

  <!-- Pending approvals -->
  <div v-if="pending.length" class="card" style="margin-bottom:20px">
    <div style="font-size:13px;font-weight:600;color:var(--warn);margin-bottom:12px">⏳ 待审批 ({{pending.length}})</div>
    <div v-for="r in pending" :key="r.id" style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--bg3)">
      <div style="flex:1">
        <div style="font-weight:600">{{childName(r.child_id)}} → {{r.reward_name}}</div>
        <div style="font-size:12px;color:var(--text2);margin-top:2px">消耗 {{r.points_cost}} 积分 · {{fmtDate(r.created_at)}}</div>
      </div>
      <button class="btn btn-success" @click="review(r.id,'approved')">通过</button>
      <button class="btn btn-danger" @click="review(r.id,'rejected')">拒绝</button>
    </div>
  </div>

  <!-- History -->
  <div class="card">
    <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:12px">历史记录</div>
    <div v-for="r in history" :key="r.id" style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--bg3)">
      <div style="flex:1">
        <div>{{childName(r.child_id)}} → {{r.reward_name}}</div>
        <div style="font-size:12px;color:var(--text2)">{{r.points_cost}} 积分 · {{fmtDate(r.created_at)}}</div>
        <div v-if="r.parent_note" style="font-size:12px;color:var(--accent2);margin-top:2px">家长留言：{{r.parent_note}}</div>
      </div>
      <span :style="{padding:'3px 10px',borderRadius:'20px',fontSize:'12px',
        background: r.status==='approved' ? '#1e3a1e' : '#3a1e1e',
        color: r.status==='approved' ? 'var(--success)' : 'var(--danger)'}">
        {{r.status === 'approved' ? '✓ 已通过' : '✗ 已拒绝'}}
      </span>
    </div>
    <div v-if="!history.length" style="text-align:center;color:var(--text2);padding:20px">暂无记录</div>
  </div>

  <!-- Create modal -->
  <div class="modal-overlay" v-if="modal.open" @click.self="modal.open=false">
    <div class="modal">
      <h3>申请兑换奖励</h3>
      <div class="form-row">
        <label>小朋友</label>
        <select v-model="modal.child_id">
          <option v-for="c in children" :key="c.id" :value="c.id">{{c.avatar_emoji}} {{c.name}} ({{c.available_points}}分)</option>
        </select>
      </div>
      <div class="form-row">
        <label>奖励内容</label>
        <input v-model="modal.reward_name" placeholder="例：看电视30分钟">
      </div>
      <div class="form-row">
        <label>消耗积分</label>
        <input type="number" v-model.number="modal.points_cost" min="1">
      </div>
      <div class="form-actions">
        <button class="btn btn-ghost" @click="modal.open=false">取消</button>
        <button class="btn btn-primary" @click="submit">提交申请</button>
      </div>
    </div>
  </div>
</div>`,

  setup(props, { emit }) {
    const { ref, onMounted } = Vue;

    const pending = ref([]);
    const history = ref([]);
    const modal = ref({ open: false, child_id: '', reward_name: '', points_cost: 50 });

    function childName(id) {
      const c = props.children.find(x => x.id === id);
      return c ? `${c.avatar_emoji} ${c.name}` : '?';
    }

    function fmtDate(dt) {
      return new Date(dt).toLocaleString('zh-CN', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' });
    }

    async function load() {
      const [pendingRes, histRes] = await Promise.all([
        fetch('/api/redemptions?status=pending'),
        fetch('/api/redemptions?status=approved'),
      ]);
      const rejectedRes = await fetch('/api/redemptions?status=rejected');
      pending.value = await pendingRes.json();
      const approved = await histRes.json();
      const rejected = await rejectedRes.json();
      history.value = [...approved, ...rejected].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      emit('pending-count', pending.value.length);
    }

    async function review(id, status) {
      await fetch(`/api/redemptions/${id}`, {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ status }),
      });
      emit('toast', status === 'approved' ? '已通过申请' : '已拒绝申请', status === 'approved' ? 'success' : 'warn');
      load();
    }

    async function submit() {
      const res = await fetch('/api/redemptions', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(modal.value),
      });
      if (res.ok) {
        modal.value.open = false;
        emit('toast', '申请已提交，等待家长审批');
        load();
      } else {
        const err = await res.json();
        emit('toast', err.detail || '提交失败', 'warn');
      }
    }

    onMounted(load);

    return { pending, history, modal, childName, fmtDate, review, submit, load };
  }
};
