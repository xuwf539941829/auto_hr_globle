# Auto HR Copilot

一个全新搭建的自动招聘项目骨架，和仓库里的 [`webBossAI.py`](E:/project/auto_hr/webBossAI.py) / [`config.json`](E:/project/auto_hr/config.json) 解耦，后续会把 Boss 执行能力以连接器形式接进来。

## 当前包含

- `frontend/`
  - Next.js WebUI 骨架
  - 工作台
  - 画像设计页
  - 候选人筛选页
  - 候选人详情页
  - 反馈学习页
- `backend/`
  - FastAPI API 骨架
  - 岗位 / 画像 / 候选人 / 反馈 / 任务路由
  - 内存态 mock 数据服务
  - Boss 职位列表连接器
  - JD 转译服务：LLM 优先，规则引擎兜底

## 目录说明

```text
frontend/
backend/
docs/
webBossAI.py        # 保留原样，未修改
config.json         # 保留原样，未修改
```

## 启动方式

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认地址：
- API: `http://127.0.0.1:8000`
- 文档: `http://127.0.0.1:8000/docs`

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：
- WebUI: `http://127.0.0.1:3000`

## Boss 在线职位列表

如果要读取 Boss 当前登录账号的在线职位列表，需要满足两点：

1. Chrome 已登录 Boss 招聘账号
2. Chrome 以远程调试方式启动，例如 `--remote-debugging-port=9222`

系统会优先调用 Boss 的在线岗位接口；失败时自动回退到本地 mock 数据。

## LLM 转译配置

现在 JD 转译支持“LLM 优先，规则兜底”。

只要给后端进程配置下面这些环境变量，就会优先走大模型结构化转译：

```bash
AUTO_HR_LLM_API_KEY=你的密钥
AUTO_HR_LLM_BASE_URL=https://api.openai.com/v1
AUTO_HR_LLM_MODEL=gpt-4.1-mini
AUTO_HR_LLM_API_STYLE=chat_completions
AUTO_HR_LLM_TIMEOUT_SECONDS=45
```

说明：

- `AUTO_HR_LLM_API_KEY`
  - 必填。不配置时会自动回退到规则转译
- `AUTO_HR_LLM_BASE_URL`
  - 可选，默认是 OpenAI 兼容地址
- `AUTO_HR_LLM_MODEL`
  - 可选，指定调用的模型
- `AUTO_HR_LLM_API_STYLE`
  - 可选，支持 `chat_completions` 和 `responses`
- `AUTO_HR_LLM_TIMEOUT_SECONDS`
  - 可选，请求超时时间

## 当前实现状态

这是一版能跑起来的产品骨架，重点是把核心流程搭通：

1. JD 编辑后可重新转译
2. 转译接口优先尝试 LLM 结构化输出
3. 当模型未配置、请求失败或 JSON 不合法时，自动回退到规则引擎
4. 页面会展示当前画像来自 `LLM 转译` 还是 `规则兜底`
5. 招聘职位列表会优先从 Boss 当前登录账号的在线岗位接口读取

## 下一步建议

1. 把“保存校准”接成真实接口
2. 把用户人工校准内容参与下一轮转译 prompt
3. 增加转译日志和原始模型返回审计
4. 把候选人筛选也切到 LLM 证据审计链路
