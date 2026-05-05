/** The grid: registry of placed action instances and the snapshot-driven
 * render loop.
 *
 * Layout rule (matches the v1 spec, but device-agnostic):
 *   - If the user has placed actions on multiple rows, the **bottom row**
 *     becomes tribe slots (left-to-right = first 5 lobby tribes).
 *   - All other placed actions are buff slots, ordered top-to-bottom,
 *     left-to-right; new buffs claim the lowest-ordered free slot.
 *   - Single-row placement: all are buff slots, no tribes shown.
 */

import type { KeyAction } from "@elgato/streamdeck";
import streamDeck from "@elgato/streamdeck";

import {
  preloadIcons,
  renderBlank,
  renderBuff,
  renderConnecting,
  renderDisconnected,
  renderTribe,
} from "./render";
import type { Snapshot, Tribe } from "./snapshot";
import { SlotState } from "./state";
import { WsClient, type ConnectionState } from "./ws-client";

const DEFAULT_WS_URL = "ws://127.0.0.1:8765";
const MAX_TRIBES_DISPLAYED = 5;

interface PlacedAction {
  action: KeyAction;
  column: number;
  row: number;
}

class Grid {
  private actions = new Map<string, PlacedAction>();
  private slots = new SlotState();
  private latestSnapshot: Snapshot | null = null;
  private connection: ConnectionState = "disconnected";
  private client: WsClient | null = null;

  async start(): Promise<void> {
    await preloadIcons();
    this.client = new WsClient({
      url: DEFAULT_WS_URL,
      onSnapshot: (snap) => this.handleSnapshot(snap),
      onConnectionChange: (state) => this.handleConnectionChange(state),
      log: (msg, ...rest) => streamDeck.logger.info(msg, ...rest),
    });
    this.client.start();
  }

  registerAction(action: KeyAction, column: number, row: number): void {
    this.actions.set(action.id, { action, column, row });
    this.renderAction(action.id);
  }

  unregisterActionById(actionId: string): void {
    this.actions.delete(actionId);
    this.slots.removeAction(actionId);
  }

  private partitionedActions(): { buffSlotIds: string[]; tribeSlotIds: string[] } {
    if (this.actions.size === 0) return { buffSlotIds: [], tribeSlotIds: [] };

    const placed = [...this.actions.values()];
    const maxRow = Math.max(...placed.map((p) => p.row));
    const minRow = Math.min(...placed.map((p) => p.row));

    // Single-row placement: no tribes, all buffs.
    if (maxRow === minRow) {
      return {
        buffSlotIds: placed
          .slice()
          .sort((a, b) => a.column - b.column)
          .map((p) => p.action.id),
        tribeSlotIds: [],
      };
    }

    const tribeRow = placed
      .filter((p) => p.row === maxRow)
      .sort((a, b) => a.column - b.column)
      .slice(0, MAX_TRIBES_DISPLAYED);

    const buffs = placed
      .filter((p) => p.row !== maxRow)
      .sort((a, b) => a.row - b.row || a.column - b.column);

    return {
      buffSlotIds: buffs.map((p) => p.action.id),
      tribeSlotIds: tribeRow.map((p) => p.action.id),
    };
  }

  private handleSnapshot(snapshot: Snapshot): void {
    this.latestSnapshot = snapshot;
    const source = snapshot.phase === "combat" && snapshot.ally ? snapshot.ally : snapshot.player;
    const { buffSlotIds, tribeSlotIds } = this.partitionedActions();

    const changedBuffs = this.slots.applyBuffs(buffSlotIds, source.buffs);
    for (const id of changedBuffs) this.renderAction(id);
    // Tribes always redraw — count and identity can both change.
    for (const id of tribeSlotIds) this.renderAction(id);
  }

  private handleConnectionChange(state: ConnectionState): void {
    const prev = this.connection;
    this.connection = state;
    if (prev === state) return;
    if (state === "disconnected") {
      this.slots.reset();
      this.latestSnapshot = null;
    }
    for (const id of this.actions.keys()) this.renderAction(id);
  }

  private renderAction(actionId: string): void {
    const placed = this.actions.get(actionId);
    if (!placed) return;

    if (this.connection === "disconnected") {
      void placed.action.setImage(renderDisconnected());
      return;
    }
    if (this.connection === "connecting") {
      void placed.action.setImage(renderConnecting());
      return;
    }

    const { buffSlotIds, tribeSlotIds } = this.partitionedActions();
    const tribeIndex = tribeSlotIds.indexOf(actionId);
    if (tribeIndex >= 0) {
      const tribe: Tribe | undefined = this.latestSnapshot?.tribes[tribeIndex];
      void placed.action.setImage(tribe ? renderTribe(tribe) : renderBlank());
      return;
    }

    if (buffSlotIds.includes(actionId)) {
      const entry = this.slots.get(actionId);
      void placed.action.setImage(entry ? renderBuff(entry.buff) : renderBlank());
      return;
    }

    void placed.action.setImage(renderBlank());
  }
}

export const grid = new Grid();
