# bgstreamboy

Stream Deck companion for Hearthstone Battlegrounds. Renders live numeric buff state on a 15-button (5×3) Stream Deck.

Two halves:

- `companion/` — Python service that tails Hearthstone's `Power.log` and broadcasts run state over a local WebSocket.
- `plugin/` — Stream Deck plugin (TypeScript / Node) that subscribes and renders the grid.

macOS-native. No Windows dependency.

## Status

v1 in progress. See [the plan](https://example.invalid) — currently working through Step 1 (data-path spike).

## Install (once v1 ships)

```sh
# 1. Companion
brew install uv
uv tool install bgstreamboy-companion
bgstreamboy --install-log-config   # writes ~/Library/Preferences/Blizzard/Hearthstone/log.config
# Restart Hearthstone so the new log config takes effect.
bgstreamboy                        # starts the WebSocket service on ws://localhost:8765

# 2. Stream Deck plugin
cd plugin
npm install
npm run build
npm run link                       # registers the plugin with Stream Deck Mac app
```

Open Hearthstone → BG lobby. The Stream Deck switches to the BG Stream Boy profile automatically.

## Development

See `companion/README.md` and `plugin/README.md`.
