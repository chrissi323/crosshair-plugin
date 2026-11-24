import {
  ButtonItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin } from "@decky/api";
import { useState, useEffect, useRef } from "react";
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

interface Option<T> {
  data: T;
  label: string; // shown in the slider title
  short: string; // shown under the slider notch
}

const RESOLUTION_OPTIONS: Option<string>[] = [
  { data: "auto", label: "Auto-detect", short: "Auto" },
  { data: "1280x800", label: "1280 x 800 (Steam Deck)", short: "800p" },
  { data: "1920x1080", label: "1920 x 1080", short: "1080p" },
  { data: "1920x1200", label: "1920 x 1200", short: "1200p" },
  { data: "2560x1440", label: "2560 x 1440", short: "1440p" },
  { data: "2560x1600", label: "2560 x 1600", short: "1600p" },
  { data: "3840x2160", label: "3840 x 2160 (4K)", short: "4K" },
];
const STEP_OPTIONS: Option<number>[] = [1, 5, 10, 50].map((n) => ({
  data: n,
  label: `${n} px`,
  short: `${n}`,
}));

// Wait this long after the last slider move before calling the backend, so
// scrolling through the options doesn't re-place the crosshair for each one.
const CHOICE_DEBOUNCE_MS = 400;

const optionLabel = <T,>(options: Option<T>[], value: T) =>
  options.find((option) => option.data === value)?.label ?? String(value);

// A notched slider for picking one of a few options; on the Deck it is changed
// with left/right on the D-pad, like the QAM's performance overlay level.
// Popups (Steam's DropdownItem, showContextMenu) are avoided on purpose: after a
// choice in a popup the QAM panel didn't re-render until the next input in it.
function ChoiceSlider<T>(props: {
  label: string;
  description?: string;
  options: Option<T>[];
  value: T;
  onChange(value: T): void;
}) {
  const { label, description, options, value, onChange } = props;
  const index = Math.max(0, options.findIndex((option) => option.data === value));
  return (
    <SliderField
      label={`${label}: ${optionLabel(options, value)}`}
      description={description}
      value={index}
      min={0}
      max={options.length - 1}
      step={1}
      notchCount={options.length}
      notchLabels={options.map((option, i) => ({ notchIndex: i, label: option.short, value: i }))}
      notchTicksVisible={true}
      showValue={false}
      validValues="steps"
      onChange={(i) => {
        const option = options[i];
        if (option && option.data !== value) onChange(option.data);
      }}
    />
  );
}

// Screen size as seen by the Steam client; only used by the backend if
// gamescope can't be queried.
const fallbackSize = (): [number, number] => {
  const dpr = window.devicePixelRatio || 1;
  return [Math.round(window.screen.width * dpr), Math.round(window.screen.height * dpr)];
};

const describe = (action: string, [width, height, source, restarted]: PlaceResult) =>
  `${action} for ${width}x${height} (${source})` + (restarted ? ", overlay restarted!" : "!");

// Text under the resolution slider explaining what the current choice does
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

  // Runs `action` once no new call for the same key came in for CHOICE_DEBOUNCE_MS
  const timers = useRef<Record<string, number>>({});
  const debounced = (key: string, action: () => void) => {
    window.clearTimeout(timers.current[key]);
    timers.current[key] = window.setTimeout(action, CHOICE_DEBOUNCE_MS);
  };

  const step = state?.nudge_step ?? 5;
  const nudge = (dx: number, dy: number) =>
    run(async () => {
      await adjustCrosshairOffset(dx, dy);
      return state?.active ? `Moved by x=${dx}, y=${dy}` : `Correction saved (x=${dx}, y=${dy})`;
    }, "Failed to move crosshair.");

  return (
    <PanelSection title="Crosshair Plugin">
      <PanelSectionRow>
        <div style={{ fontSize: "12px", lineHeight: "1.3", opacity: 0.8 }}>
          NOTE: This plugin works by replacing the performance overlay with text that acts as a crosshair in your game. Currently you can not have both a performance overlay and crosshairs at the same time. To restore performance overlay, simply toggle one of the 4 levels from the QAM tab.
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ChoiceSlider
          label="Screen resolution"
          description={resolutionHint(state)}
          options={RESOLUTION_OPTIONS}
          value={state?.resolution_mode ?? "auto"}
          onChange={(mode) => {
            setState((prev) => (prev ? { ...prev, resolution_mode: mode } : prev));
            debounced("resolution", () =>
              run(async () => {
                const result = await setResolutionMode(mode, ...fallbackSize());
                return result
                  ? describe("Crosshair re-placed", result)
                  : `Screen resolution set to ${mode}`;
              }, "Failed to set screen resolution.")
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
        <ChoiceSlider
          label="Nudge step"
          options={STEP_OPTIONS}
          value={step}
          onChange={(newStep) => {
            setState((prev) => (prev ? { ...prev, nudge_step: newStep } : prev));
            debounced("step", () =>
              run(async () => {
                await setNudgeStep(newStep);
                return `Nudge step set to ${newStep} px`;
              }, "Failed to set nudge step.")
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
