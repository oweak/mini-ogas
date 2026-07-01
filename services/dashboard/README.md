# dashboard

Mini-OGAS dashboard is a Vue 3 industrial operations console for a distributed
machining factory demo.

## Current UI Direction

The dashboard is designed as a compact industrial management console rather
than a generic admin dashboard. The first version focuses on three workflows:

- Factory Map: central control, workshop nodes, machines, current work orders,
  status, output, yield, tool wear, and sync state.
- Work Order Dispatch: order queue, process routes, progress, priority, blocked
  work, and dispatch recommendations.
- Alarm Handling: alarm confirmation, rule-engine diagnosis, AI suggestion,
  required approval, isolation, and dispatch-change actions.

## Run Locally

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

## Build

```bash
npm run build
```

## Notes

The current version uses local mock data in `src/data.ts`. It is ready to be
connected to `central-api`, `ai-dispatcher`, and `production-planner` once those
services expose stable endpoints.
