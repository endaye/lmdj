import { createRoot } from "react-dom/client";
import { App } from "./ui/App";
import { getAudio } from "./ui/useEngine";
import "./ui/theme.css";

const root = createRoot(document.getElementById("root")!);
void getAudio().then(({ engine, decode }) => {
  root.render(<App engine={engine} decode={decode} />);
});
