# FinAlly E2E tests

Playwright suite. Tests run serially against one app and expect a fresh database (01-fresh-start checks $10,000 cash).

In Docker (from the project root):

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down -v
```

Locally against a running app (start it with `LLM_MOCK=true` and a fresh `db/finally.db`):

```bash
cd test && npm install && npx playwright install chromium
BASE_URL=http://localhost:8000 npx playwright test
```
