const $ = (id) => document.getElementById(id);

function toast(msg, isErr) {
  const el = $("toast");
  el.hidden = false;
  el.textContent = msg;
  el.classList.toggle("is-err", !!isErr);
  clearTimeout(el._t);
  el._t = setTimeout(() => {
    el.hidden = true;
  }, 2800);
}

async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { ...(opts.headers || {}) };
  if (method !== "GET" && method !== "HEAD" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, {
    ...opts,
    headers,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* ignore */
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || res.statusText || "请求失败";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function setPage(name) {
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("is-visible"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("is-active"));
  document.getElementById("page-" + name).classList.add("is-visible");
  document.querySelector('[data-page="' + name + '"]').classList.add("is-active");
  const titles = { console: "控制台", manage: "管理", plugins: "插件", logs: "日志", about: "关于" };
  $("pageTitle").textContent = titles[name] || "ZexBot";
  if (name === "about") {
    refreshAbout().catch(() => {});
  }
  if (name === "manage") {
    refreshGroupsUi().catch(() => {});
  }
  if (name === "plugins") {
    refreshPluginCatalog().catch(() => {});
  }
  if (name === "logs") {
    refreshLogs(false).catch(() => {});
    startLogsPollIfNeeded();
  } else {
    stopLogsPoll();
  }
}

async function loadMeta() {
  try {
    const m = await api("/api/meta");
    $("metaVer").textContent = `v${m.version}`;
  } catch {
    $("metaVer").textContent = "";
  }
}

async function refreshAbout() {
  const nameEl = $("aboutName");
  const verEl = $("aboutVersion");
  const authorEl = $("aboutAuthor");
  if (!nameEl || !verEl || !authorEl) return;
  try {
    const m = await api("/api/meta");
    nameEl.textContent = m.name || "ZexBot";
    verEl.textContent = m.version != null ? String(m.version) : "—";
    authorEl.textContent = m.author || "—";
  } catch {
    nameEl.textContent = "—";
    verEl.textContent = "—";
    authorEl.textContent = "—";
  }
}

async function loadConfigForm() {
  const c = await api("/api/config");
  $("wsUrl").value = c.ws_url || "";
  $("token").value = c.token || "";
  $("togglePrivate").checked = !!c.private_message_enabled;
}

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const pill = $("statusPill");
    const dot = $("statusDot");
    const txt = $("statusText");
    pill.classList.remove("is-on", "is-warn");
    if (s.running && s.connected) {
      pill.classList.add("is-on");
      txt.textContent = "运行中 · 已连接";
    } else if (s.running) {
      pill.classList.add("is-warn");
      txt.textContent = "运行中 · 未连接";
    } else {
      txt.textContent = "未运行";
    }
    $("connHint").textContent = s.running
      ? s.connected
        ? "与 OneBot 服务端通信正常。"
        : "正在尝试连接或已断开，请检查 WebSocket 与 LLBot 配置。"
      : "";
  } catch {
    $("statusText").textContent = "状态不可用";
  }
}

async function saveConfigFromForm() {
  const body = {
    ws_url: $("wsUrl").value.trim(),
    token: $("token").value,
  };
  await api("/api/config", { method: "PUT", body: JSON.stringify(body) });
  await api("/api/config/save", { method: "POST" });
  toast("配置已保存到磁盘");
}

async function reloadConfigDisk() {
  await api("/api/config/reload", { method: "POST" });
  await loadConfigForm();
  toast("已从磁盘重载配置");
}

async function startBot() {
  await saveConfigFromForm().catch(() => {});
  await api("/api/bot/start", { method: "POST" });
  toast("机器人已启动");
  await refreshStatus();
}

async function stopBot() {
  await api("/api/bot/stop", { method: "POST" });
  toast("机器人已关闭");
  await refreshStatus();
}

async function savePrivateToggle() {
  const enabled = $("togglePrivate").checked;
  await api("/api/config", {
    method: "PUT",
    body: JSON.stringify({ private_message_enabled: enabled }),
  });
  await api("/api/config/save", { method: "POST" });
  toast(enabled ? "已开启私聊处理" : "已关闭私聊处理");
}

async function refreshGroupsUi() {
  const data = await api("/api/groups");
  const le = $("listEnabled");
  const ld = $("listDisabled");
  le.innerHTML = "";
  ld.innerHTML = "";
  const mkItem = (g, isEnabled) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "gname";
    name.textContent = g.group_name || String(g.group_id);
    const gid = document.createElement("span");
    gid.className = "gid";
    gid.textContent = g.group_id;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mini " + (isEnabled ? "mini-on" : "mini-off");
    btn.textContent = isEnabled ? "停用" : "启用";
    btn.addEventListener("click", async () => {
      await api("/api/groups/toggle", {
        method: "POST",
        body: JSON.stringify({ group_id: g.group_id, enabled: !isEnabled }),
      });
      toast(isEnabled ? "已从启用列表移除" : "已加入启用列表");
      await refreshGroupsUi();
    });
    li.appendChild(name);
    li.appendChild(gid);
    li.appendChild(btn);
    return li;
  };
  data.enabled.forEach((g) => le.appendChild(mkItem(g, true)));
  data.disabled.forEach((g) => ld.appendChild(mkItem(g, false)));
  if (!data.connected && (data.enabled.length + data.disabled.length === 0)) {
    const li = document.createElement("li");
    li.textContent = "暂无数据，请先连接并点击「刷新群列表」。";
    ld.appendChild(li);
  }
}

async function pullGroupsFromApi() {
  await api("/api/groups/refresh", { method: "POST" });
  toast("群列表已更新");
  await refreshGroupsUi();
}

let logsPollTimer = null;
const LOG_POLL_MS = 2000;

function stopLogsPoll() {
  if (logsPollTimer) {
    clearInterval(logsPollTimer);
    logsPollTimer = null;
  }
}

function startLogsPollIfNeeded() {
  stopLogsPoll();
  const chk = $("toggleLogsRealtime");
  const page = document.getElementById("page-logs");
  if (chk && chk.checked && page && page.classList.contains("is-visible")) {
    logsPollTimer = setInterval(function () {
      refreshLogs(true).catch(function () {});
    }, LOG_POLL_MS);
  }
}

async function refreshLogs(autoScroll = false) {
  const { lines } = await api("/api/logs?limit=800");
  const box = $("logBox");
  box.textContent = (lines || []).join("\n");
  if (autoScroll && box) {
    box.scrollTop = box.scrollHeight;
  }
}

async function clearLogs() {
  await api("/api/logs/clear", { method: "POST", body: "{}" });
  toast("已清空内存日志");
  await refreshLogs(true);
}

function closePluginModal() {
  $("pluginModal").hidden = true;
  $("pluginModalFrame").src = "about:blank";
}

function openPluginConfig(symbol) {
  $("pluginModalTitle").textContent = "配置 · " + symbol;
  $("pluginModalFrame").src = "/api/plugins/" + encodeURIComponent(symbol) + "/admin";
  $("pluginModal").hidden = false;
}

async function refreshPluginCatalog() {
  const data = await api("/api/plugins");
  const plugins = data.plugins || [];
  const g = $("pluginGrid");
  g.innerHTML = "";
  if (!plugins.length) {
    g.innerHTML =
      '<p class="muted">暂无插件目录。请在 <code>zexbot/plugins</code> 下创建英文名称文件夹，并放入 <code>plugin.py</code>、<code>config.json</code>、按需添加 <code>admin</code>、<code>data</code> 等。</p>';
    return;
  }
  for (const p of plugins) {
    const card = document.createElement("article");
    card.className = "plugin-card" + (p.valid ? "" : " plugin-card-warn");
    const head = document.createElement("div");
    head.className = "plugin-card-head";
    const left = document.createElement("div");
    const h = document.createElement("h3");
    h.className = "plugin-card-title";
    h.textContent = p.title || p.symbol;
    left.appendChild(h);
    const tags = document.createElement("div");
    tags.className = "plugin-card-tags";
    const tLoad = document.createElement("span");
    tLoad.className =
      "plugin-tag " + (p.loaded ? "plugin-tag--load-yes" : "plugin-tag--load-no");
    tLoad.textContent = p.loaded ? "已加载" : "未加载";
    tags.appendChild(tLoad);
    const tAuth = document.createElement("span");
    const authLabel = p.author && String(p.author).trim() ? String(p.author).trim() : "未声明";
    tAuth.className =
      "plugin-tag " +
      (p.author && String(p.author).trim() ? "plugin-tag--author" : "plugin-tag--author-empty");
    tAuth.textContent = "作者：" + authLabel;
    tags.appendChild(tAuth);
    const tAdm = document.createElement("span");
    tAdm.className =
      "plugin-tag " + (p.has_admin ? "plugin-tag--admin-yes" : "plugin-tag--admin-no");
    tAdm.textContent = p.has_admin ? "含配置页" : "无配置页";
    tags.appendChild(tAdm);
    left.appendChild(tags);
    head.appendChild(left);
    card.appendChild(head);
    if (!p.valid && p.error) {
      const er = document.createElement("p");
      er.className = "plugin-card-err";
      er.textContent = p.error;
      card.appendChild(er);
    }
    if (p.load_error) {
      const le = document.createElement("p");
      le.className = "plugin-card-err";
      le.textContent = "加载失败：" + p.load_error;
      card.appendChild(le);
    }
    const row = document.createElement("div");
    row.className = "plugin-card-actions";
    const lab = document.createElement("label");
    lab.className = "plugin-toggle" + (p.enabled ? "" : " is-off");
    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = !!p.enabled;
    chk.disabled = !p.valid;
    chk.title = p.valid ? "插件开关" : "修正插件目录后即可启用";
    const sp = document.createElement("span");
    sp.textContent = p.enabled ? "已开启" : "已关闭";
    lab.appendChild(chk);
    lab.appendChild(sp);
    chk.addEventListener("change", async () => {
      try {
        await api("/api/plugins/" + encodeURIComponent(p.symbol) + "/enabled", {
          method: "PUT",
          body: JSON.stringify({ enabled: chk.checked }),
        });
        sp.textContent = chk.checked ? "已开启" : "已关闭";
        lab.classList.toggle("is-off", !chk.checked);
        toast(chk.checked ? "插件已开启" : "插件已关闭");
      } catch (e) {
        chk.checked = !chk.checked;
        toast(e.message, true);
      }
    });
    row.appendChild(lab);
    const cfgBtn = document.createElement("button");
    cfgBtn.type = "button";
    cfgBtn.className = "btn btn-blue btn-sm";
    cfgBtn.textContent = "配置";
    cfgBtn.disabled = !p.valid || !p.has_admin;
    cfgBtn.title = !p.has_admin ? "该插件未提供 admin 页面" : "";
    cfgBtn.addEventListener("click", () => openPluginConfig(p.symbol));
    row.appendChild(cfgBtn);
    card.appendChild(row);
    g.appendChild(card);
  }
}

function wire() {
  document.querySelectorAll(".nav-btn").forEach((b) => {
    b.addEventListener("click", () => setPage(b.dataset.page));
  });
  $("btnSaveCfg").addEventListener("click", () => saveConfigFromForm().catch((e) => toast(e.message, true)));
  $("btnReloadCfg").addEventListener("click", () => reloadConfigDisk().catch((e) => toast(e.message, true)));
  $("btnStart").addEventListener("click", () => startBot().catch((e) => toast(e.message, true)));
  $("btnStop").addEventListener("click", () => stopBot().catch((e) => toast(e.message, true)));
  $("togglePrivate").addEventListener("change", () => savePrivateToggle().catch((e) => toast(e.message, true)));
  $("btnRefreshGroups").addEventListener("click", () => pullGroupsFromApi().catch((e) => toast(e.message, true)));
  $("btnRefreshLogs").addEventListener("click", () =>
    refreshLogs(false).catch((e) => toast(e.message, true)),
  );
  $("btnClearLogs").addEventListener("click", () =>
    clearLogs().catch((e) => toast(e.message, true)),
  );
  $("toggleLogsRealtime").addEventListener("change", function () {
    startLogsPollIfNeeded();
    toast(this.checked ? "已开启实时刷新（每 2 秒）" : "已关闭实时刷新");
  });
  $("btnRefreshPlugins").addEventListener("click", () => refreshPluginCatalog().catch((e) => toast(e.message, true)));
  $("pluginModalClose").addEventListener("click", closePluginModal);
  $("pluginModalBackdrop").addEventListener("click", closePluginModal);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("pluginModal").hidden) closePluginModal();
  });
}

async function boot() {
  wire();
  await loadMeta();
  try {
    await loadConfigForm();
  } catch {
    toast("无法读取配置", true);
  }
  await refreshStatus();
  setInterval(refreshStatus, 4000);
}

boot();
