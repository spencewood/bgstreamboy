/** Mirror of the JSON shape emitted by the companion service. */

export type Mode = "solo" | "duos" | "unknown";
export type Phase = "recruit" | "combat" | "hero_select" | "shopping" | "other" | "unknown";

export interface Buff {
  type: string;
  label?: string | null;
  attack?: number | null;
  health?: number | null;
  value?: number | null;
  current?: number | null;
  target?: number | null;
  last_changed: number;
}

export interface Side {
  buffs: Buff[];
}

export interface Tribe {
  name: string;
  remaining: number | null;
  max: number | null;
}

export interface Snapshot {
  mode: Mode;
  phase: Phase;
  player: Side;
  ally: Side | null;
  tribes: Tribe[];
}
