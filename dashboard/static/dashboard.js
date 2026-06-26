/* ═══════════════════════════════════════════════════════════════════
   HAR Dashboard — Frontend Logic
   WebSocket + Chart.js + UI Updates
   ═══════════════════════════════════════════════════════════════════ */

// ── Activity definitions (7 classes) ────────────────────────────
const ACTIVITIES = [
  { id: 0, en: "sit", zh: "静坐", icon: "chair", color: "#3b82f6" },
  { id: 1, en: "stand", zh: "站立", icon: "person", color: "#06b6d4" },
  { id: 2, en: "walk", zh: "步行", icon: "walk", color: "#22c55e" },
  { id: 3, en: "run", zh: "跑步", icon: "run", color: "#eab308" },
  { id: 4, en: "upstairs", zh: "上楼", icon: "up", color: "#f97316" },
  { id: 5, en: "downstairs", zh: "下楼", icon: "down", color: "#8b5cf6" },
  { id: 6, en: "fall", zh: "跌倒", icon: "alert", color: "#ef4444" },
];

// ── SVG icons for activity cards ─────────────────────────────────
function activityIcon(act) {
  const icons = {
    chair: '<circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 20h16M8 14h16" stroke="currentColor" stroke-width="2"/>',
    person: '<circle cx="16" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2"/><line x1="16" y1="13" x2="16" y2="28" stroke="currentColor" stroke-width="2"/>',
    walk: '<circle cx="16" cy="7" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 11l-3 8 5 3 3 8M12 18l4-2" fill="none" stroke="currentColor" stroke-width="2"/>',
    run: '<circle cx="16" cy="7" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 11l2 6 6-2 2 8M16 16l4 3M18 12l3-3" fill="none" stroke="currentColor" stroke-width="2"/>',
    up: '<path d="M16 4l-8 10h6v8h4v-8h6z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
    down: '<path d="M16 28l-8-10h6V8h4v10h6z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
    alert: '<path d="M16 4L2 28h28z" fill="none" stroke="currentColor" stroke-width="2"/><line x1="16" y1="14" x2="16" y2="20" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="24" r="1" fill="currentColor"/>',
  };
  return icons[act.icon] || icons.person;
}

// ── Generate activity cards ──────────────────────────────────────
function buildActivityCards() {
  const container = document.getElementById("activityCards");
  ACTIVITIES.forEach((act, i) => {
    const card = document.createElement("div");
    card.className = "activity-card";
    card.id = `actCard${act.id}`;
    card.style.color = act.color;
    card.innerHTML = `
      <svg width="32" height="32" viewBox="0 0 32 32">${activityIcon(act)}</svg>
      <span class="act-label">${act.zh}</span>
    `;
    container.appendChild(card);
  });
}

// ── Chart.js initialization ──────────────────────────────────────
const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 200 },
  scales: {
    x: { display: false },
    y: { min: -200, max: 200, ticks: { font: { size: 10 }, stepSize: 100 } },
  },
  elements: { point: { radius: 0 } },
  plugins: { legend: { display: false } },
  interaction: { intersect: false, mode: 'index' },
};

function makeChart(canvasId) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  const labels = Array.from({ length: 50 }, (_, i) => i);
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "X", data: Array(50).fill(0), borderColor: "#f44336", borderWidth: 1.5, tension: 0.3 },
        { label: "Y", data: Array(50).fill(0), borderColor: "#22c55e", borderWidth: 1.5, tension: 0.3 },
        { label: "Z", data: Array(50).fill(0), borderColor: "#3b82f6", borderWidth: 1.5, tension: 0.3 },
      ],
    },
    options: chartOptions,
  });
}

const accChart = makeChart("accChart");
const gyroChart = makeChart("gyroChart");

// ── Update charts ─────────────────────────────────────────────────
function updateChart(chart, data) {
  if (!data) return;
  chart.data.datasets[0].data = data.x || [];
  chart.data.datasets[1].data = data.y || [];
  chart.data.datasets[2].data = data.z || [];
  chart.update("none");
}

// ── Update activity display ──────────────────────────────────────
function updateActivity(data) {
  if (data.activity_id === null || data.activity_id === undefined) return;

  // Update cards
  document.querySelectorAll(".activity-card").forEach(c => c.classList.remove("active"));
  const activeCard = document.getElementById(`actCard${data.activity_id}`);
  if (activeCard) activeCard.classList.add("active");

  // Update current activity text
  const act = ACTIVITIES[data.activity_id];
  const nameEl = document.querySelector(".activity-name");
  const confEl = document.querySelector(".confidence");

  if (act) {
    nameEl.textContent = data.activity_zh || act.zh;
    nameEl.style.color = act.color;
    confEl.textContent = `置信度: ${Math.round((data.confidence || 0) * 100)}%`;
  }
}

// ── Log console ──────────────────────────────────────────────────
function addLog(msg) {
  const consoleEl = document.getElementById("logConsole");
  if (!consoleEl) return;
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = msg;
  consoleEl.appendChild(line);
  // Keep only last 100 lines
  while (consoleEl.children.length > 100) {
    consoleEl.removeChild(consoleEl.firstChild);
  }
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// ── Sensor body SVG update ───────────────────────────────────────
function updateSensors(sensors) {
  const chest = document.getElementById("sensorChest");
  const thigh = document.getElementById("sensorThigh");
  if (!chest || !thigh) return;

  const chestOk = sensors && sensors.chest;
  const thighOk = sensors && sensors.thigh;

  // Update chest sensor color
  const chestRect = chest.querySelector("rect");
  chestRect.setAttribute("fill", chestOk ? "#00c853" : "#ef4444");
  chestRect.setAttribute("stroke", chestOk ? "#00a844" : "#c62828");

  // Update thigh sensor color
  const thighRect = thigh.querySelector("rect");
  thighRect.setAttribute("fill", thighOk ? "#00c853" : "#ef4444");
  thighRect.setAttribute("stroke", thighOk ? "#00a844" : "#c62828");

  // Show/hide radio waves
  chest.querySelectorAll("path").forEach(p => p.style.display = chestOk ? "" : "none");
  thigh.querySelectorAll("path").forEach(p => p.style.display = thighOk ? "" : "none");
}

// ── Status bar ───────────────────────────────────────────────────
function updateStatus(mode) {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  dot.className = "status-dot";
  if (mode === "live") {
    dot.classList.add("live");
    text.textContent = "实时模式";
  } else {
    dot.classList.add("demo");
    text.textContent = "演示模式";
  }
}

// ── Model info ───────────────────────────────────────────────────
function updateModelInfo(model) {
  if (!model) return;
  document.getElementById("modelName").textContent = model.name || "逻辑回归 (LR)";
  document.getElementById("modelFeats").textContent = (model.features || 184) + " 维";
}

// ── Clock ────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    now.toLocaleTimeString("zh-CN", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── Button handlers ──────────────────────────────────────────────
let hardwareConnected = false;
let sessionActive = true;

function toggleHardware() {
  const btn = document.getElementById("btnConnect");
  if (!hardwareConnected) {
    const ipInput = document.getElementById("esp32IP");
    const customIP = ipInput ? ipInput.value.trim() : "";
    socket.emit("connect_hardware", { ip: customIP || null });
  } else {
    socket.emit("disconnect_hardware");
    hardwareConnected = false;
    btn.classList.remove("active");
  }
}

function toggleSession() {
  const btn = document.getElementById("btnSession");
  sessionActive = !sessionActive;
  if (sessionActive) {
    btn.classList.add("active");
    socket.emit("start_session");
  } else {
    btn.classList.remove("active");
    addLog("> 会话已暂停");
  }
}

function generateReport() {
  const btn = document.getElementById("btnReport");
  btn.classList.add("active");
  socket.emit("generate_report");
  setTimeout(() => btn.classList.remove("active"), 2000);
}

function toggleLog() {
  const checked = document.getElementById("logToggle").checked;
  const consoleEl = document.getElementById("logConsole");
  consoleEl.classList.toggle("hidden", !checked);
}

// ── SocketIO ─────────────────────────────────────────────────────
const socket = io();

socket.on("connect", () => {
  addLog("> 已连接到 HAR Dashboard 服务器");
});

socket.on("disconnect", () => {
  addLog("> 与服务器的连接已断开");
});

socket.on("sensor_update", (data) => {
  // Update charts
  if (data.acc) updateChart(accChart, data.acc);
  if (data.gyro) updateChart(gyroChart, data.gyro);

  // Update activity
  updateActivity(data);

  // Update sensors
  if (data.sensors) updateSensors(data.sensors);

  // Update model info
  if (data.model) updateModelInfo(data.model);

  // Update status
  if (data.mode) updateStatus(data.mode);

  // Add log
  if (data.log) addLog(data.log);
});

socket.on("log", (data) => {
  addLog(data.msg || data);
});

socket.on("hardware_status", (data) => {
  const btn = document.getElementById("btnConnect");
  if (data.connected) {
    hardwareConnected = true;
    btn.classList.add("active");
    addLog(`✅ 硬件已连接 — ${data.port}`);
  } else {
    hardwareConnected = false;
    btn.classList.remove("active");
  }
});

socket.on("session_status", (data) => {
  if (data.active) {
    addLog("📊 会话进行中 — 正在记录数据...");
  }
});

// ── Init ─────────────────────────────────────────────────────────
buildActivityCards();
addLog("> Dashboard 初始化完成");
addLog("> 等待传感器数据...");
