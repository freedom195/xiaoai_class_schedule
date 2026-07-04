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
      <input type="password" v-model="xiaomi.password" placeholder="请输入小米账号密码">
      <div style="font-size:11px;color:var(--text3);margin-top:4px">出于安全考虑密码不会预填，每次保存都需重新输入</div>
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
        <div v-if="xiaomi.testResult.verify_url" style="margin-top:8px;padding:8px;background:var(--bg);border-radius:7px;font-size:12px">
          <div style="margin-bottom:6px;color:var(--warning)">⚠️ 小米账号需要安全验证</div>
          <div style="margin-bottom:6px">1. 点击下方链接在浏览器中打开</div>
          <a :href="xiaomi.testResult.verify_url" target="_blank" style="color:var(--primary);word-break:break-all;text-decoration:underline;font-size:11px">{{ xiaomi.testResult.verify_url }}</a>
          <div style="margin-top:6px;margin-bottom:6px">2. 完成短信验证码验证</div>
          <div style="margin-bottom:4px;color:var(--text-secondary);font-size:11px">（验证后页面可能报错跳转，这是正常现象，验证已生效）</div>
          <div style="margin-bottom:6px">3. 回到此页面重新点击「保存并登录」</div>
          <div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--bg3);color:var(--text-secondary)">
            💡 如果反复验证仍无法登录，推荐使用下方的 Cookie 方式登录
          </div>
        </div>
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

  <!-- Cookie login (alternative to password) -->
  <div class="card" style="margin-bottom:16px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <div style="font-size:14px;font-weight:600">Cookie 方式登录（推荐）</div>
      <button class="btn btn-ghost" @click="cookieExpanded = !cookieExpanded" style="font-size:12px;padding:4px 10px">
        {{cookieExpanded ? '收起 ▲' : '展开 ▼'}}
      </button>
    </div>
    <div v-if="!cookieExpanded" style="font-size:12px;color:var(--text3)">
      如果密码登录触发安全验证无法通过，可使用 Cookie 方式登录，绕过验证。
      <span v-if="xiaomi.has_cookie" style="color:var(--success)">✓ 已配置 Cookie</span>
    </div>
    <div v-if="cookieExpanded">
      <div style="font-size:12px;color:var(--text3);margin-bottom:12px;line-height:1.6">
        <b>获取方法：</b><br>
        1. 在浏览器中打开 <a href="https://account.xiaomi.com" target="_blank" style="color:var(--primary)">https://account.xiaomi.com</a> 并登录小米账号<br>
        2. 按 F12 打开开发者工具 → Application(应用) → Cookies<br>
        3. 找到 <code style="background:var(--bg);padding:1px 4px;border-radius:3px">userId</code> 和 <code style="background:var(--bg);padding:1px 4px;border-radius:3px">passToken</code> 两个 Cookie 值<br>
        4. 复制到下方对应输入框，点击「Cookie 登录」
      </div>
      <div class="form-row">
        <label>userId</label>
        <input v-model="cookie.user_id" placeholder="从浏览器 Cookie 中获取 userId">
      </div>
      <div class="form-row">
        <label>passToken</label>
        <input v-model="cookie.pass_token" placeholder="从浏览器 Cookie 中获取 passToken">
      </div>
      <div style="display:flex;gap:8px;margin-top:4px">
        <button class="btn btn-primary" @click="saveXiaomiCookie" :disabled="cookie.saving">
          {{cookie.saving ? '登录中...' : 'Cookie 登录'}}
        </button>
      </div>
      <div v-if="cookie.result" style="margin-top:8px;font-size:12px"
        :style="{color: cookie.result.ok ? 'var(--success)' : 'var(--danger)'}">
        <template v-if="cookie.result.ok">✓ Cookie 登录成功</template>
        <template v-else>✗ {{ cookie.result.error }}</template>
      </div>
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

    const xiaomi = ref({ account: '', password: '', device_id: '', saving: false, testing: false, testResult: null, has_cookie: false });
    const cookie = ref({ user_id: '', pass_token: '', saving: false, result: null });
    const cookieExpanded = ref(false);
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
      if (!xiaomi.value.account.trim()) {
        emit('toast', '请填写小米账号', 'warn');
        return;
      }
      if (!xiaomi.value.password) {
        emit('toast', '请填写密码（密码框不会预填，需手动输入）', 'warn');
        return;
      }
      if (!xiaomi.value.device_id.trim()) {
        emit('toast', '请填写设备ID', 'warn');
        return;
      }
      xiaomi.value.saving = true;
      const res = await fetch('/api/config/xiaomi', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ account: xiaomi.value.account, password: xiaomi.value.password, device_id: xiaomi.value.device_id }),
      });
      const data = await res.json();
      xiaomi.value.saving = false;
      if (data.ok) {
        emit('toast', '小爱配置已保存并登录成功', 'success');
        xiaomi.value.testResult = null;
      } else {
        const errMsg = data.error || '登录失败，请检查账号密码';
        emit('toast', errMsg, 'warn');
        xiaomi.value.testResult = { ok: false, error: errMsg };
        if (data.verify_url) {
          xiaomi.value.testResult.verify_url = data.verify_url;
          cookieExpanded.value = true;
        }
      }
      emit('xiaomi-status-changed');
    }

    async function saveXiaomiCookie() {
      if (!cookie.value.user_id.trim()) {
        emit('toast', '请填写 userId', 'warn');
        return;
      }
      if (!cookie.value.pass_token.trim()) {
        emit('toast', '请填写 passToken', 'warn');
        return;
      }
      if (!xiaomi.value.device_id.trim()) {
        emit('toast', '请填写设备ID', 'warn');
        return;
      }
      cookie.value.saving = true;
      cookie.value.result = null;
      const res = await fetch('/api/config/xiaomi/cookie', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          pass_token: cookie.value.pass_token,
          user_id: cookie.value.user_id,
          device_id: xiaomi.value.device_id,
        }),
      });
      const data = await res.json();
      cookie.value.saving = false;
      cookie.value.result = data;
      if (data.ok) {
        emit('toast', 'Cookie 登录成功', 'success');
        xiaomi.value.has_cookie = true;
      } else {
        emit('toast', data.error || 'Cookie 登录失败', 'warn');
      }
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
        xiaomi.value.has_cookie = data.has_cookie || false;
        if (data.cookie_user_id) {
          cookie.value.user_id = data.cookie_user_id;
        }
      }
    }

    onMounted(() => { initChildren(); loadXiaomiConfig(); });

    return { xiaomi, cookie, cookieExpanded, newChild, advanceMin, saveXiaomi, saveXiaomiCookie, testXiaomi, addChild, updateChild, deleteChild, isDirty, applyDeviceId };
  }
};
