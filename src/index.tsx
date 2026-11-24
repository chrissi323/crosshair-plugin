import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin } from "@decky/api";
import { useState, useEffect } from "react";
import { FaCrosshairs } from "react-icons/fa";

type Style = "box" | "dot";
// [width, height, source ("gamescope" | "manual" | "fallback"), mangoapp restarted]
type PlaceResult = [number, number, string, boolean];

interface PluginState {
  style: Style;
  nudge_x: number;
  nudge_y: number;
  nudge_step: number;
  resolution_mode: string; // "auto" or "WIDTHxHEIGHT"
  active: boolean;
  offset_x: number | null;
  offset_y: number | null;
  last_placement: [number, number, string] | null; // [width, height, source]
}

const getState = callable<[], PluginState>("get_state");
const makeCrosshair = callable<[Style, number, number], PlaceResult>("make_crosshair");
const recenterCrosshair = callable<[number, number], PlaceResult>("recenter_crosshair");
const setResolutionMode = callable<[string, number, number], PlaceResult | null>(
  "set_resolution_mode"
);
const setNudgeStep = callable<[number], void>("set_nudge_step");
const adjustCrosshairOffset = callable<[number, number], void>("adjust_crosshair_offset");
const removeCrosshair = callable<[], void>("remove_crosshair");

const RESOLUTION_OPTIONS = [
  { data: "auto", label: "Auto-detect" },
  { data: "1280x800", label: "1280 x 800 (Steam Deck)" },
  { data: "1920x1080", label: "1920 x 1080" },
  { data: "1920x1200", label: "1920 x 1200" },
  { data: "2560x1440", label: "2560 x 1440" },
  { data: "2560x1600", label: "2560 x 1600" },
  { data: "3840x2160", label: "3840 x 2160 (4K)" },
];
const STEP_OPTIONS = [1, 5, 10, 50].map((n) => ({ data: n, label: `${n} px` }));

// Steam's dropdown keeps its own selection and doesn't reliably follow
// `selectedOption`, so the shown value is rendered from our state instead.
const optionLabel = (options: { data: unknown; label: string }[], value: unknown) =>
  options.find((option) => option.data === value)?.label ?? String(value);

// Screen size as seen by the Steam client; only used by the backend if
// gamescope can't be queried.
const fallbackSize = (): [number, number] => {
  const dpr = window.devicePixelRatio || 1;
  return [Math.round(window.screen.width * dpr), Math.round(window.screen.height * dpr)];
};

const describe = (action: string, [width, height, source, restarted]: PlaceResult) =>
  `${action} for ${width}x${height} (${source})` + (restarted ? ", overlay restarted!" : "!");

// Text under the resolution dropdown explaining what the current choice does
const resolutionHint = (state: PluginState | null) => {
  if (!state) return undefined;
  const placed = state.active ? state.last_placement : null;
  if (state.resolution_mode === "auto") {
    return placed
      ? `Crosshair centered for ${placed[0]}x${placed[1]} (${placed[2]})`
      : "Uses the resolution reported by gamescope";
  }
  return placed
    ? `Crosshair centered for ${placed[0]}x${placed[1]} (manual)`
    : `Fixed: next crosshair is centered for ${state.resolution_mode}`;
};

// Delay before acting on a dropdown choice, so the dropdown menu can close
// before the panel re-renders (otherwise it can pop open again).
const DROPDOWN_ACTION_DELAY_MS = 300;

const styleLabel = (style: Style) => (style === "box" ? "Box" : "Dot");

// Kept outside the component: the QAM unmounts the plugin panel when it is
// closed, which would otherwise reset the status to its initial value.
let lastStatus = "No action yet";

function Content() {
  const [status, setStatusState] = useState(lastStatus);
  const [state, setState] = useState<PluginState | null>(null);
  const setStatus = (text: string) => {
    lastStatus = text;
    setStatusState(text);
  };

  const refresh = async () => {
    try {
      setState(await getState());
    } catch (error) {
      console.error(error);
    }
  };

  // Runs a backend action, shows the returned status text and reloads the state
  const run = async (action: () => Promise<string>, failure: string) => {
    try {
      setStatus(await action());
    } catch (error) {
      console.error(error);
      setStatus(failure);
    }
    await refresh();
  };

  useEffect(() => {
    refresh();
  }, []);

  const step = state?.nudge_step ?? 5;
  const nudge = (dx: number, dy: number) =>
    run(async () => {
      await adjustCrosshairOffset(dx, dy);
      return state?.active ? `Moved by x=${dx}, y=${dy}` : `Correction saved (x=${dx}, y=${dy})`;
    }, "Failed to move crosshair.");

  return (
    <PanelSection title="Crosshair Plugin">
      <PanelSectionRow>
        <div>
          NOTE: This plugin works by replacing the performance overlay with text that acts as a crosshair in your game. Currently you can not have both a performance overlay and crosshairs at the same time. To restore performance overlay, simply toggle one of the 4 levels from the QAM tab.
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="Screen resolution"
          description={resolutionHint(state)}
          rgOptions={RESOLUTION_OPTIONS}
          selectedOption={state?.resolution_mode ?? "auto"}
          renderButtonValue={() => optionLabel(RESOLUTION_OPTIONS, state?.resolution_mode ?? "auto")}
          onChange={(option) => {
            if (option.data === state?.resolution_mode) return;
            // Show the new choice right away, act on it once the menu has closed
            setState((prev) => (prev ? { ...prev, resolution_mode: option.data } : prev));
            setTimeout(
              () =>
                run(async () => {
                  const result = await setResolutionMode(option.data, ...fallbackSize());
                  return result
                    ? describe("Crosshair re-placed", result)
                    : `Screen resolution set to ${option.data}`;
                }, "Failed to set screen resolution."),
              DROPDOWN_ACTION_DELAY_MS
            );
          }}
        />
      </PanelSectionRow>
      {(["box", "dot"] as Style[]).map((style) => (
        <PanelSectionRow key={style}>
          <ButtonItem
            layout="below"
            onClick={() =>
              run(
                async () =>
                  describe(
                    `Crosshair ${styleLabel(style)} applied`,
                    await makeCrosshair(style, ...fallbackSize())
                  ),
                `Failed to apply ${style} crosshair.`
              )
            }
          >
            Make Crosshair {styleLabel(style)}
          </ButtonItem>
        </PanelSectionRow>
      ))}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() =>
            run(
              async () => describe("Crosshair re-centered", await recenterCrosshair(...fallbackSize())),
              "Failed to re-center crosshair."
            )
          }
        >
          Re-center
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() =>
            run(async () => {
              await removeCrosshair();
              return "Crosshair removed!";
            }, "Failed to remove crosshair.")
          }
        >
          Remove Crosshair
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Status" childrenLayout="below">
          {status}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Offset X">{state?.offset_x ?? "-"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Offset Y">{state?.offset_y ?? "-"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <Field label="Correction">{state ? `${state.nudge_x}, ${state.nudge_y}` : "-"}</Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="Nudge step"
          rgOptions={STEP_OPTIONS}
          selectedOption={step}
          renderButtonValue={() => optionLabel(STEP_OPTIONS, step)}
          onChange={(option) => {
            if (option.data === step) return;
            setState((prev) => (prev ? { ...prev, nudge_step: option.data } : prev));
            setTimeout(
              () =>
                run(async () => {
                  await setNudgeStep(option.data);
                  return `Nudge step set to ${option.data} px`;
                }, "Failed to set nudge step."),
              DROPDOWN_ACTION_DELAY_MS
            );
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => nudge(0, -step)}>
          Up
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => nudge(-step, 0)}>
          Left
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => nudge(step, 0)}>
          Right
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => nudge(0, step)}>
          Down
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: "Crosshair Plugin",
  titleView: <div className={staticClasses.Title}>Crosshair Plugin</div>,
  content: <Content />,
  icon: <FaCrosshairs />,
}));
