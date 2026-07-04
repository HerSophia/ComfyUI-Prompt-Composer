// Prompt Composer 前端 i18n。
//
// 一个轻量的多语言取词模块，不依赖 ComfyUI 内部 API。
// 语言表结构为 { 语言code: { key: 文案 } }。
// 通过 t(key) 取词，找不到时回退到英文，再找不到就返回 key 本身。

const MESSAGES = {
  zh_CN: {
    // 节点按钮
    open_panel: "打开配置面板",

    // 配置面板
    panel_title: "Prompt Composer 配置",
    section_basic: "基础设置",
    section_character: "角色",
    section_fixed_tags: "固定词",
    section_disabled_tags: "禁用词",
    section_random_categories: "随机分类",
    section_lock_categories: "锁定分类",

    label_sampler: "采样方式",
    label_rating: "分级",
    label_return_debug: "返回调试日志",

    sampler_weighted: "按权重",
    sampler_random: "纯随机",
    rating_general: "全年龄",
    rating_explicit: "成人",

    current_character: "当前角色",
    character_none: "无（原创）",
    btn_choose_character: "选择角色",
    btn_clear_character: "清除",

    placeholder_fixed_tags: "每行一个，或用逗号分隔",
    placeholder_disabled_tags: "每行一个，或用逗号分隔",

    btn_confirm: "确定",
    btn_cancel: "取消",

    // 角色检索子面板
    search_title: "检索角色",
   search_placeholder: "输入中文名或英文 id 搜索",
    search_loading: "正在加载角色索引……",
    search_no_match: "没有匹配的角色。",
    search_result_count: "共 {n} 条。",
    search_result_truncated: "结果较多，只显示前 {n} 条，请继续输入以缩小范围。",
    search_no_zh_name: "(无中文名)",
    search_load_failed: "加载角色索引失败",

    // 提示词预览
    preview_title: "最新提示词",
    preview_empty: "尚未生成，运行一次后在此显示。",
    label_resolution: "分辨率",

    // 分类名
    cat_hair: "头发",
    cat_eyes: "眼睛",
    cat_clothing: "服装",
    cat_expression: "表情",
    cat_pose: "姿态",
    cat_hand: "手部",
    cat_leg: "腿部",
    cat_camera: "镜头",
    cat_composition: "构图",
    cat_background: "背景",
  cat_lighting: "光照",
    cat_nsfw_act: "NSFW 动作",
    cat_nsfw_body: "NSFW 身体",
    cat_nsfw_gear: "NSFW 道具",

    // 采样方式说明
    btn_help: "？",
    sampler_help_weighted: "按权重：依据标签热度加权随机，热门标签更容易被选中，结果更常见、更稳定。",
    sampler_help_random: "纯随机：所有候选标签等概率随机，冷门标签机会均等，结果更多样。",

    // 标签检索
    btn_search_tag: "检索标签",
    tag_search_title: "检索标签",
    tag_search_placeholder: "输入中文或英文标签搜索",
    tag_search_load_failed: "加载标签索引失败",

    // 分辨率
    label_resolution_mode: "分辨率模式",
    resolution_auto: "自动推断",
    resolution_manual: "手动指定",
    label_width: "宽",
    label_height: "高",

    // 权重
    section_weights: "标签权重",
    weights_hint: "每行一个，格式为 标签:权重，例如 1girl:1.2。权重范围 0.6 到 1.5，等于 1 不加权。",
    placeholder_weights: "标签:权重，每行一个",

    //负面词
    section_negative: "负面提示词",
    label_use_builtin_negative: "启用内置负面词",
    label_recycle_conflict: "回收互斥淘汰标签进负面",
    section_user_negative: "用户负面词",
    placeholder_user_negative: "每行一个，或用逗号分隔",

    // 预设与历史
    section_preset_history: "预设与历史",
    btn_open_preset: "预设",
    btn_open_history: "历史",
    preset_title: "配置预设",
    btn_save_preset: "保存当前为预设",
    preset_name_prompt: "请输入预设名：",
    preset_overwrite_confirm: "已存在同名预设，是否覆盖？",
    preset_empty: "还没有预设。",
    btn_load: "载入",
    btn_delete: "删除",
    btn_export: "导出",
    btn_import: "导入",
    history_title: "生成历史",
    history_empty: "还没有历史记录。",
    btn_clear_history: "清空历史",
    btn_reload_config: "载入配置",
    btn_favorite: "收藏",
    btn_unfavorite: "取消收藏",
    history_prompt_label: "提示词",
    history_negative_label: "负面",
    history_resolution_label: "分辨率",
    history_favorite_mark: "★",
    import_prompt: "请粘贴导出的 JSON：",
    import_failed: "导入失败，JSON 格式不正确。",

    // 关联加成与自动追加
    section_association: "关联推荐",
    label_association_boost: "开启关联加成",
    label_association_strength: "加成强度",
label_auto_add_requires: "自动补充硬依赖",
    label_auto_add_related: "自动补充软关联",

    // 标签检索内的关联推荐区
    assoc_rec_title: "关联推荐",
  assoc_rec_btn: "关联",
    assoc_rec_loading: "正在加载关联词……",
    assoc_rec_empty: "没有可推荐的关联词。",
    assoc_load_failed: "加载关联词失败",
  },

  en: {
    open_panel: "Open Config Panel",

    panel_title: "Prompt Composer Config",
    section_basic: "Basic",
    section_character: "Character",
    section_fixed_tags: "Fixed Tags",
    section_disabled_tags: "Disabled Tags",
    section_random_categories: "Random Categories",
    section_lock_categories: "Locked Categories",

    label_sampler: "Sampler",
    label_rating: "Rating",
    label_return_debug: "Return Debug Log",

    sampler_weighted: "Weighted",
    sampler_random: "Random",
    rating_general: "General",
    rating_explicit: "Explicit",

    current_character: "Current",
   character_none: "None (original)",
    btn_choose_character: "Choose Character",
    btn_clear_character: "Clear",

    placeholder_fixed_tags: "One per line, or comma-separated",
    placeholder_disabled_tags: "One per line, or comma-separated",

    btn_confirm: "OK",
    btn_cancel: "Cancel",

 search_title: "Search Character",
    search_placeholder: "Search by Chinese name or English id",
    search_loading: "Loading character index...",
    search_no_match: "No matching character.",
    search_result_count: "{n} results.",
    search_result_truncated:
      "Too many results, showing first {n}. Keep typing to narrow down.",
    search_no_zh_name: "(noname)",
    search_load_failed: "Failed to load character index",

    preview_title: "Latest Prompt",
    preview_empty: "Not generated yet. Run once to see it here.",
    label_resolution: "Resolution",

    cat_hair: "Hair",
    cat_eyes: "Eyes",
    cat_clothing: "Clothing",
    cat_expression: "Expression",
    cat_pose: "Pose",
    cat_hand: "Hand",
    cat_leg: "Leg",
    cat_camera: "Camera",
    cat_composition: "Composition",
    cat_background: "Background",
    cat_lighting: "Lighting",
    cat_nsfw_act: "NSFW Act",
    cat_nsfw_body: "NSFW Body",
    cat_nsfw_gear: "NSFW Gear",

  btn_help: "?",
    sampler_help_weighted:
      "Weighted: weighted random by tag popularity, popular tags are picked more often, results are more common and stable.",
    sampler_help_random:
      "Random: all candidatetags have equal probability, rare tags get equal chance, results are more diverse.",

    btn_search_tag: "Search Tag",
    tag_search_title: "Search Tag",
    tag_search_placeholder: "Search by Chinese or English tag",
    tag_search_load_failed: "Failed to load tag index",

    label_resolution_mode: "Resolution Mode",
    resolution_auto: "Auto",
    resolution_manual: "Manual",
    label_width: "W",
    label_height: "H",

    section_weights: "Tag Weights",
    weights_hint: "One per line, format tag:weight, e.g. 1girl:1.2. Range 0.6 to 1.5, weight 1 means no weighting.",
    placeholder_weights: "tag:weight, one per line",

    section_negative: "Negative Prompt",
    label_use_builtin_negative: "Enable Built-in Negatives",
    label_recycle_conflict: "Recycle Conflicting Tags Into Negative",
    section_user_negative: "User Negatives",
    placeholder_user_negative: "One per line, or comma-separated",

    section_preset_history: "Presets & History",
    btn_open_preset: "Presets",
    btn_open_history: "History",
    preset_title: "Config Presets",
    btn_save_preset: "Save Current As Preset",
    preset_name_prompt: "Enter preset name:",
    preset_overwrite_confirm: "A preset with this name exists. Overwrite?",
    preset_empty: "No presets yet.",
    btn_load: "Load",
    btn_delete: "Delete",
    btn_export: "Export",
    btn_import: "Import",
    history_title: "Generation History",
    history_empty: "No history yet.",
    btn_clear_history: "Clear History",
    btn_reload_config: "Load Config",
    btn_favorite: "Favorite",
    btn_unfavorite: "Unfavorite",
    history_prompt_label: "Prompt",
    history_negative_label: "Negative",
    history_resolution_label: "Resolution",
    history_favorite_mark: "★",
    import_prompt: "Paste the exported JSON:",
    import_failed: "Import failed, invalid JSON.",

    section_association: "Associations",
    label_association_boost: "Enable Association Boost",
    label_association_strength: "Boost Strength",
   label_auto_add_requires: "Auto Add Required Tags",
    label_auto_add_related: "Auto Add Related Tags",

    assoc_rec_title: "Related",
    assoc_rec_btn: "Related",
    assoc_rec_loading: "Loading related tags...",
    assoc_rec_empty: "No related tags to recommend.",
    assoc_load_failed: "Failed to load related tags",
  },
};

// 判定当前语言：navigator.language 以 zh 开头用 zh_CN，否则 en，默认 zh_CN。
function detectLang() {
  try {
    const raw = (navigator.language || navigator.userLanguage || "zh_CN").toLowerCase();
    if (raw.startsWith("zh")) {
      return "zh_CN";
    }
    return "en";
  } catch (e) {
    return "zh_CN";
  }
}

const CURRENT_LANG = detectLang();

// 取词。支持 {n} 这类占位符替换，params 例如 { n: 50 }。
export function t(key, params) {
  const table = MESSAGES[CURRENT_LANG] || MESSAGES.en;
  let text = table[key];
  if (text === undefined) {
    text = (MESSAGES.en && MESSAGES.en[key]) !== undefined ? MESSAGES.en[key] : key;
  }
  if (params) {
    for (const name of Object.keys(params)) {
      text = text.replace("{" + name + "}", String(params[name]));
    }
  }
  return text;
}

export function currentLang() {
  return CURRENT_LANG;
}
