# ProofPatch web dashboard

React + Vite + TypeScript developer dashboard for ProofPatch.

## Development

```bash
cd apps/web
npm install
npm run dev        # http://localhost:5173 (proxies /api to 127.0.0.1:8000)
```

Start the API first:

```bash
uvicorn proofpatch_api.main:app --port 8000
```

## Build

```bash
npm run build      # outputs to apps/web/dist (served by the API if present)
```
