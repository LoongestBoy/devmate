# 内部前端与 FastAPI 规范 (Project Guidelines)

## 1. 项目模板规范
所有的 Web 项目都必须包含以下基础结构：
- `index.html`: 主页入口
- `styles.css`: 全局样式文件
- `app.js`: 前端交互逻辑
- `pyproject.toml`: 统一使用 uv 管理依赖

## 2. API 设计最佳实践
- 所有 FastAPI 路由必须带有明确的 `response_model`。
- 必须使用 `CORS` 中间件以允许前端跨域请求。
- 推荐将业务逻辑与路由层分离，保持代码的整洁与可测试性。