import streamDeck from "@elgato/streamdeck";

import { BgSlotAction } from "./actions/bg-slot";
import { grid } from "./grid";

streamDeck.logger.setLevel("info");

streamDeck.actions.registerAction(new BgSlotAction());

streamDeck.connect().then(() => {
  grid.start();
});
