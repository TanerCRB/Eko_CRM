import "./styles/tokens.css";
import "./styles/tokens-shell.css";
import "./styles/components.css";
import "./styles/shell.css";
import { mount } from "./mount";

window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  window.location.assign("/klienci");
});

mount(document);
