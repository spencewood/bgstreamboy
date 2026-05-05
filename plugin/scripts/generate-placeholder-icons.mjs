/* Generate placeholder PNG assets referenced by the manifest, so the plugin
 * validates and loads. These are intentionally minimal — replace with real
 * artwork before publishing.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { createCanvas } from "@napi-rs/canvas";

const PLUGIN_DIR = resolve(import.meta.dirname, "..", "com.bgstreamboy.companion.sdPlugin");

function write(path, draw, size) {
  const full = resolve(PLUGIN_DIR, path);
  mkdirSync(dirname(full), { recursive: true });
  const canvas = createCanvas(size, size);
  draw(canvas.getContext("2d"), size);
  writeFileSync(full, canvas.toBuffer("image/png"));
  console.log(`wrote ${path} (${size}×${size})`);
}

function drawDisc(color) {
  return (ctx, size) => {
    ctx.fillStyle = "#101010";
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size * 0.32, 0, Math.PI * 2);
    ctx.fill();
  };
}

// Action key icon (used as default art on placed buttons before the WS arrives).
write("imgs/actions/slot/key.png", drawDisc("#3a3a3a"), 144);
write("imgs/actions/slot/key@2x.png", drawDisc("#3a3a3a"), 288);

// Action list icon (small image in the actions list pane).
write("imgs/actions/slot/icon.png", drawDisc("#cc6633"), 28);
write("imgs/actions/slot/icon@2x.png", drawDisc("#cc6633"), 56);

// Category icon (small image next to "BG Companion" in the actions pane).
write("imgs/plugin/category-icon.png", drawDisc("#cc6633"), 28);
write("imgs/plugin/category-icon@2x.png", drawDisc("#cc6633"), 56);

// Marketplace icon (large image when the plugin is browsed in the store).
write("imgs/plugin/marketplace.png", drawDisc("#cc6633"), 288);
write("imgs/plugin/marketplace@2x.png", drawDisc("#cc6633"), 576);
