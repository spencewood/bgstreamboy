# bgstreamboy plugin

Stream Deck plugin that subscribes to the bgstreamboy companion service and renders live BG buff state on a 5×3 grid.

## Build

```sh
npm install        # also installs runtime deps inside com.bgstreamboy.companion.sdPlugin/
npm run build      # produces com.bgstreamboy.companion.sdPlugin/bin/plugin.js
```

## Develop

```sh
npm run watch      # rebuilds on save and restarts the linked plugin
```

## Try it on your Stream Deck

```sh
npm run link       # tells Stream Deck app to load the plugin from this folder
```

Open Stream Deck app. There should be a new "BG Stream Boy" category in the actions list with one action ("BG Slot"). Drag 15 instances onto a 5×3 profile — one in each cell. (A bundled `.streamDeckProfile` that pre-places these is on the v1 backlog.)

Each `BG Slot` instance figures out its row/column on appear and self-registers with the grid controller. The plugin maintains a single WebSocket connection to `ws://127.0.0.1:8765` (the default companion address) and pushes rendered images to whichever slots are currently placed.

When the companion service is offline, every placed slot renders a uniform "offline" tile.

## Slot assignment

Top 10 cells (rows 1–2) are buff slots. Bottom row (row 3) is reserved (blank in v1).

For buffs, the grid uses the same algorithm spelled out in the project plan:

1. Buff already in a slot → update in place, don't move.
2. Buff is new and a slot is free → place in lowest-numbered free slot.
3. All 10 slots full → evict the slot with the oldest `last_changed`.

This keeps muscle memory stable; only eviction priority depends on recency.

## Files

- `src/plugin.ts` — entry; wires the action and starts the grid
- `src/actions/bg-slot.ts` — `SingletonAction` subclass; reports each placed instance to the grid
- `src/grid.ts` — owns the WebSocket client and dispatches snapshots to placed slots
- `src/state.ts` — pure slot-assignment logic
- `src/render.ts` — `@napi-rs/canvas` image composition (icon + value overlay)
- `src/ws-client.ts` — reconnecting WebSocket client
- `src/snapshot.ts` — TS mirror of the companion's JSON schema
- `com.bgstreamboy.companion.sdPlugin/manifest.json` — plugin metadata
- `com.bgstreamboy.companion.sdPlugin/imgs/` — placeholder PNG assets (regenerate via `node scripts/generate-placeholder-icons.mjs`)
