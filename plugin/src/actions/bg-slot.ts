import {
  action,
  SingletonAction,
  type WillAppearEvent,
  type WillDisappearEvent,
} from "@elgato/streamdeck";

import { grid } from "../grid";

@action({ UUID: "com.bgstreamboy.companion.slot" })
export class BgSlotAction extends SingletonAction {
  override onWillAppear(ev: WillAppearEvent): void {
    if (!ev.action.isKey()) return;
    const coords = ev.action.coordinates;
    if (!coords) return;
    grid.registerAction(ev.action, coords.column, coords.row);
  }

  override onWillDisappear(ev: WillDisappearEvent): void {
    grid.unregisterActionById(ev.action.id);
  }
}
