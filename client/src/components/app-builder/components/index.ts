/**
 * App Builder Basic Components
 *
 * Export all basic components and registration function.
 */

export { HeadingComponent } from "./HeadingComponent";
export { TextComponent } from "./TextComponent";
export { CardComponent } from "./CardComponent";
export { DividerComponent } from "./DividerComponent";
export { SpacerComponent } from "./SpacerComponent";
export { ButtonComponent } from "./ButtonComponent";

import { registerComponent } from "../ComponentRegistry";
import { HeadingComponent } from "./HeadingComponent";
import { TextComponent } from "./TextComponent";
import { CardComponent } from "./CardComponent";
import { DividerComponent } from "./DividerComponent";
import { SpacerComponent } from "./SpacerComponent";
import { ButtonComponent } from "./ButtonComponent";

/**
 * Register all basic components with the ComponentRegistry.
 * Call this function once during app initialization.
 */
export function registerBasicComponents(): void {
	registerComponent("heading", HeadingComponent);
	registerComponent("text", TextComponent);
	registerComponent("card", CardComponent);
	registerComponent("divider", DividerComponent);
	registerComponent("spacer", SpacerComponent);
	registerComponent("button", ButtonComponent);
}
