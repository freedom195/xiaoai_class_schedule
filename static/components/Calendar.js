const TASK_TYPES = [
  { value: 'study',        label: '学习',    color: '#3b82f6', emoji: '📖', defaultPoints: 10 },
  { value: 'screen',       label: '电子产品', color: '#f97316', emoji: '📱', defaultPoints: 10 },
  { value: 'exercise',     label: '运动',    color: '#10b981', emoji: '🏃', defaultPoints: 20 },
  { value: 'rest',         label: '休息',    color: '#64748b', emoji: '😴', defaultPoints: 0 },
  { value: 'eye_exercise', label: '眼保健操', color: '#0ea5e9', emoji: '👁️', defaultPoints: 10 },
  { value: 'custom',       label: '其他',    color: '#8b5cf6', emoji: '✨', defaultPoints: 10 },
];

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

const CalendarPage = {
  props: ['children'],
  emits: ['toast'],
  template: `
<div class="page">
  <div class="page-header">
    <span class="page-title">📅 课表</span>
    <div style="display:flex;gap:8px;align-items:center">
      <select v-model="selectedChildId" style="background:var(--bg2);border:1px solid var(--bg3);color:var(--text);padding:6px 10px;border-radius:7px;font-size:13px">
        <option value="">所有孩子</option>
        <option v-for="c in children" :key="c.id" :value="c.id">{{c.avatar_emoji}} {{c.name}}</option>
      </select>
      <button class="btn btn-ghost" @click="calView='timeGridDay'; refreshCal()">日视图</button>
      <button class="btn btn-ghost" @click="calView='timeGridWeek'; refreshCal()">周视图</button>
      <button class="btn btn-primary" @click="openCreate()">+ 新建任务</button>
      <button class="btn btn-ghost" @click="clearModal.open=true" style="color:var(--danger);border:1px solid var(--danger)20">🗑 清除课程</button>
    </div>
  </div>
  <div id="calendar-el" style="flex:1;min-height:0;background:var(--bg2);border-radius:var(--radius);padding:12px;border:1px solid var(--bg3)"></div>

  <!-- Create/Edit Modal -->
  <div class="modal-overlay" v-if="modal.open" @click.self="modal.open=false">
    <div class="modal" style="width:500px;max-height:90vh;overflow-y:auto">
      <h3>{{ modal.id ? '编辑任务' : '新建任务' }}</h3>

      <!-- Quick type buttons -->
      <div class="form-row">
        <label>任务类型（快捷）</label>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <div v-for="t in TASK_TYPES" :key="t.value"
            @click="applyType(t)"
            style="cursor:pointer;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:600;transition:opacity .15s;border:2px solid transparent"
            :style="{background: modal.task_type===t.value ? t.color : t.color+'22',
                     color: modal.task_type===t.value ? 'white' : t.color,
                     borderColor: modal.task_type===t.value ? t.color : 'transparent'}">
            {{t.emoji}} {{t.label}}
          </div>
        </div>
      </div>

      <div class="form-row">
        <label>小朋友</label>
        <select v-model="modal.child_id">
          <option v-for="c in children" :key="c.id" :value="c.id">{{c.avatar_emoji}} {{c.name}}</option>
        </select>
      </div>
      <div class="form-row">
        <label>任务名称</label>
        <input v-model="modal.title" placeholder="例：数学练习" @input="autoKeywords">
      </div>
      <div class="form-row">
        <label>开始时间</label>
        <input type="datetime-local" v-model="modal.start_time">
      </div>
      <div class="form-row">
        <label>时长（分钟）</label>
        <input type="number" v-model.number="modal.duration" min="1" max="300" placeholder="例：30">
      </div>

      <!-- Recurrence -->
      <div class="form-row">
        <label>重复规则</label>
        <div style="display:flex;gap:8px;margin-bottom:8px">
          <div v-for="opt in [{v:'none',l:'仅当天'},{v:'daily',l:'每天'},{v:'weekly',l:'每周几'}]" :key="opt.v"
            @click="modal.recurrence_type=opt.v"
            style="cursor:pointer;padding:5px 14px;border-radius:20px;font-size:12px;font-weight:600"
            :style="{background: modal.recurrence_type===opt.v ? 'var(--accent)' : 'var(--bg3)',
                     color: modal.recurrence_type===opt.v ? 'white' : 'var(--text2)'}">
            {{opt.l}}
          </div>
        </div>
        <!-- Weekday picker -->
        <div v-if="modal.recurrence_type==='weekly'" style="display:flex;gap:6px;flex-wrap:wrap">
          <div v-for="(d, i) in WEEKDAYS" :key="i"
            @click="toggleWeekday(i)"
            style="cursor:pointer;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600"
            :style="{background: modal.recurrence_days.includes(i) ? 'var(--accent)' : 'var(--bg3)',
                     color: modal.recurrence_days.includes(i) ? 'white' : 'var(--text2)'}">
            {{d}}
          </div>
        </div>
      </div>

      <div class="form-row">
        <label>颜色</label>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <div v-for="c in COLORS" :key="c" @click="modal.color=c"
            style="width:26px;height:26px;border-radius:6px;cursor:pointer;transition:transform .1s"
            :style="{background:c, outline: modal.color===c ? '2px solid white' : 'none', transform: modal.color===c ? 'scale(1.2)' : 'scale(1)'}"></div>
        </div>
      </div>
      <div class="form-row">
        <label>积分奖励</label>
        <input type="number" v-model.number="modal.points_reward" min="0" max="100">
      </div>
      <div class="form-row">
        <label>语音关键词（空格分隔）</label>
        <input v-model="modal.keywords_str" placeholder="数学 数学练习">
      </div>
      <div class="form-row">
        <label>备注（播报时附加）</label>
        <input v-model="modal.notes" placeholder="可选">
      </div>
      <div class="form-actions">
        <button class="btn btn-ghost" @click="modal.open=false">取消</button>
        <button v-if="modal.id && !modal.completed && modal.for_date === todayStr()" class="btn btn-success" @click="completeItem">
          ✓ 完成
        </button>
        <span v-if="modal.id && modal.completed && modal.for_date === todayStr()" style="color:var(--success);font-weight:600;font-size:13px;margin-right:8px">已完成 ✓</span>
        <button v-if="modal.id" class="btn btn-danger-outline" @click="deleteItem(false)">
          {{ modal.recurrence_type !== 'none' ? '删除本次' : '删除' }}
        </button>
        <button v-if="modal.id && modal.recurrence_type !== 'none'" class="btn btn-danger" @click="deleteItem(true)">
          删除全部重复
        </button>
        <button class="btn btn-primary" @click="saveItem">保存</button>
      </div>
    </div>
  </div>

  <!-- Clear Modal -->
  <div class="modal-overlay" v-if="clearModal.open" @click.self="clearModal.open=false">
    <div class="modal" style="width:420px">
      <h3>🗑 清除课程</h3>
      <p style="font-size:13px;color:var(--text2);margin-bottom:16px">删除指定日期范围内的所有课程（包括重复课程的模板）</p>

      <!-- Quick options -->
      <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
        <button class="btn btn-ghost" @click="setQuickRange('today')">今天起</button>
        <button class="btn btn-ghost" @click="setQuickRange('tomorrow')">明天起</button>
        <button class="btn btn-ghost" @click="setQuickRange('this_week')">本周剩余</button>
        <button class="btn btn-ghost" @click="setQuickRange('this_month')">本月剩余</button>
      </div>

      <div class="form-row">
        <label>开始日期</label>
        <input type="date" v-model="clearModal.start_date">
      </div>
      <div class="form-row">
        <label>结束日期</label>
        <input type="date" v-model="clearModal.end_date">
      </div>
      <div class="form-row">
        <label>筛选孩子（可选）</label>
        <select v-model="clearModal.child_id">
          <option value="">全部孩子</option>
          <option v-for="c in children" :key="c.id" :value="c.id">{{c.avatar_emoji}} {{c.name}}</option>
        </select>
      </div>

      <div style="background:#3a1e1e;border:1px solid var(--danger)40;border-radius:8px;padding:10px 12px;font-size:12px;color:#fca5a5;margin-bottom:16px">
        ⚠️ 此操作不可撤销。重复课程（每天/每周几）的模板也会被删除，所有日期的实例均不再出现。
      </div>

      <div class="form-actions">
        <button class="btn btn-ghost" @click="clearModal.open=false">取消</button>
        <button class="btn btn-danger" @click="confirmClear" :disabled="clearModal.loading">
          {{ clearModal.loading ? '删除中...' : '确认删除' }}
        </button>
      </div>
    </div>
  </div>
</div>`,

  setup(props, { emit }) {
    const { ref, onMounted, watch } = Vue;

    const COLORS = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16','#64748b','#0ea5e9'];

    const selectedChildId = ref('');
    const calView = ref('timeGridDay');
    let calendar = null;

    const modal = ref({
      open: false, id: null, child_id: '', task_type: 'study',
      title: '', start_time: '', duration: 60, for_date: '', completed: false,
      color: '#3b82f6', points_reward: 10, keywords_str: '', notes: '',
      recurrence_type: 'none', recurrence_days: [],
    });

    function todayStr() {
      return new Date().toISOString().slice(0, 10);
    }

    const clearModal = ref({
      open: false, loading: false,
      start_date: todayStr(), end_date: todayStr(), child_id: '',
    });

    function setQuickRange(preset) {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const fmt = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
      const today = fmt(now);
      if (preset === 'today') {
        clearModal.value.start_date = today;
        clearModal.value.end_date = today;
      } else if (preset === 'tomorrow') {
        const tom = new Date(now); tom.setDate(tom.getDate() + 1);
        clearModal.value.start_date = fmt(tom);
        clearModal.value.end_date = fmt(tom);
      } else if (preset === 'this_week') {
        const dow = now.getDay() || 7;          // 1=Mon..7=Sun
        const sun = new Date(now); sun.setDate(now.getDate() + (7 - dow));
        clearModal.value.start_date = today;
        clearModal.value.end_date = fmt(sun);
      } else if (preset === 'this_month') {
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        clearModal.value.start_date = today;
        clearModal.value.end_date = fmt(lastDay);
      }
    }

    async function confirmClear() {
      const cm = clearModal.value;
      if (!cm.start_date || !cm.end_date) return;
      if (cm.start_date > cm.end_date) {
        alert('开始日期不能晚于结束日期');
        return;
      }
      cm.loading = true;
      const res = await fetch('/api/schedule/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: cm.start_date,
          end_date: cm.end_date,
          child_id: cm.child_id || null,
          include_recurring: true,
        }),
      });
      const data = await res.json();
      cm.loading = false;
      cm.open = false;
      calendar?.refetchEvents();
      const msg = `已删除 ${data.total} 个课程`
        + (data.deleted_recurring ? `（含 ${data.deleted_recurring} 个重复模板）` : '');
      emit('toast', msg, data.total > 0 ? 'warn' : 'success');
    }

    function toLocalDT(dt) {
      const d = new Date(dt);
      const pad = n => String(n).padStart(2,'0');
      return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    function applyType(t) {
      modal.value.task_type = t.value;
      modal.value.color = t.color;
      if (!modal.value.id && !modal.value.title) {
        if (t.value === 'rest') { modal.value.title = '休息时间'; modal.value.keywords_str = '休息'; modal.value.points_reward = 5; }
        if (t.value === 'eye_exercise') { modal.value.title = '眼保健操'; modal.value.keywords_str = '眼保健操 眼操'; modal.value.points_reward = 10; }
      }
    }

    function toggleWeekday(i) {
      const days = modal.value.recurrence_days;
      const idx = days.indexOf(i);
      if (idx >= 0) days.splice(idx, 1);
      else days.push(i);
    }

    function addMinutes(dtStr, minutes) {
      const d = new Date(dtStr);
      d.setMinutes(d.getMinutes() + minutes);
      return toLocalDT(d);
    }

    function getDurationMinutes(startStr, endStr) {
      const s = new Date(startStr);
      const e = new Date(endStr);
      return Math.round((e - s) / 60000);
    }

    function openCreate(start, end) {
      const now = new Date();
      const s = start ? toLocalDT(start) : toLocalDT(new Date(now.getTime() + 5*60000));
      const dur = (start && end) ? getDurationMinutes(toLocalDT(start), toLocalDT(end)) : 60;
      modal.value = {
        open: true, id: null,
        child_id: props.children[0]?.id || '',
        task_type: 'study', title: '',
        start_time: s, duration: dur,
        color: '#3b82f6', points_reward: TASK_TYPES.find(t=>t.value==='study')?.defaultPoints ?? 10, keywords_str: '', notes: '',
        recurrence_type: 'none', recurrence_days: [],
      };
    }

    function openEdit(item) {
      const rd = item.extendedProps.recurrence_days || [];
      const s = toLocalDT(item.start);
      const e = toLocalDT(item.end || item.start);
      modal.value = {
        open: true, id: item.extendedProps.item_id,
        child_id: item.extendedProps.child_id,
        task_type: item.extendedProps.task_type || 'study',
        title: item.title.replace(/ ↻$/, '').replace(/ ✏️$/, ''),
        start_time: s,
        duration: getDurationMinutes(s, e),
        for_date: item.extendedProps.completion_date || '',
        completed: item.extendedProps.completed || false,
        color: item.backgroundColor || '#3b82f6',
        points_reward: item.extendedProps.points_reward,
        keywords_str: (item.extendedProps.keywords || []).join(' '),
        notes: item.extendedProps.notes || '',
        recurrence_type: item.extendedProps.recurrence_type || 'none',
        recurrence_days: [...rd],
      };
    }

    function autoKeywords() {
      if (!modal.value.keywords_str) {
        modal.value.keywords_str = modal.value.title;
      }
    }

    async function loadEvents(fetchInfo, successCb) {
      const params = new URLSearchParams({
        start: fetchInfo.startStr.slice(0,19),
        end: fetchInfo.endStr.slice(0,19),
      });
      if (selectedChildId.value) params.set('child_id', selectedChildId.value);
      const res = await fetch('/api/schedule?' + params);
      const items = await res.json();
      successCb(items.map(i => ({
        id: i.id + '-' + i.start_time.slice(0,10),
        title: i.title + (i.completed ? ' ✓' : '') + (i.voice_modified ? ' ✏️' : ''),
        start: i.start_time,
        end: i.end_time,
        backgroundColor: i.color,
        textColor: '#fff',
        extendedProps: {
          item_id: i.id, child_id: i.child_id, task_type: i.task_type,
          keywords: i.keywords, points_reward: i.points_reward,
          notes: i.notes, completed: i.completed,
          recurrence_type: i.recurrence_type,
          recurrence_days: i.recurrence_days,
          completion_date: i.completion_date,
          voice_modified: i.voice_modified || false,
          original_title: i.original_title || '',
        },
        classNames: [
          ...(i.completed ? ['completed-event'] : []),
          ...(i.voice_modified ? ['voice-modified-event'] : []),
        ],
        opacity: i.completed ? 0.6 : 1,
      })));
    }

    function refreshCal() {
      if (calendar) {
        calendar.changeView(calView.value);
        calendar.refetchEvents();
      }
    }

    async function saveItem(force = false) {
      const m = modal.value;
      if (!m.title.trim()) { alert('请填写任务名称'); return; }
      if (!m.duration || m.duration <= 0) { alert('时长必须大于 0 分钟'); return; }

      const end_time = addMinutes(m.start_time, m.duration);

      const body = {
        child_id: m.child_id,
        title: m.title,
        task_type: m.task_type,
        start_time: m.start_time,
        end_time: end_time,
        color: m.color,
        points_reward: m.points_reward,
        xp_reward: m.points_reward,
        keywords: m.keywords_str.split(/\s+/).filter(Boolean),
        notes: m.notes,
        recurrence_type: m.recurrence_type,
        recurrence_days: m.recurrence_type === 'weekly' ? m.recurrence_days : [],
      };

      // Conflict check (skip if user already confirmed)
      if (!force) {
        const params = m.id ? `?exclude_id=${m.id}` : '';
        const chkRes = await fetch('/api/schedule/check-conflict' + params, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const chk = await chkRes.json();
        if (chk.has_conflict) {
          const names = chk.conflicts.map(c => {
            const s = c.start_time.slice(11, 16);
            const e = c.end_time.slice(11, 16);
            return `「${c.title}」(${s}-${e})`;
          }).join('、');
          const ok = confirm(`该时段与以下课程时间重叠：\n${names}\n\n确定仍要保存吗？`);
          if (!ok) return;
        }
      }

      const url = m.id ? `/api/schedule/${m.id}` : '/api/schedule';
      const method = m.id ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (res.ok) {
        modal.value.open = false;
        calendar?.refetchEvents();
        emit('toast', m.id ? '任务已更新' : '任务已创建');
      }
    }

    async function completeItem() {
      const m = modal.value;
      if (!confirm(`确认完成「${m.title}」？`)) return;
      const resp = await fetch('/api/completions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          schedule_item_id: m.id,
          child_id: m.child_id,
          completion_date: m.for_date || undefined,
        }),
      });
      if (resp.ok) {
        m.completed = true;
        calendar?.refetchEvents();
        emit('toast', '课程已完成！', 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        emit('toast', err.detail || '操作失败', 'error');
      }
    }

    async function deleteItem(deleteAll) {
      const m = modal.value;
      const label = deleteAll
        ? '删除此重复任务的所有日期实例？'
        : '删除本次课程？';
      if (!confirm(label)) return;

      let url = `/api/schedule/${m.id}`;
      if (!deleteAll && m.for_date && m.recurrence_type !== 'none') {
        url += `?date=${m.for_date}`;
      }
      const resp = await fetch(url, { method: 'DELETE' });
      if (resp.ok) {
        m.open = false;
        calendar?.refetchEvents();
        emit('toast', deleteAll ? '所有重复课程已删除' : '本次课程已删除', 'warn');
      } else {
        const err = await resp.json().catch(() => ({}));
        emit('toast', err.detail || '删除失败', 'error');
      }
    }

    onMounted(() => {
      const el = document.getElementById('calendar-el');
      calendar = new FullCalendar.Calendar(el, {
        initialView: calView.value,
        locale: 'zh-cn',
        headerToolbar: { left: 'prev,next today', center: 'title', right: '' },
        height: 'auto',
        slotMinTime: '06:00:00',
        slotMaxTime: '22:00:00',
        nowIndicator: true,
        editable: true,
        selectable: true,
        slotEventOverlap: false,
        events: loadEvents,
        select: (info) => openCreate(info.start, info.end),
        eventClick: (info) => openEdit(info.event),
        eventDrop: async (info) => {
          await fetch(`/api/schedule/${info.event.extendedProps.item_id}`, {
            method: 'PUT',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ start_time: info.event.startStr, end_time: info.event.endStr }),
          });
        },
        eventResize: async (info) => {
          await fetch(`/api/schedule/${info.event.extendedProps.item_id}`, {
            method: 'PUT',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ end_time: info.event.endStr }),
          });
        },
      });
      calendar.render();
    });

    watch(selectedChildId, () => calendar?.refetchEvents());

    // Auto-fill default points when task type changes
    watch(() => modal.value.task_type, (newType) => {
      const t = TASK_TYPES.find(t => t.value === newType);
      if (t) modal.value.points_reward = t.defaultPoints;
    });

    return {
      selectedChildId, calView, modal, COLORS, TASK_TYPES, WEEKDAYS,
      clearModal, setQuickRange, confirmClear,
      openCreate, openEdit, autoKeywords, applyType, toggleWeekday,
      saveItem, completeItem, deleteItem, refreshCal,
      todayStr,
    };
  }
};
