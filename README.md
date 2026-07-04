# Prompt Composer

一个面向 ComfyUI 的结构化提示词生成插件。它不是简单的随机标签拼接节点，而是一套带分类采样、约束求解、特征推断和多模型编译的生成引擎。核心逻辑与 ComfyUI 解耦，可以单独作为库使用。

## 特性

- **结构化生成**：标签按分类采样，经约束求解后构成提示词抽象语法树（AST），最后编译成文本，而不是直接拼字符串。
- **约束求解**：处理标签之间的硬依赖（requires）、互斥（conflicts）、蕴含（implies），并做特征层面的冲突消解与自动补全。
- **二创支持**：内置角色 identity 数据，可锁定角色识别特征，在此基础上随机其余分类。
- **标签关联**：基于 Danbooru 共现数据离线挖掘标签关联，支持采样时的关联加成与采样后的自动补词，默认关闭，不影响原有行为。
- **分级控制**：区分全年龄与成人内容，分级过滤贯穿采样与编译。
- **负面提示词**：内置负面词，支持用户追加，支持把互斥淘汰的标签回收进负面。
- **配置面板与检索**：前端提供配置面板、角色检索、标签检索和关联推荐，文案支持中英双语。
- **数据请求驱动**：core 不依赖 ComfyUI，参数通过一份 JSON 配置传入，节点层只负责输入输出。

## 目录结构

```text
Prompt Composer/
├── __init__.py                  ComfyUI节点入口
├── prompt_composer/
│   ├── core/                    核心引擎，不依赖 ComfyUI
│   │   ├── models.py            数据模型
│   │   ├── tag_store.py         标签数据加载
│   │   ├── sampler.py           分类采样器
│   │   ├── constraint_resolver.py  约束求解
│   │   ├── feature_inference.py 特征推断
│   │   ├── ast_builder.py       AST 构建
│   │   ├── compiler.py          编译器
│   │   ├── pipeline.py          生成流程入口
│   │   ├── identity_store.py    角色数据加载
│   │   ├── association_store.py 标签关联加载与查询
│   │   └── ...
│   ├── nodes/                   ComfyUI节点适配层与只读路由
│   ├── data/
│   │   ├── semantic/       分类语义数据（随仓库提交）
│   │   ├── associations.json    标签关联数据（离线生成后提交）
│   │   ├── tags_index.json      标签检索索引
│   │   ├── identities_index.json 角色检索索引
│   │   └── raw/                 原始大数据（不进仓库，仅供离线脚本使用）
│   └── tools/                   离线数据处理脚本
├── web/                         前端脚本与 i18n
├── tests/                       单元测试
└── docs/                        设计与路线文档
```

## 安装

把整个目录放到 ComfyUI 的 `custom_nodes` 下，重启 ComfyUI 即可。目录名建议用`ComfyUI-Prompt-Composer`。

```text
ComfyUI/custom_nodes/ComfyUI-Prompt-Composer/
```

运行时的 core 与节点层只用 Python 标准库，无需额外安装依赖。只有在本地运行 `tools/` 下的离线数据脚本时才需要 `PyYAML`。

```bash
pip install pyyaml
```

## 使用

在 ComfyUI 里添加 `Prompt Composer Generate` 节点。节点有两个输入：

- `seed`：随机种子。
- `config`：一份 JSON 配置，涵盖采样方式、分级、固定词、禁用词、随机分类、权重、负面词、关联加成等全部参数。

节点提供配置面板，可视化编辑上述参数，无需手写 JSON。面板内含角色检索、标签检索和关联推荐。

节点输出：

- `prompt`：正向提示词。
- `negative`：负面提示词。
- `ast_json`：结构化 AST。
- `debug_log`：生成过程日志。
- `width` / `height`：建议分辨率。

## 数据说明

数据分三层，加载优先级从低到高为 Semantic、Rules、User，后者覆盖前者。

- **Semantic 层**（`data/semantic/`）：各分类标签的基础数据，随仓库提交。
- **Rules overlay**（`data/semantic/rules/overlay.json`）：人工维护的约束规则，叠加在语义层之上。
- **User 层**（`data/user/`）：用户本地覆盖，因人而异，不进仓库。

标签关联数据（`data/associations.json`）由离线脚本从 Danbooru 共现数据挖掘产出，随仓库提交，运行时按需加载。关联数据缺失时，相关功能退化为无关联，不影响默认生成。

原始数据（`data/raw/`）体积很大，只用于离线跑数据脚本，不进仓库，需自行准备。

## 工具脚本

`tools/` 下的脚本均为离线运行，产物随仓库提交，不在 ComfyUI 启动时执行，保持启动零开销。

- `import_danbooru.py`：从 Danbooru 原始数据导入并生成语义层分类数据。
- `build_identities.py`：生成角色 identity 数据。
- `build_tag_index.py`：生成标签检索索引。
- `build_identity_index.py`：生成角色检索索引。
- `build_associations.py`：从共现数据挖掘标签关联，产出关联文件与候选清单。

以标签关联为例：

```bash
# 只统计不写入
python prompt_composer/tools/build_associations.py --dry-run

# 正式生成
python prompt_composer/tools/build_associations.py
```

## 测试

使用标准库 unittest：

```bash
python -m unittest discover -s tests
```

## 设计原则

- core不依赖 ComfyUI，ComfyUI 只是其中一个前端。
- 请求驱动，参数通过配置传入，默认行为稳定。
- 关系数据由离线脚本产出并提交仓库，不在启动时生成。
- 前端文案统一走 i18n。

更多设计背景见 `docs/Prompt_Composer_Roadmap.md`。
