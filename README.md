# bgstreamboy

Stream Deck companion for Hearthstone Battlegrounds. Renders live numeric buff state, the lobby's 5 tribes (with shared-pool color shift), and a recruit/combat phase indicator on whatever Stream Deck you have plugged in.

macOS-native. No Windows dependency. Works on any Stream Deck size (Mini / standard / XL).

## Architecture

Two halves:

- `companion/` — Python service that tails Hearthstone's `Power.log` and broadcasts game state over a local WebSocket.
- `plugin/` — Stream Deck plugin (TypeScript / Node) that subscribes and renders the grid.

## One-time setup

```sh
# 1. Toolchain
brew install uv
# (you also need Node 24+ and the Stream Deck Mac app)

# 2. Install Hearthstone log.config (turns on verbose Power.log writing)
./bgstreamboy install
# Restart Hearthstone after this — it only reads log.config on startup.

# 3. Build + link the plugin into Stream Deck app
./bgstreamboy plugin link
```

Open Stream Deck app, drag instances of the **BG Stream Boy → BG Slot** action onto your profile (any layout, any deck size).

## Daily flow

```sh
./bgstreamboy
```

That's it — companion starts, plugin auto-connects, deck reflects whatever Hearthstone is doing.

## Other commands

```sh
./bgstreamboy demo      # animate the storyboard on your deck (no Hearthstone needed)
./bgstreamboy test      # run the simulator scenarios (no deck needed)
./bgstreamboy install   # write Hearthstone's log.config (one-time)
./bgstreamboy plugin build      # rebuild the Stream Deck plugin bundle
./bgstreamboy plugin restart    # rebuild + force-restart the plugin process
./bgstreamboy plugin link       # register the plugin with Stream Deck (one-time)
./bgstreamboy --replay <file>   # replay a captured Power.log instead of tailing live
./bgstreamboy --help            # full CLI flag reference
```

To run from anywhere:

```sh
ln -s "$(pwd)/bgstreamboy" /usr/local/bin/bgstreamboy
```

## What you'll see on the deck

- **Top rows** (above the bottom row): buff slots. Each placed key fills with whichever buff is currently active — bloodgem, eternal knight, jewelry box, whelp buff, etc. (49 buff types in the catalog.)
- **Bottom row**: the lobby's 5 tribes with current shared-pool counts; color shifts green → yellow → red as a tribe depletes.
- **Phase tint**: cool blue background = recruit; warm red = combat. In duos, combat also swaps the buff display from your buffs to your ally's.
- **Connection state**: 🔌 offline tile if the companion is down, 🔄 linking tile while reconnecting.

## Development

See `companion/README.md` and `plugin/README.md` for the inner workings. Test scenarios live in `companion/tests/scenarios.py` — they use `LogBuilder` to synthesize any Power.log permutation and validate the extractors against it. `tests/demo_on_deck.py` drives the same scenarios through the live WebSocket pipeline so you can see them on a real deck.
