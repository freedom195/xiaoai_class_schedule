const SettingsPage = {
  props: ['children'],
  emits: ['reload-children', 'toast', 'xiaomi-status-changed'],
  template: `
<div class="page">
  <div class="page-title" style="margin-bottom:20px">⚙️ 设置</div>

  <!-- Xiaomi config -->
  <div class="card" style="margin-bottom:16px">
    <div style="font-size:14px;font-weight:600;margin-bottom:14px">小爱音箱配置</div>
    <div class="form-row">
      <label>小米账号（手机号或邮箱）</label>
      <input v-model="xiaomi.account" placeholder="your@email.com">
    </div>
    <div class="form-row">
      <label>密码</label>
      <input type="password" v-model="xiaomi.password" placeholder="••••••••">
    </div>
    <div class="form-row">
      <label>设备ID（mi_did）</label>
      <input v-model="xiaomi.device_id" placeholder="例：123456789">
      <div style="font-size:11px;color:var(--text3);margin-top:4px">可在米家 App 或小爱开放平台查看设备 ID</div>
    </div>
    <div style="display:flex;gap:8px;margin-top:4px">
      <button class="btn btn-primary" @click="saveXiaomi" :disabled="xiaomi.saving">
        {{xiaomi.saving ? '保存中...' : '保存并登录'}}
      </button>
      <button class="btn btn-ghost" @click="testXiaomi" :disabled="xiaomi.testing">
        {{xiaomi.testing ? '测试中...' : '测试连接'}}
      </button>
    </div>
    <div v-if="xiaomi.testResult" style="margin-top:8px;font-size:12px"
      :style="{color: xiaomi.testResult.ok ? 'var(--success)' : 'var(--danger)'}">
      <template v-if="xiaomi.testResult.ok">
        ✓ {{ xiaomi.testResult.device?.name }}
      </template>
      <template v-else>
        ✗ {{ xiaomi.testResult.error }}
        <div v-if="xiaomi.testResult.suggested_devices?.length" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px">
          <span v-for="d in xiaomi.testResult.suggested_devices"
            :key="d.deviceID" class="device-suggestion"
            @click="applyDeviceId(d.deviceID)"
            title="点击使用此设备">
            {{ d.name || d.deviceID }}
          </span>
        </div>
      </template>
    </div>
  </div>

  <!-- Children management -->
  <div class="card" style="margin-bottom:16px">
    <div style="font-size:14px;font-weight:600;margin-bottom:14px">孩子管理</div>
    <div v-for="c in children" :key="c.id" style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
      <input v-model="c._emoji" style="width:50px;background:var(--bg);border:1px solid var(--bg3);color:var(--text);border-radius:7px;padding:6px;text-align:center;font-size:20px">
      <input v-model="c._name" style="flex:1;background:var(--bg);border:1px solid var(--bg3);color:var(--text);border-radius:7px;padding:7px 10px;font-size:14px">
      <button v-if="isDirty(c)" class="btn btn-primary" @click="updateChild(c)">保存</button>
      <button class="btn btn-danger" @click="deleteChild(c)">删除</button>
    </div>
    <div style="display:flex;gap:8px;margin-top:8px">
      <input v-model="newChild.emoji" style="width:50px;background:var(--bg);border:1px solid var(--bg3);color:var(--text);border-radius:7px;padding:6px;text-align:center;font-size:20px" placeholder="👦">
      <input v-model="newChild.name" placeholder="新孩子姓名" style="flex:1;background:var(--bg);border:1px solid var(--bg3);color:var(--text);border-radius:7px;padding:7px 10px;font-size:14px">
      <button class="btn btn-success" @click="addChild">添加</button>
    </div>
  </div>

  <!-- Advance notice -->
  <div class="card">
    <div style="font-size:14px;font-weight:600;margin-bottom:14px">播报设置</div>
    <div class="form-row">
      <label>提前播报时间（分钟）</label>
      <input type="number" v-model.number="advanceMin" min="0" max="5" style="width:80px">
      <div style="font-size:11px;color:var(--text3);margin-top:4px">任务开始前提前几分钟播报，默认 1 分钟</div>
    </div>
  </div>
</div>`,

  setup(props, { emit }) {
    const { ref, onMounted } = Vue;

    const xiaomi = ref({ account: '', password: '', device_id: '', saving: false, testing: false, testResult: null });
    const newChild = ref({ name: '', emoji: '👦' });
    const advanceMin = ref(1);

    // Initialize editable copies on children
    function isDirty(c) {
      return c._name !== c.name || c._emoji !== c.avatar_emoji;
    }

    function initChildren() {
      props.children.forEach(c => {
        c._name = c.name;
        c._emoji = c.avatar_emoji;
      });
    }

    async function saveXiaomi() {
      xiaomi.value.saving = true;
      const res = await fetch('/api/config/xiaomi', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ account: xiaomi.value.account, password: xiaomi.value.password, device_id: xiaomi.value.device_id }),
      });
      const data = await res.json();
      xiaomi.value.saving = false;
      emit('toast', data.ok ? '小爱配置已保存并登录成功' : '登录失败，请检查账号密码', data.ok ? 'success' : 'warn');
      emit('xiaomi-status-changed');
    }

    async function testXiaomi() {
      xiaomi.value.testing = true;
      xiaomi.value.testResult = null;
      const res = await fetch('/api/config/xiaomi/test', { method: 'POST' });
      xiaomi.value.testResult = await res.json();
      xiaomi.value.testing = false;
    }

    function applyDeviceId(deviceId) {
      xiaomi.value.device_id = deviceId;
      emit('toast', '已替换设备ID，请点击"保存并登录"应用');
    }

    async function addChild() {
      if (!newChild.value.name.trim()) return;
      await fetch('/api/children', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ name: newChild.value.name, avatar_emoji: newChild.value.emoji }),
      });
      newChild.value = { name: '', emoji: '👦' };
      emit('reload-children');
      emit('toast', '已添加孩子');
    }

    async function updateChild(c) {
      await fetch(`/api/children/${c.id}`, {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ name: c._name, avatar_emoji: c._emoji }),
      });
      c.name = c._name;
      c.avatar_emoji = c._emoji;
      emit('reload-children');
      emit('toast', '已更新');
    }

    async function deleteChild(c) {
      if (!confirm(`确定删除 ${c.name}？相关课表和积分记录也会一并删除。`)) return;
      await fetch(`/api/children/${c.id}`, { method: 'DELETE' });
      emit('reload-children');
      emit('toast', '已删除', 'warn');
    }

    async function loadXiaomiConfig() {
      const res = await fetch('/api/config/xiaomi');
      if (res.ok) {
        const data = await res.json();
        xiaomi.value.account = data.account || '';
        xiaomi.value.device_id = data.device_id || '';
      }
    }

    onMounted(() => { initChildren(); loadXiaomiConfig(); });

    return { xiaomi, newChild, advanceMin, saveXiaomi, testXiaomi, addChild, updateChild, deleteChild, isDirty, applyDeviceId };
  }
};
