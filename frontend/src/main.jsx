import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./mobile.css";
import App from "./App";
// Il tema va caricato dopo le pagine, così il nuovo aspetto vale ovunque.
import "./theme.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
