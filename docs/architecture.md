# Architecture Notes

## Product Flow

1. JD 深度转译
2. 画像对齐与人工校准
3. 证据链深度分析
4. 分级决策与反馈学习

## Backend Modules

- `app/api/`: REST API routes
- `app/models/`: domain models
- `app/schemas/`: request payload schemas
- `app/services/`: in-memory services and future business layer

## Frontend Modules

- `app/`: route pages
- `components/`: reusable UI pieces
- `lib/api.ts`: backend calls with mock fallback
- `lib/mock-data.ts`: offline demo data

## Planned Integrations

- PostgreSQL
- Redis + task queue
- Playwright worker
- Boss connector adapted from legacy implementation
- LLM-driven JD translation and resume audit
