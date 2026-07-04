import { app } from "../../scripts/app.js";
import { t } from "./i18n.js";

// Prompt Composer 配置面板。
//
// 节点只保留 seed 和一个隐藏的 config（STRING，存 JSON）。本脚本给节点加一个
// "打开配置面板"按钮，点开一个浮层，把全部生成参数集中在面板里编辑，确定后
// 序列化成 JSON 写回 config widget。角色检索作为一个子面板，复用一份内存索引。

const NODE_NAME = "PromptComposerGenerate";
const IDENTITY_SEP = " ｜ ";
const MAX_RESULTS = 50;

// 与后端 _DEFAULT_CONFIG 保持一致的默认配置。
const DEFAULT_CONFIG = {
  sampler: "weighted",
  rating: "general",
  identity: "",
  fixed_tags: ["1girl"],
  disabled_tags: [],
  random_categories: [
    "hair",
    "eyes",
    "clothing",
    "expression",
    "pose",
    "hand",
    "leg",
    "camera",
    "composition",
    "background",
    "lighting",
  ],
  lock_categories: [],
  return_debug: true,
  resolution_mode: "auto",
  manual_width: 896,
  manual_height: 1152,
  weights: {},
  use_builtin_negative: true,
  user_negative: [],
  recycle_conflict_negative: false,
  // 关联加成与自动追加，默认全部关闭，与后端 _DEFAULT_CONFIG 一致。
  association_boost: false,
  association_strength: 0.5,
  auto_add_requires: false,
  auto_add_related: false,
};

// 分类勾选框的可选项。常见分类加上 nsfw 分类。
const ALL_CATEGORIES= [
  "hair",
  "eyes",
  "clothing",
  "expression",
  "pose",
  "hand",
  "leg",
  "camera",
  "composition",
  "background",
  "lighting",
  "nsfw_act",
  "nsfw_body",
  "nsfw_gear",
];

// ------------------------- 角色索引加载与检索 -------------------------

let identityIndexCache = null;
let identityIndexLoading = null;

async function loadIdentityIndex() {
  if (identityIndexCache) {
    return identityIndexCache;
  }
  if (identityIndexLoading) {
    return identityIndexLoading;
  }
  identityIndexLoading = fetch("/prompt_composer/identities")
    .then((response)=> {
      if (!response.ok) {
        throw new Error(t("search_load_failed") + ": " + response.status);
      }
      return response.json();
    })
    .then((data) => {
      identityIndexCache = Array.isArray(data) ? data : [];
      return identityIndexCache;
    })
    .finally(() => {
      identityIndexLoading = null;
    });
  return identityIndexLoading;
}

function filterIdentities(index, keyword) {
  const kw = (keyword || "").trim().toLowerCase();
  if (!kw) {
    return{ items: index.slice(0, MAX_RESULTS), truncated: index.length > MAX_RESULTS };
  }
  const matched = [];
  for (const entry of index) {
    const id = (entry.id || "").toLowerCase();
    const name = (entry.name || "").toLowerCase();
    const tag = (entry.display_tag || "").toLowerCase();
    if (id.includes(kw) || name.includes(kw) || tag.includes(kw)) {
      matched.push(entry);
      if (matched.length > MAX_RESULTS) {
        break;
      }
    }
  }
  const truncated = matched.length > MAX_RESULTS;
  return { items: matched.slice(0, MAX_RESULTS), truncated };
}

// ------------------------- config 读写 -------------------------

function findConfigWidget(node) {
  if (!node.widgets) {
    return null;
  }
  return node.widgets.find((w) => w.name === "config") || null;
}

// 从 config widget 读取并规整为完整配置对象，解析失败用默认。
function readConfig(node) {
  const widget = findConfigWidget(node);
  const cfg = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
  if (!widget || !widget.value) {
    return cfg;
  }
  let data = null;
  try {
    data = JSON.parse(widget.value);
  } catch (e) {
    return cfg;
  }
  if (!data || typeof data !== "object") {
    return cfg;
  }
  if (typeof data.sampler === "string") cfg.sampler = data.sampler;
  if (typeof data.rating === "string") cfg.rating = data.rating;
  if (typeof data.identity === "string") cfg.identity = data.identity;
  if (Array.isArray(data.fixed_tags)) cfg.fixed_tags = data.fixed_tags.slice();
  if (Array.isArray(data.disabled_tags)) cfg.disabled_tags = data.disabled_tags.slice();
  if (Array.isArray(data.random_categories)) {
    cfg.random_categories = data.random_categories.slice();
  }
  if (Array.isArray(data.lock_categories)) cfg.lock_categories = data.lock_categories.slice();
  if (typeof data.return_debug === "boolean") cfg.return_debug = data.return_debug;
  if (data.resolution_mode === "auto" || data.resolution_mode === "manual") {
    cfg.resolution_mode = data.resolution_mode;
  }
  if (typeof data.manual_width === "number") cfg.manual_width = data.manual_width;
  if (typeof data.manual_height === "number") cfg.manual_height = data.manual_height;
  if (data.weights && typeof data.weights === "object" && !Array.isArray(data.weights)) {
    const w = {};
    for (const key of Object.keys(data.weights)) {
      const num = Number(data.weights[key]);
      if (!Number.isNaN(num)) {
        w[key] = num;
      }
    }
    cfg.weights = w;
  }
  if (typeof data.use_builtin_negative === "boolean") {
    cfg.use_builtin_negative = data.use_builtin_negative;
  }
  if (Array.isArray(data.user_negative)) cfg.user_negative = data.user_negative.slice();
  if (typeof data.recycle_conflict_negative === "boolean") {
    cfg.recycle_conflict_negative = data.recycle_conflict_negative;
  }
  // 关联加成与自动追加字段，开关取布尔，强度取数值并限定范围。
  if (typeof data.association_boost === "boolean") {
    cfg.association_boost = data.association_boost;
  }
  if (typeof data.association_strength === "number" && !Number.isNaN(data.association_strength)) {
    let s = data.association_strength;
    if (s < 0) s = 0;
    if (s > 5) s = 5;
    cfg.association_strength = s;
  }
  if (typeof data.auto_add_requires === "boolean") {
    cfg.auto_add_requires = data.auto_add_requires;
  }
  if (typeof data.auto_add_related === "boolean") {
    cfg.auto_add_related = data.auto_add_related;
  }
  return cfg;
}

function writeConfig(node, cfg) {
  const widget = findConfigWidget(node);
  if (!widget) {
    return;
  }
  widget.value = JSON.stringify(cfg, null, 2);
  if (widget.callback) {
    widget.callback(widget.value);
  }
  node.setDirtyCanvas(true, true);
}

// 把多行或逗号分隔的文本转成字符串数组。
function textToList(text) {
  return (text || "")
    .split(/[\n,]/)
    .map((s)=> s.trim())
    .filter((s) => s.length > 0);
}

function listToText(list) {
  return (list || []).join("\n");
}

// 把关联加成强度规整成 [0, 5] 内的浮点，非法回退 0.5。
function clampStrength(value) {
  let s = Number(value);
  if (Number.isNaN(s)) {
    return 0.5;
  }
  if (s < 0) s = 0;
  if (s > 5) s = 5;
  return s;
}

// 把权重对象转成每行 标签:权重 的文本。
function weightsToText(weights) {
  if (!weights || typeof weights !== "object") {
    return "";
  }
  const lines = [];
  for (const key of Object.keys(weights)) {
    lines.push(key + ":" + weights[key]);
  }
  return lines.join("\n");
}

// 把每行 标签:权重 的文本解析成权重对象，非法行跳过。
function textToWeights(text) {
  const result = {};
  const lines = (text|| "").split(/\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    const idx = trimmed.lastIndexOf(":");
    if (idx <= 0) {
      continue;
    }
    const tag = trimmed.slice(0, idx).trim();
    const num =Number(trimmed.slice(idx + 1).trim());
    if (!tag || Number.isNaN(num)) {
      continue;
    }
    result[tag] = num;
  }
  return result;
}

// ------------------------- 预设与历史：本地存储 -------------------------

const PRESET_KEY = "prompt_composer.presets";
const HISTORY_KEY = "prompt_composer.history";
const HISTORY_LIMIT = 50;

function loadPresets() {
  try {
    const raw = localStorage.getItem(PRESET_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch (e) {
    return [];
  }
}

function savePresets(list) {
  try {
    localStorage.setItem(PRESET_KEY, JSON.stringify(list));
  } catch (e) {
    // 存储失败时静默，不阻断主流程。
  }
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch (e) {
    return [];
  }
}

function saveHistory(list) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
  } catch (e) {
    // 忽略。
  }
}

// 追加一条历史，超出上限时丢弃最旧的非收藏项。
function appendHistory(entry) {
  const list = loadHistory();
  list.unshift(entry);
  // 先统计非收藏项，从尾部开始丢弃多余的非收藏项。
  const nonFav = list.filter((it) => !it.favorite);
  if (nonFav.length > HISTORY_LIMIT) {
    let toDrop = nonFav.length - HISTORY_LIMIT;
    for (let i = list.length - 1; i >= 0 && toDrop > 0; i--) {
      if (!list[i].favorite) {
        list.splice(i, 1);
        toDrop--;
      }
    }
  }
  saveHistory(list);
}

// ------------------------- 通用 DOM 辅助 -------------------------

function el(tag, style, text) {
  const node = document.createElement(tag);
  if (style) {
    node.style.cssText = style;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function makeOverlay() {
  return el(
    "div",
    "position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10000;" +
      "display:flex;align-items:center;justify-content:center;"
  );
}

// ------------------------- 角色检索子面板 -------------------------

function openCharacterSearch(onPick) {
  const overlay = makeOverlay();
  const panel = el(
    "div",
    "width:420px;max-height:70vh;background:#2b2b2b;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:8px;display:flex;flex-direction:column;" +
      "box-shadow:0 4px 20px rgba(0,0,0,0.6);font-size:13px;overflow:hidden;z-index:10001;"
  );
  overlay.appendChild(panel);

  const header = el(
    "div",
    "padding:10px 12px;font-weight:bold;border-bottom:1px solid#444;" +
      "display:flex;justify-content:space-between;align-items:center;",
    t("search_title")
  );
  const closeBtn = el("span", "cursor:pointer;font-size:18px;line-height:1;padding:0 4px;", "×");
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const searchInput = el(
 "input",
    "margin:10px 12px;padding:6px 8px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid#555;border-radius:4px;outline:none;"
  );
  searchInput.type = "text";
  searchInput.placeholder =t("search_placeholder");
  panel.appendChild(searchInput);

  const hint = el("div", "padding:0 12px 6px;color:#999;font-size:12px;");
  panel.appendChild(hint);

  const list = el("div", "overflow-y:auto;flex:1;padding:0 6px 8px;");
  panel.appendChild(list);

  document.body.appendChild(overlay);

  function close() {
    if (overlay.parentNode) {
   overlay.parentNode.removeChild(overlay);
    }
  }

  closeBtn.addEventListener("click", close);
overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) {
      close();
    }
  });

  function render(index) {
    const { items, truncated } = filterIdentities(index, searchInput.value);
    list.innerHTML = "";
    if (items.length === 0) {
    hint.textContent = t("search_no_match");
      return;
    }
    hint.textContent = truncated
      ? t("search_result_truncated", { n: MAX_RESULTS })
      : t("search_result_count", { n: items.length });
    for (const entry of items) {
      const row = el(
        "div",
        "padding:6px 8px;border-radius:4px;cursor:pointer;display:flex;" +
          "justify-content:space-between;gap:8px;"
      );
      row.addEventListener("mouseenter", () => (row.style.background = "#3a3a3a"));
      row.addEventListener("mouseleave", () => (row.style.background = "transparent"));
      row.addEventListener("click", () => {
        onPick(entry);
        close();
      });
      const nameSpan = el("span", "color:#e0e0e0;", entry.name || t("search_no_zh_name"));
      const idSpan = el("span", "color:#888;font-size:12px;text-align:right;", entry.id);
      row.appendChild(nameSpan);
      row.appendChild(idSpan);
      list.appendChild(row);
    }
  }

  hint.textContent = t("search_loading");
  loadIdentityIndex()
    .then((index) => {
      render(index);
      searchInput.addEventListener("input", () => render(index));
      searchInput.focus();
    })
    .catch((err) => {
      hint.textContent = String(err && err.message ? err.message : err);
    });
}
// ------------------------- 标签检索：加载与过滤 -------------------------

let tagIndexCache = null;
let tagIndexLoading = null;

async function loadTagIndex() {
  if (tagIndexCache) {
  return tagIndexCache;
  }
  if (tagIndexLoading) {
    return tagIndexLoading;
  }
  tagIndexLoading = fetch("/prompt_composer/tags")
    .then((response) => {
      if (!response.ok) {
        throw new Error(t("tag_search_load_failed") + ": " + response.status);
      }
      return response.json();
    })
    .then((data) => {
      tagIndexCache = Array.isArray(data) ? data : [];
      return tagIndexCache;
    })
    .finally(() => {
  tagIndexLoading = null;
    });
  return tagIndexLoading;
}

function filterTags(index, keyword) {
  const kw = (keyword || "").trim().toLowerCase();
  if (!kw) {
    return { items: index.slice(0, MAX_RESULTS), truncated: index.length > MAX_RESULTS };
  }
  const matched = [];
  for (const entry of index) {
    const tag = (entry.tag || "").toLowerCase();
    const category = (entry.category || "").toLowerCase();
    const zh = (entry.label_zh || "").toLowerCase();
    if (tag.includes(kw) || category.includes(kw) || zh.includes(kw)) {
      matched.push(entry);
      if (matched.length > MAX_RESULTS) {
        break;
      }
    }
  }
  const truncated = matched.length > MAX_RESULTS;
 return { items: matched.slice(0, MAX_RESULTS), truncated };
}

// ------------------------- 标签关联：按标签查询 -------------------------

// 按标签缓存关联结果，避免重复请求同一标签。
const associationCache = {};

// 拉取某标签的关联词列表。失败或无数据时返回空数组，不报错。
async function loadAssociations(tag, limit) {
  const key = (tag || "").trim().toLowerCase();
  if (!key) {
    return [];
  }
  if (associationCache[key]) {
    return associationCache[key];
  }
  const url =
    "/prompt_composer/associations?tag=" +
    encodeURIComponent(key) +
    (limit ? "&limit=" +encodeURIComponent(limit) : "");
  try {
    const response = await fetch(url);
    if (!response.ok) {
    throw new Error(t("assoc_load_failed") + ": " + response.status);
    }
    const data = await response.json();
    const items = Array.isArray(data) ? data : [];
    associationCache[key] =items;
    return items;
  } catch (e) {
    return [];
  }
}

// ------------------------- 标签检索子面板 -------------------------

function openTagSearch(onPick, getExisting) {
  // getExisting 可选，返回当前已选标签数组，用于推荐区的去重与冲突过滤。
  const overlay =makeOverlay();
  const panel = el(
    "div",
    "width:460px;max-height:70vh;background:#2b2b2b;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:8px;display:flex;flex-direction:column;" +
      "box-shadow:0 4px 20px rgba(0,0,0,0.6);font-size:13px;overflow:hidden;z-index:10001;"
  );
  overlay.appendChild(panel);

  const header = el(
    "div",
    "padding:10px 12px;font-weight:bold;border-bottom:1px solid #444;" +
      "display:flex;justify-content:space-between;align-items:center;",
    t("tag_search_title")
  );
  const closeBtn = el("span", "cursor:pointer;font-size:18px;line-height:1;padding:0 4px;", "×");
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const searchInput = el(
    "input",
    "margin:10px 12px;padding:6px 8px;background:#1e1e1e;color:#e0e0e0;" +
"border:1px solid #555;border-radius:4px;outline:none;"
  );
  searchInput.type = "text";
  searchInput.placeholder = t("tag_search_placeholder");
  panel.appendChild(searchInput);

  const hint = el("div", "padding:0 12px 6px;color:#999;font-size:12px;");
  panel.appendChild(hint);

  const list = el("div", "overflow-y:auto;flex:1;padding:0 6px 8px;");
  panel.appendChild(list);

  // 关联推荐区：选中或查看一个标签时，展示其关联词，用户点选才加入。
  const recWrap = el(
    "div",
    "border-top:1px solid #444;padding:6px 12px 10px;max-height:38%;" +
      "overflow-y:auto;display:none;"
  );
  const recTitle = el(
    "div",
    "color:#9cf;font-size:12px;margin-bottom:4px;",
    t("assoc_rec_title")
  );
  const recHint = el("div", "color:#999;font-size:12px;");
  const recList = el("div", "display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;");
  recWrap.appendChild(recTitle);
  recWrap.appendChild(recHint);
  recWrap.appendChild(recList);
  panel.appendChild(recWrap);

  document.body.appendChild(overlay);

  function close() {
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }

  closeBtn.addEventListener("click", close);
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) {
      close();
    }
  });

 // 展示某标签的关联推荐。对已选标签做去重过滤，已在面板里的不重复列出。
  function showRecommendations(tag) {
    recWrap.style.display = "block";
    recTitle.textContent = t("assoc_rec_title") + "：" + tag;
    recHint.textContent = t("assoc_rec_loading");
    recList.innerHTML = "";
    const existing = typeof getExisting === "function" ? getExisting() : [];
    const existingSet = {};
    for (const name of existing) {
      existingSet[String(name).trim().toLowerCase()] = true;
    }
    loadAssociations(tag, 12).then((items) => {
      recList.innerHTML = "";
      const filtered = items.filter(
        (it) => !existingSet[String(it.tag).trim().toLowerCase()]
      );
      if (filtered.length === 0) {
        recHint.textContent = t("assoc_rec_empty");
        return;
      }
      recHint.textContent = "";
      for (const it of filtered) {
        const chip = el(
          "span",
          "padding:3px 8px;background:#33405a;color:#cde;border-radius:10px;" +
            "cursor:pointer;font-size:12px;",
          it.tag + "  " + Number(it.weight).toFixed(2)
        );
        chip.addEventListener("mouseenter", () => (chip.style.background = "#3f5378"));
        chip.addEventListener("mouseleave", () => (chip.style.background = "#33405a"));
        chip.addEventListener("click", () => {
          onPick({ tag: it.tag, category: "", label_zh: "" });
          existingSet[String(it.tag).trim().toLowerCase()] = true;
          chip.style.opacity = "0.4";
          chip.style.pointerEvents = "none";
        });
        recList.appendChild(chip);
      }
    });
  }

  function render(index) {
    const { items, truncated } = filterTags(index, searchInput.value);
    list.innerHTML = "";
    if (items.length === 0) {
      hint.textContent = t("search_no_match");
      return;
    }
    hint.textContent = truncated
      ? t("search_result_truncated", {n: MAX_RESULTS })
      : t("search_result_count", { n: items.length });
    for (const entry of items) {
      const row = el(
  "div",
        "padding:6px 8px;border-radius:4px;cursor:pointer;display:flex;" +
     "justify-content:space-between;gap:8px;align-items:center;"
      );
      row.addEventListener("mouseenter", () => (row.style.background = "#3a3a3a"));
      row.addEventListener("mouseleave", () => (row.style.background = "transparent"));
      const zhSpan = el("span", "color:#e0e0e0;flex:1;", entry.label_zh || entry.tag);
      zhSpan.addEventListener("click", () => {
        onPick(entry);
        close();
      });
      const tagSpan = el(
    "span",
   "color:#888;font-size:12px;text-align:right;",
   entry.tag + "  [" + entry.category + "]"
      );
      tagSpan.addEventListener("click", () => {
        onPick(entry);
        close();
      });
      // 单独的关联按钮：点它只展示关联推荐，不关闭面板。
      const recBtn = el(
        "span",
        "color:#9cf;font-size:12px;cursor:pointer;padding:0 4px;",
        t("assoc_rec_btn")
      );
      recBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        showRecommendations(entry.tag);
      });
      row.appendChild(zhSpan);
      row.appendChild(tagSpan);
    row.appendChild(recBtn);
      list.appendChild(row);
    }
  }


  hint.textContent = t("search_loading");
  loadTagIndex()
    .then((index) => {
      render(index);
      searchInput.addEventListener("input",() => render(index));
      searchInput.focus();
    })
    .catch((err) => {
      hint.textContent = String(err && err.message ? err.message : err);
    });
}


// 创建一个检索标签按钮，选中后把标签追加到目标文本区（去重）。
function makeTagSearchButton(area) {
  const btn = el(
    "button",
    "margin:2px 12px 0;padding:3px 10px;background:#4a6;color:#fff;" +
      "border:none;border-radius:4px;cursor:pointer;display:block;",
    t("btn_search_tag")
  );
  btn.addEventListener("click", () => {
    openTagSearch(
      (entry) => {
        const list = textToList(area.value);
        if (!list.includes(entry.tag)) {
          list.push(entry.tag);
        }
        area.value = listToText(list);
      },
      // 推荐区用当前文本区已有标签做去重与过滤。
      () => textToList(area.value)
    );
  });
  return btn;
}

// ------------------------- 主配置面板 -------------------------

function sectionTitle(text) {
  return el(
    "div",
    "margin:12px 12px 4px;font-weight:bold;color:#cfcfcf;" +
  "border-bottom:1px solid #444;padding-bottom:2px;",
    text
  );
}

function makeSelect(options, value) {
  const sel = el(
    "select",
    "margin:4px 12px;padding:4px 6px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;"
  );
  for (const opt of options) {
    const o = el("option", "", opt.label);
    o.value = opt.value;
    if (opt.value === value) {
      o.selected = true;
    }
    sel.appendChild(o);
  }
  return sel;
}

function makeCategoryChecklist(selected) {
  const wrap = el(
    "div",
    "margin:4px 12px;display:flex;flex-wrap:wrap;gap:6px 12px;"
  );
  const set = new Set(selected || []);
  const boxes = [];
  for (const cat of ALL_CATEGORIES) {
    const label = el("label", "display:flex;align-items:center;gap:4px;cursor:pointer;");
    const box = el("input", "");
    box.type = "checkbox";
    box.value = cat;
    box.checked = set.has(cat);
    label.appendChild(box);
    // 优先显示本地化分类名，未配置时回退到原始分类名。
    const catKey = "cat_" + cat;
    const catText =t(catKey) === catKey ? cat : t(catKey);
   label.appendChild(el("span", "", catText));
    wrap.appendChild(label);
    boxes.push(box);
  }
  return { wrap, boxes };
}

function checklistValues(boxes) {
  return boxes.filter((b) => b.checked).map((b) => b.value);
}

function openConfigPanel(node) {
  const cfg = readConfig(node);

  const overlay = makeOverlay();
  const panel =el(
    "div",
    "width:480px;max-height:82vh;background:#2b2b2b;color:#e0e0e0;" +
      "border:1px solid#555;border-radius:8px;display:flex;flex-direction:column;" +
      "box-shadow:0 4px 20px rgba(0,0,0,0.6);font-size:13px;overflow:hidden;"
  );
  overlay.appendChild(panel);

  const header = el(
    "div",
    "padding:10px 12px;font-weight:bold;border-bottom:1px solid #444;"+
      "display:flex;justify-content:space-between;align-items:center;",
    t("panel_title")
  );
  const closeBtn = el("span", "cursor:pointer;font-size:18px;line-height:1;padding:0 4px;", "×");
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const body = el("div", "overflow-y:auto;flex:1;padding-bottom:8px;");
  panel.appendChild(body);

  // 预设与历史入口
  body.appendChild(sectionTitle(t("section_preset_history")));
  const phRow = el("div", "margin:4px 12px;display:flex;gap:8px;");
  const presetBtn = el(
    "button",
    "padding:4px 12px;background:#557;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_open_preset")
  );
  const historyBtn = el(
    "button",
    "padding:4px 12px;background:#557;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_open_history")
  );
  presetBtn.addEventListener("click", () => openPresetPanel(node));
  historyBtn.addEventListener("click", () => openHistoryPanel(node));
  phRow.appendChild(presetBtn);
  phRow.appendChild(historyBtn);
  body.appendChild(phRow);

  //基础设置
  body.appendChild(sectionTitle(t("section_basic")));

  // 采样方式标题行：标签 + 帮助按钮。
  const samplerHead = el(
    "div",
"margin:4px 12px 0;color:#aaa;display:flex;align-items:center;gap:6px;"
  );
  samplerHead.appendChild(el("span", "", t("label_sampler")));
  const samplerHelpBtn = el(
    "span",
    "display:inline-flex;align-items:center;justify-content:center;" +
      "width:16px;height:16px;border-radius:50%;background:#555;color:#fff;" +
      "font-size:11px;cursor:pointer;user-select:none;",
    t("btn_help")
  );
  samplerHead.appendChild(samplerHelpBtn);
  body.appendChild(samplerHead);

  const samplerSel = makeSelect(
    [
      { value: "weighted", label: t("sampler_weighted") },
      { value: "random", label: t("sampler_random") },
    ],
    cfg.sampler
  );
  body.appendChild(samplerSel);

  // 采样方式说明区，默认隐藏，点帮助按钮切换显示。
  const samplerHelp = el(
    "div",
    "display:none;margin:4px 12px;padding:6px 8px;background:#1e1e1e;" +
      "border:1px solid#444;border-radius:4px;color:#bbb;font-size:12px;line-height:1.6;"
  );
  samplerHelp.appendChild(el("div", "", t("sampler_help_weighted")));
  samplerHelp.appendChild(el("div", "margin-top:4px;", t("sampler_help_random")));
  body.appendChild(samplerHelp);
  samplerHelpBtn.addEventListener("click", () => {
    samplerHelp.style.display = samplerHelp.style.display === "none" ? "block" : "none";
  });

  body.appendChild(el("div", "margin:4px 12px 0;color:#aaa;", t("label_rating")));
  const ratingSel = makeSelect(
    [
      { value: "general", label: t("rating_general") },
      { value: "explicit", label: t("rating_explicit") },
    ],
    cfg.rating
  );
  body.appendChild(ratingSel);

  const debugLabel = el(
    "label",
    "margin:8px 12px 0;display:flex;align-items:center;gap:6px;cursor:pointer;"
  );
  const debugBox = el("input", "");
  debugBox.type = "checkbox";
  debugBox.checked = !!cfg.return_debug;
  debugLabel.appendChild(debugBox);
  debugLabel.appendChild(el("span", "", t("label_return_debug")));
  body.appendChild(debugLabel);
  // 分辨率模式
  body.appendChild(el("div", "margin:8px 12px 0;color:#aaa;", t("label_resolution_mode")));
  const resModeSel = makeSelect(
    [
      { value: "auto", label: t("resolution_auto") },
      { value: "manual", label: t("resolution_manual") },
    ],
    cfg.resolution_mode
  );
  body.appendChild(resModeSel);

  // 手动宽高输入行，仅在 manual 模式显示。
  const manualRow = el(
    "div",
    "margin:4px 12px;display:flex;align-items:center;gap:8px;"
  );
  manualRow.appendChild(el("span", "color:#aaa;", t("label_width")));
  const manualWidthInput = el(
    "input",
    "width:80px;padding:4px 6px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;outline:none;"
  );
  manualWidthInput.type = "number";
  manualWidthInput.value = String(cfg.manual_width);
  manualRow.appendChild(manualWidthInput);
  manualRow.appendChild(el("span", "color:#aaa;", t("label_height")));
  const manualHeightInput = el(
    "input",
    "width:80px;padding:4px 6px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;outline:none;"
  );
  manualHeightInput.type = "number";
  manualHeightInput.value = String(cfg.manual_height);
  manualRow.appendChild(manualHeightInput);
  body.appendChild(manualRow);

  function refreshManualRow() {
    manualRow.style.display= resModeSel.value === "manual" ? "flex" : "none";
  }
  refreshManualRow();
  resModeSel.addEventListener("change", refreshManualRow);


  //角色
  body.appendChild(sectionTitle(t("section_character")));
  const charRow = el("div", "margin:4px 12px;display:flex;align-items:center;gap:8px;");
  const charLabel = el("span", "color:#aaa;", t("current_character") + ":");
  const charValue = el("span","color:#e0e0e0;flex:1;");
  const chooseBtn = el(
    "button",
    "padding:3px 10px;background:#3a5;color:#fff;border:none;border-radius:4px;cursor:pointer;",
    t("btn_choose_character")
  );
  const clearBtn = el(
    "button",
    "padding:3px 10px;background:#555;color:#fff;border:none;border-radius:4px;cursor:pointer;",
    t("btn_clear_character")
  );
  charRow.appendChild(charLabel);
  charRow.appendChild(charValue);
  charRow.appendChild(chooseBtn);
  charRow.appendChild(clearBtn);
  body.appendChild(charRow);

  let identityValue = cfg.identity || "";
  function refreshChar() {
    charValue.textContent = identityValue ? identityValue : t("character_none");
  }
  refreshChar();

  chooseBtn.addEventListener("click", () => {
    openCharacterSearch((entry) => {
      identityValue = entry.name ? entry.id + IDENTITY_SEP + entry.name : entry.id;
    refreshChar();
    });
  });
  clearBtn.addEventListener("click", () => {
    identityValue = "";
    refreshChar();
  });

  // 固定词
  body.appendChild(sectionTitle(t("section_fixed_tags")));
  const fixedArea = el(
    "textarea",
    "margin:4px 12px;height:56px;background:#1e1e1e;color:#e0e0e0;" +
   "border:1px solid #555;border-radius:4px;padding:6px 8px;resize:vertical;outline:none;display:block;width:calc(100% - 24px);box-sizing:border-box;"
  );
  fixedArea.placeholder = t("placeholder_fixed_tags");
  fixedArea.value = listToText(cfg.fixed_tags);
  body.appendChild(fixedArea);
  body.appendChild(makeTagSearchButton(fixedArea));

  // 禁用词
  body.appendChild(sectionTitle(t("section_disabled_tags")));
  const disabledArea = el(
    "textarea",
    "margin:4px 12px;height:56px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;padding:6px 8px;resize:vertical;outline:none;display:block;width:calc(100% - 24px);box-sizing:border-box;"
  );
    disabledArea.placeholder = t("placeholder_disabled_tags");
  disabledArea.value = listToText(cfg.disabled_tags);
 body.appendChild(disabledArea);
  body.appendChild(makeTagSearchButton(disabledArea));

  // 随机分类
  body.appendChild(sectionTitle(t("section_random_categories")));
  const randomList = makeCategoryChecklist(cfg.random_categories);
  body.appendChild(randomList.wrap);

  // 锁定分类
  body.appendChild(sectionTitle(t("section_lock_categories")));
  const lockList = makeCategoryChecklist(cfg.lock_categories);
  body.appendChild(lockList.wrap);

  // 标签权重
  body.appendChild(sectionTitle(t("section_weights")));
  body.appendChild(
    el("div", "margin:2px 12px;color:#999;font-size:12px;line-height:1.5;", t("weights_hint"))
  );
  const weightsArea = el(
    "textarea",
    "margin:4px 12px;height:56px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;padding:6px 8px;resize:vertical;outline:none;display:block;width:calc(100% - 24px);box-sizing:border-box;"
  );
  weightsArea.placeholder = t("placeholder_weights");
  weightsArea.value = weightsToText(cfg.weights);
  body.appendChild(weightsArea);

  // 负面提示词
  body.appendChild(sectionTitle(t("section_negative")));
  const builtinNegLabel = el(
    "label",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;:pointer;"
  );
  const builtinNegBox = el("input", "");
  builtinNegBox.type = "checkbox";
  builtinNegBox.checked = !!cfg.use_builtin_negative;
  builtinNegLabel.appendChild(builtinNegBox);
  builtinNegLabel.appendChild(el("span", "", t("label_use_builtin_negative")));
  body.appendChild(builtinNegLabel);

  const recycleLabel = el(
    "label",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;:pointer;"
  );
  const recycleBox = el("input", "");
  recycleBox.type = "checkbox";
  recycleBox.checked = !!cfg.recycle_conflict_negative;
  recycleLabel.appendChild(recycleBox);
  recycleLabel.appendChild(el("span", "", t("label_recycle_conflict")));
  body.appendChild(recycleLabel);

  body.appendChild(sectionTitle(t("section_user_negative")));
  const userNegArea = el(
    "textarea",
    "margin:4px 12px;height:56px;background:#1e1e1e;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:4px;padding:6px 8px;resize:vertical;outline:none;display:block;width:calc(100% - 24px);box-sizing:border-box;"
  );
  userNegArea.placeholder = t("placeholder_user_negative");
  userNegArea.value = listToText(cfg.user_negative);
  body.appendChild(userNegArea);
  body.appendChild(makeTagSearchButton(userNegArea));

  // 关联加成与自动追加区。默认全部关闭，开启后才影响生成。
  body.appendChild(sectionTitle(t("section_association")));

  const boostLabel = el(
    "label",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;cursor:pointer;"
  );
  const boostBox = el("input", "");
  boostBox.type = "checkbox";
  boostBox.checked = !!cfg.association_boost;
  boostLabel.appendChild(boostBox);
boostLabel.appendChild(el("span", "", t("label_association_boost")));
  body.appendChild(boostLabel);

  const strengthWrap = el(
    "div",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;"
  );
  strengthWrap.appendChild(el("span", "color:#cfcfcf;", t("label_association_strength")));
  const strengthInput = el(
    "input",
    "width:70px;background:#1e1e1e;color:#e0e0e0;border:1px solid #555;" +
      "border-radius:4px;padding:3px 6px;outline:none;"
  );
  strengthInput.type = "number";
  strengthInput.min = "0";
  strengthInput.max = "5";
  strengthInput.step = "0.1";
  strengthInput.value = String(cfg.association_strength);
  strengthWrap.appendChild(strengthInput);
  body.appendChild(strengthWrap);

  const autoReqLabel = el(
    "label",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;cursor:pointer;"
  );
  const autoReqBox = el("input", "");
  autoReqBox.type = "checkbox";
  autoReqBox.checked = !!cfg.auto_add_requires;
  autoReqLabel.appendChild(autoReqBox);
  autoReqLabel.appendChild(el("span", "", t("label_auto_add_requires")));
  body.appendChild(autoReqLabel);

  const autoRelLabel = el(
    "label",
    "margin:4px 12px 0;display:flex;align-items:center;gap:6px;cursor:pointer;"
  );
  const autoRelBox = el("input", "");
  autoRelBox.type = "checkbox";
  autoRelBox.checked = !!cfg.auto_add_related;
  autoRelLabel.appendChild(autoRelBox);
  autoRelLabel.appendChild(el("span", "", t("label_auto_add_related")));
  body.appendChild(autoRelLabel);


  // 底部按钮
  const footer = el(
    "div",
    "padding:10px 12px;border-top:1px solid #444;display:flex;justify-content:flex-end;gap:8px;"
  );
  const cancelBtn = el(
    "button",
    "padding:5px 16px;background:#555;color:#fff;border:none;border-radius:4px;cursor:pointer;",
    t("btn_cancel")
  );
const confirmBtn = el(
    "button",
    "padding:5px 16px;background:#3a5;color:#fff;border:none;border-radius:4px;cursor:pointer;",
    t("btn_confirm")
  );
footer.appendChild(cancelBtn);
  footer.appendChild(confirmBtn);
  panel.appendChild(footer);

  document.body.appendChild(overlay);

  function close() {
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }

  closeBtn.addEventListener("click", close);
  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("mousedown", (e) => {
    if (e.target ===overlay) {
      close();
    }
  });

  confirmBtn.addEventListener("click", () => {
    const newCfg = {
      sampler: samplerSel.value,
      rating: ratingSel.value,
      identity: identityValue,
      fixed_tags: textToList(fixedArea.value),
      disabled_tags:textToList(disabledArea.value),
      random_categories: checklistValues(randomList.boxes),
      lock_categories: checklistValues(lockList.boxes),
      return_debug: debugBox.checked,
      resolution_mode: resModeSel.value,
      manual_width: parseInt(manualWidthInput.value, 10) || 0,
      manual_height: parseInt(manualHeightInput.value, 10) || 0,
      weights: textToWeights(weightsArea.value),
      use_builtin_negative: builtinNegBox.checked,
      user_negative: textToList(userNegArea.value),
      recycle_conflict_negative: recycleBox.checked,
      association_boost: boostBox.checked,
      association_strength: clampStrength(strengthInput.value),
      auto_add_requires: autoReqBox.checked,
      auto_add_related: autoRelBox.checked,
    };
    writeConfig(node, newCfg);
    close();
  });
}

// ------------------------- 预设子面板 -------------------------

function openPresetPanel(node) {
   const overlay = makeOverlay();
  const panel = el(
    "div",
    "width:420px;max-height:70vh;background:#2b2b2b;color:#e0e0e0;" +
      "border:1px solid #555;border-radius:8px;display:flex;flex-direction:column;" +
      "box-shadow:0 4px 20px rgba(0,0,0,0.6);font-size:13px;overflow:hidden;z-index:10001;"
  );
  overlay.appendChild(panel);

  const header = el(
    "div",
    "padding:10px 12px;font-weight:bold;border-bottom:1px solid #444;" +
      "display:flex;justify-content:space-between;align-items:center;",
    t("preset_title")
  );
  const closeBtn = el("span", ":pointer;font-size:18px;line-height:1;padding:0 4px;", "×");
  header.appendChild(closeBtn);
  panel.appendChild(header);

 const toolbar = el("div", "padding:8px 12px;display:flex;gap:8px;flex-wrap:wrap;");
  const saveBtn = el(
    "button",
    "padding:4px 12px;background:#3a5;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_save_preset")
  );
  const exportBtn = el(
    "button",
    "padding:4px 12px;background:#557;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_export")
  );
  const importBtn = el(
    "button",
    "padding:4px 12px;background:#557;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_import")
  );
  toolbar.appendChild(saveBtn);
  toolbar.appendChild(exportBtn);
  toolbar.appendChild(importBtn);
  panel.appendChild(toolbar);

  const list = el("div", "overflow-y:auto;flex:1;padding:0 12px 8px;");
  panel.appendChild(list);

  document.body.appendChild(overlay);

  function close() {
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) {
      close();
    }
  });

  function render() {
 const presets = loadPresets();
    list.innerHTML = "";
    if (presets.length === 0) {
      list.appendChild(el("div", "color:#999;padding:8px 0;", t("preset_empty")));
      return;
    }
    presets.forEach((preset, index) => {
      const row = el(
        "div",
        "padding:6px 0;border-bottom:1px solid #3a3a3a;display:flex;" +
          "align-items:center;gap:8px;"
      );
      row.appendChild(el("span", "flex:1;color:#e0e0e0;", preset.name || ""));
      const loadBtn = el(
        "button",
        "padding:2px 10px;background:#3a5;color:#fff;border:none;border-radius:4px;:pointer;",
        t("btn_load")
      );
      const delBtn = el(
        "button",
        "padding:2px 10px;background:#844;color:#fff;border:none;border-radius:4px;:pointer;",
        t("btn_delete")
      );
      loadBtn.addEventListener("click", () => {
        if (preset.config) {
          writeConfig(node, preset.config);
        }
        close();
      });
      delBtn.addEventListener("click", () => {
        const next = loadPresets();
        next.splice(index, 1);
        savePresets(next);
        render();
      });
      row.appendChild(loadBtn);
      row.appendChild(delBtn);
      list.appendChild(row);
    });
  }

  saveBtn.addEventListener("click", () => {
    const name = window.prompt(t("preset_name_prompt"), "");
    if (!name) {
      return;
    }
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    const presets = loadPresets();
    const existingIndex = presets.findIndex((p) => p.name === trimmed);
    const cfg = readConfig(node);
    if (existingIndex >= 0) {
      if (!window.confirm(t("preset_overwrite_confirm"))) {
        return;
      }
      presets[existingIndex] = { name: trimmed, config: cfg };
    } else {
      presets.push({ name: trimmed, config: cfg });
    }
    savePresets(presets);
    render();
  });

  exportBtn.addEventListener("click", () => {
    const text = JSON.stringify(loadPresets(), null, 2);
    window.prompt(t("btn_export"), text);
  });

  importBtn.addEventListener("click", () => {
    const text = window.prompt(t("import_prompt"), "");
    if (!text) {
      return;
    }
    try {
      const data = JSON.parse(text);
      if (Array.isArray(data)) {
        savePresets(data);
        render();
      } else {
        window.alert(t("import_failed"));
      }
    } catch (e) {
      window.alert(t("import_failed"));
    }
  });

  render();
}

// ------------------------- 历史子面板 -------------------------

function openHistoryPanel(node) {
  const overlay = makeOverlay();
  const panel = el(
    "div",
    "width:520px;max-height:74vh;background:#2b2b2b;color:#e0e0e0;" +
     "border:1px solid #555;border-radius:8px;display:flex;flex-direction:column;" +
      "box-shadow:0 4px 20px rgba(0,0,0,0.6);font-size:13px;overflow:hidden;z-index:10001;"
  );
  overlay.appendChild(panel);

  const header = el(
    "div",
    "padding:10px 12px;font-weight:bold;border-bottom:1px solid #444;" +
      "display:flex;justify-content:space-between;align-items:center;",
    t("history_title")
  );
  const closeBtn = el("span", ":pointer;font-size:18px;line-height:1;padding:0 4px;", "×");
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const toolbar = el("div", "padding:8px 12px;display:flex;gap:8px;");
  const clearBtn = el(
    "button",
    "padding:4px 12px;background:#844;color:#fff;border:none;border-radius:4px;:pointer;",
    t("btn_clear_history")
  );
  toolbar.appendChild(clearBtn);
  panel.appendChild(toolbar);

  const list = el("div", "overflow-y:auto;flex:1;padding:0 12px 8px;");
  panel.appendChild(list);

  document.body.appendChild(overlay);

  function close() {
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) {
      close();
    }
  });

  function render() {
    const history = loadHistory();
 list.innerHTML = "";
    if (history.length === 0) {
      list.appendChild(el("div", "color:#999;padding:8px 0;", t("history_empty")));
      return;
    }
    history.forEach((entry, index) => {
      const row = el(
        "div",
        "padding:8px 0;border-bottom:1px solid #3a3a3a;"
      );
      const head = el(
        "div",
        "display:flex;align-items:center;gap:8px;margin-bottom:4px;"
      );
      const favMark = entry.favorite ? t("history_favorite_mark") + " " : "";
      head.appendChild(
        el(
          "span",
          "flex:1;color:#8bc34a;",
          favMark + t("history_resolution_label") + ": " + (entry.resolution || "")
        )
      );
      const reloadBtn = el(
        "button",
        "padding:2px 8px;background:#3a5;color:#fff;border:none;border-radius:4px;:pointer;",
        t("btn_reload_config")
      );
      const favBtn = el(
        "button",
        "padding:2px 8px;background:#557;color:#fff;border:none;border-radius:4px;:pointer;",
        entry.favorite ? t("btn_unfavorite") : t("btn_favorite")
      );
      const delBtn = el(
        "button",
        "padding:2px 8px;background:#844;color:#fff;border:none;border-radius:4px;:pointer;",
        t("btn_delete")
      );
      reloadBtn.addEventListener("click", () => {
if (entry.config) {
          writeConfig(node, entry.config);
        }
        close();
      });
      favBtn.addEventListener("click", () => {
        const next = loadHistory();
        if (next[index]) {
          next[index].favorite = !next[index].favorite;
          saveHistory(next);
         render();
        }
      });
      delBtn.addEventListener("click", () => {
        const next = loadHistory();
        next.splice(index, 1);
       saveHistory(next);
        render();
   });
      head.appendChild(reloadBtn);
      head.appendChild(favBtn);
      head.appendChild(delBtn);
      row.appendChild(head);

      const promptText = el(
        "div",
        "color:#d0d0d0;font-size:12px;line-height:1.5;word-break:break-all;",
        t("history_prompt_label") + ": " + (entry.prompt || "")
      );
      row.appendChild(promptText);
      if (entry.negative) {
        row.appendChild(
          el(
            "div",
            "color:#c98;font-size:12px;line-height:1.5;word-break:break-all;margin-top:2px;",
          t("history_negative_label") + ": " + entry.negative
     )
        );
      }
  list.appendChild(row);
    });
  }

  clearBtn.addEventListener("click", () => {
    // 清空时保留收藏项。
    const kept = loadHistory().filter((it) => it.favorite);
    saveHistory(kept);
    render();
  });

  render();
}

//------------------------- 提示词预览 -------------------------

// 在节点上创建一个只读预览区域，显示最新提示词与分辨率。
function attachPreview(node) {
  const wrap = el(
    "div",
    "background:#1e1e1e;border:1px solid #444;border-radius:4px;" +
      "padding:6px 8px;font-size:12px;color:#e0e0e0;box-sizing:border-box;width:100%;"
  );

  const titleRow = el(
    "div",
    "display:flex;justify-content:space-between;margin-bottom:4px;color:#aaa;"
  );
  const titleSpan = el("span", "font-weight:bold;", t("preview_title"));
 const resSpan = el("span","color:#8bc34a;", "");
  titleRow.appendChild(titleSpan);
  titleRow.appendChild(resSpan);
  wrap.appendChild(titleRow);

  const textArea = el(
    "textarea",
    "width:100%;height:80px;background:#141414;color:#d0d0d0;border:1px solid #333;" +
      "border-radius:4px;padding:4px 6px;resize:vertical;outline:none;box-sizing:border-box;"
  );
  textArea.readOnly = true;
  textArea.value = t("preview_empty");
  wrap.appendChild(textArea);

  node.addDOMWidget("pc_preview", "preview", wrap, { serialize: false });
  node._pcPreviewText = textArea;
  node._pcPreviewRes = resSpan;
}

function updatePreview(node, promptText, resText) {
  if (node._pcPreviewText) {
    node._pcPreviewText.value = promptText|| t("preview_empty");
  }
  if (node._pcPreviewRes) {
    node._pcPreviewRes.textContent = resText ? t("label_resolution") + ": " + resText : "";
  }
}

// ------------------------- 扩展注册 -------------------------

app.registerExtension({
  name: "prompt_composer.config_panel",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) {
      return;
    }
    const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
  this.addWidget("button", t("open_panel"), "open", () => {
        openConfigPanel(this);
     });
      attachPreview(this);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted ? onExecuted.apply(this, arguments) : undefined;
   if (!message) {
        return;
      }
      const promptText = Array.isArray(message.prompt) ? message.prompt[0] : message.prompt;
      const resText = Array.isArray(message.resolution)
        ? message.resolution[0]
        : message.resolution;
      const negativeText = Array.isArray(message.negative)
        ? message.negative[0]
        : message.negative;
      updatePreview(this, promptText, resText);
      // 追加一条生成历史，记录当时的提示词、负面、分辨率与配置。
      try {
        appendHistory({
          prompt: promptText || "",
          negative: negativeText || "",
          resolution: resText || "",
          config: readConfig(this),
          favorite: false,
          time: Date.now(),
        });
      } catch (e) {
        // 历史记录失败不影响主流程。
      }
    };
  },
});
