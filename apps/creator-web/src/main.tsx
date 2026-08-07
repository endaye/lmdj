import {StrictMode} from "react";
import {createRoot} from "react-dom/client";

import {App} from "./app";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) throw new Error("Creator root is missing");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
