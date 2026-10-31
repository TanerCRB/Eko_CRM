import "./styles/tokens.css";
import "./styles/tokens-shell.css";
import "./styles/components.css";
import "./styles/shell.css";
import { mount } from "./mount";

window.addEventListener("vite:preloadError", (event) => {
  if (window.location.search === "?recovery=1") {
    return;
  }
  event.preventDefault();
  window.location.assign("/klienci?recovery=1");
});

mount(document);
