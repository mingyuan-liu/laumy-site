(() => {
  const key = "laumy-theme";
  const apply = value => document.documentElement.dataset.theme = value || "light";
  apply(localStorage.getItem(key));
  document.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(key, next);
    apply(next);
  });
})();
