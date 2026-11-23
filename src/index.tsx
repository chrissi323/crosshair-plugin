import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin } from "@decky/api";
import { useState, useEffect } from "react";
import { FaCrosshairs } from "react-icons/fa";

const adjustCrosshairOffset = callable<[number, number], void>("adjust_crosshair_offset");
const getCurrentOffsets = callable<[], number[]>("get_current_offsets");
const removeCrosshair = callable<[], void>("remove_crosshair");
const makeAutoCrosshair = callable<[string, number, number], [number, number, string]>(
  "make_auto_crosshair"
);

function Content() {
  const [status, setStatus] = useState("No action yet");
  const [xOffset, setXOffset] = useState(0);
  const [yOffset, setYOffset] = useState(0);

  const fetchOffsets = async () => {
    try {
      const [x, y] = await getCurrentOffsets();
      setXOffset(x);
      setYOffset(y);
    } catch (error) {
      console.error(error);
    }
  };

  const onAutoClick = async (style: "box" | "dot") => {
    const label = style === "box" ? "Box" : "Dot";
    try {
      // Only used by the backend if gamescope can't be queried
      const dpr = window.devicePixelRatio || 1;
      const fallbackWidth = Math.round(window.screen.width * dpr);
      const fallbackHeight = Math.round(window.screen.height * dpr);
      const [width, height, source] = await makeAutoCrosshair(style, fallbackWidth, fallbackHeight);
      setStatus(`Crosshair ${label} applied for ${width}x${height} (${source})!`);
      await fetchOffsets();
    } catch (error) {
      console.error(error);
      setStatus(`Failed to apply ${style} crosshair.`);
    }
  };

  const onRemoveClick = async () => {
    try {
      await removeCrosshair();
      setStatus("Crosshair removed!");
      setXOffset(0);
      setYOffset(0);
    } catch (error) {
      console.error(error);
      setStatus("Failed to remove crosshair.");
    }
  };

  const onOffsetClick = async (xDelta: number, yDelta: number) => {
    try {
      await adjustCrosshairOffset(xDelta, yDelta);
      setStatus(`Crosshair offset adjusted by x=${xDelta}, y=${yDelta}`);
      await fetchOffsets();
    } catch (error) {
      console.error(error);
      setStatus("Failed to adjust crosshair offset.");
    }
  };

  useEffect(() => {
    fetchOffsets();
  }, []);

  return (
    <PanelSection title="Crosshair Plugin">
      <PanelSectionRow>
        <div>
          NOTE: This plugin works by replacing the performance overlay with text that acts as a crosshair in your game. Currently you can not have both a performance overlay and crosshairs at the same time. To restore performance overlay, simply toggle one of the 4 levels from the QAM tab. 
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => onAutoClick("box")}>
          Make Crosshair Box
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => onAutoClick("dot")}>
          Make Crosshair Dot
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onRemoveClick}>
          Remove Crosshair
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => onOffsetClick(0, -1)}>
          Up
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => onOffsetClick(-1, 0)}>
          Left
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => onOffsetClick(1, 0)}>
          Right
        </ButtonItem>
        <ButtonItem layout="below" onClick={() => onOffsetClick(0, 1)}>
          Down
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div>Status: {status}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div>
          Current Offsets: X = {xOffset}, Y = {yOffset}
        </div>
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