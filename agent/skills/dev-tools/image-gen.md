---
name: image-gen
description: |
  AI 图像生成助手，支持文生图和图生图，对接 OpenRouter / 阿里云百炼 / 火山方舟 / Google Gemini。
  内置 API Key 加密管理：Key 以 AES 加密存入 WPS 笔记，解密密钥由「设备ID + 笔记ID + provider」现场派生，本机无需存储额外文件。
  触发词："帮我生图""文生图""图生图""用 AI 画一张""生成一张图""根据这张图生成""垫图生图""用 Flux 生图""用 Gemini 生图"。
  与 wpsnote-cli gen-image 的区别：本 Skill 支持图生图、多服务商选择、更高质量模型，是内置生图的升级替代方案。
metadata:
  version: "2.0.0"
  category: content-creation
  tags: [image, gen-image, flux, gemini, dashscope, openrouter]
  dependencies: [wps-note]
  scripts:
    - comm_script/image_gen.py
---

# Image Gen — AI 图像生成

支持文生图 + 图生图，自动管理 API Key，生成结果可直接插入 WPS 笔记。

---

## 铁律

- **API Key 不得在对话中输出**，无论任何情况
- `encrypt-key` 子命令输出的 `ciphertext_b64` 可以展示（这是密文，不是真实 Key）
- 告警文案必须完整展示，不可省略
- **模型名称不允许修改，不允许用户自定义**。每个 provider 只有唯一一个确认可用的模型，AI 必须严格使用下表中的值，不得根据用户描述、偏好或自行推断填写其他模型名——任何其他模型名均视为幻觉：

| provider | 唯一可用模型（硬编码，不可改动） |
|----------|-----------------------------|
| openrouter | `google/gemini-3.1-flash-image-preview` |
| dashscope（百炼） | `qwen-image-2.0-pro` |
| ark（即梦） | `doubao-seedream-5-0-260128` |
| gemini | `gemini-3-pro-image-preview` |

  用户只能选择用哪个 **provider**，模型由 AI 根据上表自动填入，任何情况下不接受覆盖。

---

## 核心流程

```
确认需求 → 确定 provider + model → 获取/解密 Key → 执行生图 → 询问是否插入笔记
```

---

## Step 1：确认生图需求

询问：

```
请告诉我：
1. 生图描述（prompt）是什么？
2. 有参考图吗？（有 → 图生图；没有 → 文生图）
3. 比例偏好？（1:1 / 16:9 / 9:16 / 4:3 / 3:4，默认 1:1）
```

- **无参考图** → 文生图，全部 provider 可用
- **有参考图** → 图生图，仅 openrouter（本地文件）/ gemini（本地文件）/ ark即梦（公网 URL）支持；百炼不支持图生图

---

## Step 2：确定 Provider

让用户从以下四个 provider 中选一个，模型由 AI 自动填入（见铁律）：

| provider | 特点 | 适合场景 |
|----------|------|---------|
| openrouter | 走代理，文生图 + 图生图（本地文件垫图） | 代理环境，需要图生图 |
| dashscope（百炼） | 国内直连，仅文生图 | 国内网络，纯文生图 |
| ark（即梦） | 国内直连，文生图 + 图生图（垫图须公网 URL） | 国内网络，需要图生图 |
| gemini | 走代理，文生图 + 图生图（本地文件垫图） | 代理环境，Google 直连 |

用户未指定时，根据是否有代理、是否需要图生图主动推荐。

> openrouter / gemini 国内需要代理，询问用户是否提供 `--proxy`。

---

## Step 3：获取 Key

### 3.1 先搜笔记

`search_notes` 搜索 `图像生成 Key`，找到后 `read_note` 读取，在表格中找 provider 对应行，取出 `ciphertext_b64` 和 `note_id`。

找到密文 → 直接进入 **Step 4**（note 模式，脚本自动解密）。

找不到笔记或对应行 → 进入 **Step 3.2**。

### 3.2 向用户索取 Key

```
我需要 {provider} 的 API Key 才能继续。
获取地址：{平台 URL}

请直接粘贴你的 Key：
```

| provider | Key 获取地址 |
|----------|------------|
| openrouter | https://openrouter.ai/workspaces/default/keys |
| dashscope | https://bailian.console.aliyun.com/cn-beijing?tab=model#/api-key |
| ark | https://console.volcengine.com/ark/ |
| gemini | https://aistudio.google.com/app/api-keys |

收到 Key 后询问是否保存（见 Step 3.3）。

### 3.3 询问是否保存 Key

**必须完整展示以下告警：**

---

> ⚠️ **安全风险告知（请认真阅读）**
>
> 如果你选择保存，Key 将以 **AES 加密**后存入 WPS 笔记：
> - 加密密钥由「**本机设备 ID + 笔记 ID + provider**」现场派生，本机无需存储额外文件
> - **WPS 笔记不会获取你的 Key 内容**，密文在其他设备上无法解密
> - ⚠️ 如果你添加了**第三方 MCP 插件**，该插件可读取笔记内容（含密文）
> - ⚠️ 换设备后，同一密文无法解密，需重新保存
>
> **是否保存？**
> A. 保存（我已知悉风险）
> B. 不保存（本次临时使用）

---

**选择保存**：

1. 检查 `图像生成 Key` 笔记是否存在，不存在则 `create_note` 新建（标题 `图像生成 Key`，加 `#图像生成` 标签）

2. 执行加密：
```bash
python3 comm_script/image_gen.py encrypt-key \
    --note-id "{笔记 note_id}" \
    --provider "{provider}" \
    --key "{用户提供的Key}"
```

3. 从输出中取 `ciphertext_b64`，整表替换写入笔记（新增或替换对应 provider 行）：

```xml
<table>
  <tr>
    <td><p><strong>provider</strong></p></td>
    <td><p><strong>ciphertext_b64</strong></p></td>
    <td><p><strong>更新时间</strong></p></td>
  </tr>
  <tr>
    <td><p>{provider}</p></td>
    <td><p>{ciphertext_b64}</p></td>
    <td><p>{当前日期}</p></td>
  </tr>
</table>
```

4. 对话只说：「Key 已加密保存到笔记《图像生成 Key》，下次自动读取。」

**选择不保存**：Key 仅本次使用，直接进入 Step 4，`--key` 直接传字符串。

---

## Step 4：执行生图

### note 模式（已有保存的 Key）

```bash
python3 comm_script/image_gen.py \
    --provider "{provider}" \
    --model "{model}" \
    --key "note:{note_id}" \
    --ciphertext "{ciphertext_b64}" \
    --prompt "{prompt}" \
    [--image "{参考图路径或URL}"] \
    [--proxy "{代理地址}"] \
    --aspect "{比例}" \
    [--size "{分辨率}"] \
    --out "./output"
```

### 临时模式（本次直接使用）

```bash
python3 comm_script/image_gen.py \
    --provider "{provider}" \
    --model "{model}" \
    --key "{用户提供的Key}" \
    --prompt "{prompt}" \
    [--image "{参考图路径或URL}"] \
    [--proxy "{代理地址}"] \
    --aspect "{比例}" \
    --out "./output"
```

执行前告知：「正在调用 {provider} 生成图片，预计 30-120 秒…」

生图完成后，从 `[saved] {路径}` 行获得本地图片路径。

---

## Step 5：询问是否插入笔记

```
图片已生成：{路径}
需要插入到 WPS 笔记吗？
A. 插入当前打开的笔记
B. 插入指定笔记（请告诉我标题）
C. 不用，本地保存就行
```

选择插入时，执行以下步骤：

**1. 获取目标笔记的 anchor_id（必须先做）**
```bash
wpsnote-cli outline --note_id "{note_id}" --json
```
取 `blocks` 数组最后一个元素的 `id` 作为 `anchor_id`。

**2. 插入图片（优先 CLI）**
```bash
wpsnote-cli insert-image \
    --note_id "{note_id}" \
    --anchor_id "{最后一个block的id}" \
    --position "after" \
    --src "{图片本地路径或URL}" \
    --json
```
返回 `block_id` 表示插入成功。

**3. 降级：CLI 失败则用 MCP**
```
insert_image({ note_id: "{note_id}", anchor_id: "{anchor_id}", position: "after", src: "{url或本地路径}" })
```

> ⚠️ `insert-image` 要求目标笔记**当前在 WPS 编辑器中打开**，否则报 `INTERNAL_ERROR`。如果报错，提示用户在 WPS 中打开该笔记后重试。

---

## Step 6：删除 Key

用户说「删除 Key」「清除保存的 Key」「换一个 Key」时：

1. 搜索 `图像生成 Key` 笔记，整表替换删除对应 provider 行
2. 告知：「{provider} 的密文已从笔记中删除。下次生图需重新提供 Key。」

> 无需清理本机文件（note 模式本机本就无存储）。

---

## 常见问题处理

| 场景 | 处理方式 |
|------|---------|
| 解密失败（换了设备） | 提示"换设备后密文不可用，请重新执行保存流程" |
| openrouter / gemini 连接超时 | 提示"国内需要代理，请提供代理地址" |
| 百炼传了参考图 | 自动忽略，告知"百炼不支持图生图" |
| 火山方舟垫图是本地文件 | 提示"须为公网 URL" |
| 依赖未安装 | 提示 `pip install httpx cryptography` |
