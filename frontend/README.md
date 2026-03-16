# Frontend

React + TypeScript + Vite frontend for the Ambience AI application.

## Local setup

1. Install dependencies:

```bash
npm install
```

2. Create local env config:

```bash
cp .env.example .env
```

3. Start the dev server:

```bash
npm run dev
```

By default the frontend expects the backend at `http://localhost:8000`.

## Commands

- `npm run dev` - start the Vite dev server
- `npm run build` - type-check and build production assets
- `npm run lint` - run ESLint
- `npm run test` - run Vitest once
- `npm run test:coverage` - run tests with coverage
- `npm run test:e2e` - run Playwright tests

## Test layout

Tests live in [`tests/`] and mirror the source structure:

- `tests/components`
- `tests/contexts`
- `tests/hooks`
- `tests/pages`
- `tests/services`
- `tests/utils`

## Notes

- API calls are configured through `VITE_API_URL`
- coverage output is generated under `coverage/` and is ignored by git
