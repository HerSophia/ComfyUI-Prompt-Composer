# Prompt Composer ------ 长期路线规划

## 愿景

构建一个**结构化 Prompt 生成引擎**，而不是简单的随机 Tag 节点。

目标：

- Prompt AST（抽象语法树）
- Prompt Grammar（语法）
- Constraint Solver（约束求解）
- Prompt Compiler（编译器）
- 多模型输出（Danbooru / 自然语言 / SDXL 等）
- ComfyUI 只是其中一个前端

------------------------------------------------------------------------

### 总体架构

``` text
Tag Database(JSON/YAML)
        │
Category Sampler
        │
Feature Inference
        │
Constraint Solver
        │
Prompt AST
        │
Compiler
        │
┌───────────────┬──────────────┬──────────────┐
Danbooru     Natural Prompt   SDXL Prompt ...
```

------------------------------------------------------------------------

### 第一阶段（MVP）

目标：完成可用随机 Prompt 系统。

## 节点

- Pose
- Hand
- Leg
- Expression
- Camera
- Composition
- Clothing
- Background
- Lighting

每个节点：

- 内置 Tag 库
- 支持用户输入
- 支持随机
- 支持固定
- 支持权重

输出：

结构化对象，而不是字符串。

------------------------------------------------------------------------

#### Tag 数据

示例：

``` json
{
  "tag":"holding_skirt",
  "category":"gesture",
  "weight":20,
  "requires":["dress"],
  "conflicts":["pants"]
}
```

字段建议：

- tag
- aliases
- category
- weight
- requires
- conflicts
- implies
- features
- priority

------------------------------------------------------------------------

#### Feature 系统

不要直接判断 Tag。

而判断 Feature。

例如：

standing →

- legs_visible=true
- body_state=standing

portrait →

- legs_visible=false
- face_priority=true

Constraint 只认识 Feature。

这样以后新增 Tag 无需改代码。

------------------------------------------------------------------------

#### Constraint Solver

负责：

- requires
- conflicts
- feature conflict
- 自动重采样
- 自动补全依赖

例如：

holding_skirt

需要：

- dress

没有则：

自动补 Dress。

------------------------------------------------------------------------

#### Prompt AST

推荐：

``` text
Character
├── Gender
├── Hair
├── Eyes

Pose
├── Body
├── Hand
├── Leg

Camera
├── Angle
├── Shot

Environment
├── Scene
├── Weather
├── Lighting
```

整个 Workflow 传递 AST。

最后一步才输出文本。

------------------------------------------------------------------------

#### Compiler

目标：

同一个 AST：

输出不同 Prompt。

支持：

##### Danbooru

    1girl,
    smile,
    standing,
    holding_skirt

##### Natural Prompt

    A young woman in a flowing white dress...

##### SDXL

增加权重、质量词等。

------------------------------------------------------------------------

#### Sampling

设计接口：

- RandomSampler
- WeightedSampler
- FixedSampler
- SequentialSampler
- MutationSampler
- EvolutionSampler
- LLMSampler

Sampler 可插拔。

------------------------------------------------------------------------

#### LLM 增强层

本地 Qwen：

输入：

Danbooru Tag

输出：

自然语言 Prompt。

未来：

还能：

- 自动润色
- 自动扩写
- 自动删减
- Prompt Rewrite
- Prompt Explain

------------------------------------------------------------------------

#### 风格包（Style Package）

例如：

Anime Portrait

包含：

- Camera
- Lens
- Lighting
- Expression
- Color Style

一键应用。

------------------------------------------------------------------------

#### Prompt Mutator

例如：

smile

↓

soft_smile

↓

laugh

↓

grin

实现微变异。

------------------------------------------------------------------------

#### JSON Schema

建议统一：

``` json
{
  "character": {},
  "pose": {},
  "camera": {},
  "environment": {},
  "style": {}
}
```

未来所有模块共享。

------------------------------------------------------------------------

#### 插件化

Core：

- Grammar
- AST
- Solver
- Compiler

Adapters：

- ComfyUI
- TavernHeadless
- WebUI
- API
- VSCode

------------------------------------------------------------------------

#### 长期路线

## v0.1

随机节点

## v0.2

Constraint Solver

## v0.3

Prompt AST

## v0.4

Compiler

## v0.5

自然语言输出

## v0.6

Qwen 增强

## v0.7

Style Package

## v0.8

Mutation / Evolution

## v1.0

Prompt Composer Core

一个可独立运行的 Prompt 基础设施项目。
