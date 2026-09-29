/* ============================================================
   VOCA - Theme (Light / Dark)
   File: theme.js   (shared by every page)

   Stores the choice in localStorage (persists across app restarts
   on this machine, same as any other remembered app setting) and
   applies it via a data-theme attribute on <html>, which theme.css
   reads.
   ============================================================ */

(function () {
  const KEY = "voca_theme";

  window.VOCA_getTheme = function () {
    return localStorage.getItem(KEY) || "light";
  };

  window.VOCA_setTheme = function (name) {
    name = (name === "dark") ? "dark" : "light";
    localStorage.setItem(KEY, name);
    document.documentElement.setAttribute("data-theme", name);
    document.dispatchEvent(new CustomEvent("voca-theme-changed", { detail: name }));
  };

  // Apply immediately (this file is loaded early in <head> on every
  // page specifically so this runs before the page is visible).
  document.documentElement.setAttribute("data-theme", window.VOCA_getTheme());
})();
