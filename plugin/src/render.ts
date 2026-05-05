/** Compose buff icon (emoji) + numeric value into a 144×144 PNG data URL.
 *
 * Stream Deck's setTitle has no per-update styling, so values are drawn
 * into the image itself via @napi-rs/canvas. Each buff type maps to a color
 * emoji + tint color; emoji renders crisply at any size and reads cleanly
 * even at the deck's typical viewing angles.
 */

import { Canvas, createCanvas, type SKRSContext2D } from "@napi-rs/canvas";

import type { Buff, Tribe } from "./snapshot";

const SIZE = 144;

interface BuffIcon {
  emoji: string;
  tint: string; // hex color #rrggbb
}

const BUFF_ICONS: Record<string, BuffIcon> = {
  bloodgem:            { emoji: "💎", tint: "#b22020" },
  bloodgem_player:     { emoji: "💎", tint: "#b22020" },

  // Counters
  eternal_knight:      { emoji: "💀", tint: "#5c8de0" },
  ballers_sold:        { emoji: "🔥", tint: "#e07020" },
  pogos_played:        { emoji: "⬆️", tint: "#5cc474" },
  whelps_summoned:     { emoji: "🐲", tint: "#8868c0" },
  boars_died:          { emoji: "🐗", tint: "#c0a040" },
  automatons_summoned: { emoji: "🤖", tint: "#a0a0a8" },
  sanlayn_died:        { emoji: "🦇", tint: "#a02020" },
  orcestra_played:     { emoji: "🎺", tint: "#a06030" },

  // Stat-pair trackers (named after the source mechanic)
  deep_blues:          { emoji: "🐟", tint: "#3060c0" },
  jewelry_box:         { emoji: "💍", tint: "#d8c050" },
  tavern_spell:        { emoji: "📜", tint: "#7a4ec4" },
  big_brother:         { emoji: "👁️", tint: "#9050b0" },
  temp_tavern_spell:   { emoji: "📜", tint: "#5e3aa4" },
  whelp_buff:          { emoji: "🥚", tint: "#cc6633" },
  tavern_minion_buff:  { emoji: "✨", tint: "#e8c948" },
  cursed_crystal:      { emoji: "🔮", tint: "#702070" },
  horde_hoard:         { emoji: "🪓", tint: "#993333" },
  dazzling_lightspawn: { emoji: "🌟", tint: "#e0a040" },
  undying_army:        { emoji: "🧟", tint: "#8855cc" },
  dancing_barnstormer: { emoji: "💃", tint: "#cc4070" },
  humming_bird:        { emoji: "🐦", tint: "#40a060" },
  diremuck:            { emoji: "🌿", tint: "#306030" },
  nomi_sticker:        { emoji: "🍳", tint: "#e08040" },
  beetle_army:         { emoji: "🪲", tint: "#506030" },
  dune_dweller:        { emoji: "🏜️", tint: "#c0a060" },
  nether_construct:    { emoji: "🌌", tint: "#3a3a78" },
  archimonde:          { emoji: "👹", tint: "#7a3a3a" },
  align_elements:      { emoji: "🌀", tint: "#3a8fbf" },
  blazing_greasefire:  { emoji: "🔥", tint: "#e07040" },
  haunted_carapace:    { emoji: "👻", tint: "#7878a0" },
  improviser:          { emoji: "🎭", tint: "#c060a0" },
  felblaze_leader:     { emoji: "💚", tint: "#40a040" },
  gleaming_trader:     { emoji: "💰", tint: "#d8c050" },
  volumizer:           { emoji: "💪", tint: "#a04040" },
  nomi_kitchen_dream:  { emoji: "🍳", tint: "#e08040" },
  timewarped_goldrinn: { emoji: "🐺", tint: "#a06040" },
  fodder_refresh:      { emoji: "♻️", tint: "#5cc474" },
  tier3_shop_buff:     { emoji: "🏪", tint: "#7a8eb4" },
  consummate_conqueror: { emoji: "👑", tint: "#c0a040" },
  fang_anklet:         { emoji: "🐾", tint: "#9c5a3a" },
  dark_dazzler:        { emoji: "🌑", tint: "#5a3a78" },
  manari_messenger:    { emoji: "📯", tint: "#9050b0" },
  goldrinn:            { emoji: "🐺", tint: "#a06040" },
  nomi:                { emoji: "🍳", tint: "#e08040" },

  // Spec items not yet wired (here as approximations once their extractors land)
  magnetic:            { emoji: "🧲", tint: "#a0a0a8" },
  lightfang_aura:      { emoji: "✨", tint: "#e8c948" },
  spellcraft:          { emoji: "📖", tint: "#7a4ec4" },
  souleater_scythe:    { emoji: "🔪", tint: "#5a3a78" },
  tethys_growing:      { emoji: "🏴‍☠️", tint: "#d8c050" },
  reborn_preview:      { emoji: "🔄", tint: "#e09030" },
  resummon_preview:    { emoji: "♻️", tint: "#e09030" },
  trinket_numeric:     { emoji: "🎁", tint: "#c0a040" },
  dark_gift_numeric:   { emoji: "🎁", tint: "#702070" },
  quest_progress:      { emoji: "📜", tint: "#3a8fbf" },
};

const FALLBACK_ICON: BuffIcon = { emoji: "❓", tint: "#444448" };

/** Per-tribe visual identity. */
const TRIBE_ICONS: Record<string, BuffIcon> = {
  dragon:    { emoji: "🐲", tint: "#7a4ec4" },
  murloc:    { emoji: "🐟", tint: "#3060c0" },
  demon:     { emoji: "👹", tint: "#7a3a3a" },
  beast:     { emoji: "🐺", tint: "#90a040" },
  mech:      { emoji: "🤖", tint: "#a0a0a8" },
  elemental: { emoji: "🔥", tint: "#e07020" },
  pirate:    { emoji: "🏴‍☠️", tint: "#5a4a30" },
  undead:    { emoji: "💀", tint: "#7878a0" },
  naga:      { emoji: "🐍", tint: "#40a060" },
  quilboar:  { emoji: "🐗", tint: "#9c5a3a" },
};

/** Display label per buff type. Falls back to the buff's `label` field, then `type`. */
const LABELS: Record<string, string> = {
  bloodgem: "Blood Gem",
  bloodgem_player: "Blood Gem",
  eternal_knight: "E. Knight",
  ballers_sold: "Ballers",
  pogos_played: "Pogos",
  whelps_summoned: "Whelps",
  boars_died: "Boars",
  automatons_summoned: "Automatons",
  sanlayn_died: "San'layn",
  orcestra_played: "Orc-estra",
  deep_blues: "Deep Blues",
  jewelry_box: "Jewelry Box",
  tavern_spell: "Tavern Spell",
  big_brother: "Big Brother",
  temp_tavern_spell: "Tavern Spell",
  whelp_buff: "Whelp Buff",
  tavern_minion_buff: "Tavern Buff",
  cursed_crystal: "Cursed Crystal",
  horde_hoard: "Horde",
  dazzling_lightspawn: "Lightspawn",
  undying_army: "Undying",
  dancing_barnstormer: "Barnstormer",
  humming_bird: "Humming Bird",
  diremuck: "Diremuck",
  nomi_sticker: "Nomi Sticker",
  beetle_army: "Beetles",
  dune_dweller: "Dune",
  nether_construct: "Nether",
  archimonde: "Archimonde",
  align_elements: "Align",
  blazing_greasefire: "Greasefire",
  haunted_carapace: "Carapace",
  improviser: "Improviser",
  felblaze_leader: "Felblaze",
  gleaming_trader: "Gleaming",
  volumizer: "Volumizer",
  nomi_kitchen_dream: "Nomi Dream",
  timewarped_goldrinn: "Goldrinn TW",
  fodder_refresh: "Fodder",
  tier3_shop_buff: "Tier 3",
  consummate_conqueror: "Conqueror",
  fang_anklet: "Fang",
  dark_dazzler: "Dazzler",
  manari_messenger: "Man'ari",
  goldrinn: "Goldrinn",
  nomi: "Nomi",
  magnetic: "Magnetic",
  lightfang_aura: "Lightfang",
  spellcraft: "Spellcraft",
  souleater_scythe: "Scythe",
  tethys_growing: "Tethys",
  reborn_preview: "Reborn",
  resummon_preview: "Resummon",
  trinket_numeric: "Trinket",
  dark_gift_numeric: "Dark Gift",
  quest_progress: "Quest",
};

/** Kept for grid.ts compatibility; emoji rendering loads no external assets. */
export async function preloadIcons(): Promise<void> {
  // no-op
}

export function renderBlank(): string {
  const canvas = createCanvas(SIZE, SIZE);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#08080a";
  ctx.fillRect(0, 0, SIZE, SIZE);
  return toDataURL(canvas);
}

export function renderDisconnected(): string {
  return renderStatusTile({
    bgTop: "#1c1416",
    bgBottom: "#070304",
    emoji: "🔌",
    label: "offline",
    labelColor: "#a06070",
  });
}

export function renderConnecting(): string {
  return renderStatusTile({
    bgTop: "#1c1c24",
    bgBottom: "#06060a",
    emoji: "🔄",
    label: "linking…",
    labelColor: "#7090c0",
  });
}

function renderStatusTile(opts: {
  bgTop: string;
  bgBottom: string;
  emoji: string;
  label: string;
  labelColor: string;
}): string {
  const canvas = createCanvas(SIZE, SIZE);
  const ctx = canvas.getContext("2d");

  const bg = ctx.createLinearGradient(0, 0, 0, SIZE);
  bg.addColorStop(0, opts.bgTop);
  bg.addColorStop(1, opts.bgBottom);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Emoji glyph centered slightly above the label.
  ctx.font = '48px "Apple Color Emoji", "Segoe UI Emoji", sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#FFFFFF";
  ctx.fillText(opts.emoji, SIZE / 2, SIZE * 0.40);

  ctx.font = "600 14px sans-serif";
  ctx.fillStyle = opts.labelColor;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(opts.label, SIZE / 2, SIZE - 18);

  return toDataURL(canvas);
}

export function renderTribe(tribe: Tribe): string {
  const canvas = createCanvas(SIZE, SIZE);
  const ctx = canvas.getContext("2d");
  const icon = TRIBE_ICONS[tribe.name] ?? FALLBACK_ICON;

  // Tribe identity is in the emoji; background color encodes pool fullness
  // (green = healthy, red = nearly empty). When we don't have a fullness
  // ratio, fall back to the tribe's identity tint.
  const haveRatio = tribe.remaining != null && tribe.max && tribe.max > 0;
  const tint = haveRatio ? fullnessColor(tribe.remaining! / tribe.max!) : icon.tint;
  drawSaturatedBackground(ctx, tint);
  drawIconGlyph(ctx, icon.emoji);

  const value = tribe.remaining != null ? `${tribe.remaining}` : "?";
  drawValue(ctx, value, { yBaseline: SIZE - 14 });

  return toDataURL(canvas);
}

/** Background dominated by the tint color, used for tribe tiles where the
 * color carries information (pool fullness). Buffs use the more subdued
 * `drawTintedBackground` since their value text is the primary signal. */
function drawSaturatedBackground(ctx: SKRSContext2D, tint: string): void {
  const r = parseInt(tint.slice(1, 3), 16);
  const g = parseInt(tint.slice(3, 5), 16);
  const b = parseInt(tint.slice(5, 7), 16);

  // Vertical gradient from full saturation (top) to ~50% darker (bottom)
  // so the value text at the bottom stays readable against contrast.
  const gradient = ctx.createLinearGradient(0, 0, 0, SIZE);
  gradient.addColorStop(0, `rgb(${r}, ${g}, ${b})`);
  gradient.addColorStop(1, `rgb(${Math.round(r * 0.35)}, ${Math.round(g * 0.35)}, ${Math.round(b * 0.35)})`);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, SIZE, SIZE);
}

function fullnessColor(ratio: number): string {
  // Green (≥0.6) → Yellow (0.3–0.6) → Red (<0.3).
  const clamped = Math.max(0, Math.min(1, ratio));
  let r: number, g: number, b: number;
  if (clamped >= 0.6) {
    const t = (clamped - 0.6) / 0.4;
    r = Math.round(180 - 130 * t);
    g = Math.round(200 + 20 * t);
    b = Math.round(60 + 10 * t);
  } else if (clamped >= 0.3) {
    const t = (clamped - 0.3) / 0.3;
    r = Math.round(220 - 40 * t);
    g = Math.round(160 + 40 * t);
    b = 50;
  } else {
    const t = clamped / 0.3;
    r = Math.round(200 + 20 * t);
    g = Math.round(40 + 120 * t);
    b = Math.round(40 + 10 * t);
  }
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

export function renderBuff(buff: Buff): string {
  const canvas = createCanvas(SIZE, SIZE);
  const ctx = canvas.getContext("2d");
  const icon = BUFF_ICONS[buff.type] ?? FALLBACK_ICON;

  drawTintedBackground(ctx, icon.tint);
  drawIconGlyph(ctx, icon.emoji);
  drawValue(ctx, displayValue(buff), { yBaseline: SIZE - 14 });

  return toDataURL(canvas);
}

function drawTintedBackground(ctx: SKRSContext2D, tint: string): void {
  const r = parseInt(tint.slice(1, 3), 16);
  const g = parseInt(tint.slice(3, 5), 16);
  const b = parseInt(tint.slice(5, 7), 16);

  const base = ctx.createLinearGradient(0, 0, 0, SIZE);
  base.addColorStop(0, "#15151a");
  base.addColorStop(1, "#050507");
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, SIZE, SIZE);

  const wash = ctx.createRadialGradient(SIZE / 2, SIZE * 0.42, 0, SIZE / 2, SIZE * 0.42, SIZE * 0.7);
  wash.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.30)`);
  wash.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
  ctx.fillStyle = wash;
  ctx.fillRect(0, 0, SIZE, SIZE);
}

function drawIconGlyph(ctx: SKRSContext2D, emoji: string): void {
  ctx.font = '60px "Apple Color Emoji", "Segoe UI Emoji", sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#FFFFFF";
  ctx.fillText(emoji, SIZE / 2, SIZE * 0.42);
}

function drawValue(ctx: SKRSContext2D, text: string, opts: { yBaseline: number }): void {
  const size = text.length <= 4 ? 44 : text.length <= 6 ? 36 : 28;
  ctx.font = `800 ${size}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.shadowColor = "#000000";
  ctx.shadowBlur = 8;
  ctx.shadowOffsetY = 1;
  ctx.fillStyle = "#FFFFFF";
  ctx.fillText(text, SIZE / 2, opts.yBaseline);
  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;
}

function displayValue(buff: Buff): string {
  if (buff.attack != null && buff.health != null) return `+${buff.attack}/+${buff.health}`;
  if (buff.attack != null) return `+${buff.attack}`;
  if (buff.value != null) return `${buff.value}`;
  if (buff.current != null && buff.target != null) return `${buff.current}/${buff.target}`;
  return "?";
}

function toDataURL(canvas: Canvas): string {
  const buf = canvas.toBuffer("image/png");
  return `data:image/png;base64,${buf.toString("base64")}`;
}

export function buffLabel(buff: Buff): string {
  if (buff.label) return buff.label;
  return LABELS[buff.type] ?? buff.type;
}
