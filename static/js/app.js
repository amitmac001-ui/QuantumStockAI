(() => {
    "use strict";

    const drawer = document.getElementById("app-drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    const toggle = document.getElementById("menu-toggle");
    const close = document.getElementById("menu-close");
    if (!drawer || !backdrop || !toggle) return;

    const setOpen = (open) => {
        drawer.classList.toggle("is-open", open);
        drawer.setAttribute("aria-hidden", String(!open));
        toggle.setAttribute("aria-expanded", String(open));
        backdrop.hidden = !open;
        document.body.style.overflow = open ? "hidden" : "";
    };

    toggle.addEventListener("click", () => setOpen(true));
    close?.addEventListener("click", () => setOpen(false));
    backdrop.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
    });
})();
