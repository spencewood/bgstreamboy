/** Slot-assignment state.
 *
 * Maintains stable physical positions for buff types: a buff already on a
 * slot stays put on update; new buffs claim the lowest-ordered free slot
 * (per the supplied action ordering); when all placed slots are full, the
 * oldest-changed slot is evicted to make room.
 *
 * Slots are keyed by action id rather than a flat index so the grid is
 * device-agnostic — works for Stream Deck Mini (6), standard (15), XL (32),
 * or any subset the user has placed.
 */

import type { Buff } from "./snapshot";

export interface SlotEntry {
  buff: Buff;
}

export class SlotState {
  private slots = new Map<string, SlotEntry>();

  /** Apply the snapshot's buff list against the supplied action ordering.
   *
   * `orderedActionIds` is the placed actions sorted by physical position
   * (top-to-bottom, left-to-right). Returns the action ids whose displayed
   * buff changed (added, updated, or evicted) so the caller can redraw.
   */
  applyBuffs(orderedActionIds: readonly string[], buffs: readonly Buff[]): Set<string> {
    const changed = new Set<string>();

    for (const buff of buffs) {
      const existingId = this.findByType(buff.type);
      if (existingId !== null) {
        const prev = this.slots.get(existingId)!;
        if (!buffsEqual(prev.buff, buff)) {
          this.slots.set(existingId, { buff });
          changed.add(existingId);
        }
        continue;
      }
      const freeId = orderedActionIds.find((id) => !this.slots.has(id));
      if (freeId !== undefined) {
        this.slots.set(freeId, { buff });
        changed.add(freeId);
        continue;
      }
      const evictId = this.oldestSlot();
      if (evictId !== null) {
        this.slots.set(evictId, { buff });
        changed.add(evictId);
      }
    }

    return changed;
  }

  /** Reset all slots (e.g. on disconnect or game start). */
  reset(): Set<string> {
    const cleared = new Set(this.slots.keys());
    this.slots.clear();
    return cleared;
  }

  /** Drop a slot when its underlying action goes away (key unplaced). */
  removeAction(actionId: string): void {
    this.slots.delete(actionId);
  }

  get(actionId: string): SlotEntry | undefined {
    return this.slots.get(actionId);
  }

  private findByType(type: string): string | null {
    for (const [id, entry] of this.slots) {
      if (entry.buff.type === type) return id;
    }
    return null;
  }

  private oldestSlot(): string | null {
    let oldestId: string | null = null;
    let oldestTime = Infinity;
    for (const [id, entry] of this.slots) {
      if (entry.buff.last_changed < oldestTime) {
        oldestTime = entry.buff.last_changed;
        oldestId = id;
      }
    }
    return oldestId;
  }
}

function buffsEqual(a: Buff, b: Buff): boolean {
  return (
    a.type === b.type &&
    a.label === b.label &&
    a.attack === b.attack &&
    a.health === b.health &&
    a.value === b.value &&
    a.current === b.current &&
    a.target === b.target
  );
}
