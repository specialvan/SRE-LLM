(() => {
  const ready = (fn) => {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  };

  ready(() => {
    document.documentElement.classList.add("kb-modern");
    document.body.classList.add("kb-modernized");

    ensureMainId();
    injectSkipLink();
    injectProgressBar();
    injectCommandBar();
    enhanceReveal();
    enhanceBackTop();
    bindScrollProgress();
  });

  function ensureMainId() {
    const main = document.querySelector("main") || document.body;
    if (!main.id) main.id = "main";
  }

  function injectSkipLink() {
    if (document.querySelector(".kb-skip-link, .skip-link")) return;
    const main = document.querySelector("main") || document.body;
    const link = document.createElement("a");
    link.className = "kb-skip-link";
    link.href = `#${main.id}`;
    link.textContent = "跳到主内容";
    document.body.prepend(link);
  }

  function injectProgressBar() {
    if (document.querySelector(".kb-progress")) return;
    const bar = document.createElement("div");
    bar.className = "kb-progress";
    bar.setAttribute("aria-hidden", "true");
    document.body.prepend(bar);
  }

  function injectCommandBar() {
    const main = document.querySelector("main");
    if (!main || document.querySelector(".kb-command")) return;
    const bar = document.createElement("div");
    bar.className = "kb-command";
    bar.innerHTML = `
      <label class="kb-search-label">
        <span class="sr-only">搜索章节</span>
        <input type="search" placeholder="搜索章节 / finding / artifact / lease..." aria-label="搜索知识库章节">
      </label>
      <span class="kb-command__hint">⌘ / Ctrl + F 也可使用浏览器搜索</span>`;
    main.prepend(bar);
    const input = bar.querySelector("input");
    input.addEventListener("input", () => filterSections(input.value));
  }

  function filterSections(query) {
    const normalized = query.trim().toLowerCase();
    document.querySelectorAll("section").forEach((section) => {
      if (!normalized) {
        section.classList.remove("kb-hidden");
        return;
      }
      section.classList.toggle("kb-hidden", !section.textContent.toLowerCase().includes(normalized));
    });
  }

  function enhanceReveal() {
    const targets = Array.from(document.querySelectorAll("section, .card, .callout, .metrics-row, .gif-block, .trio figure"));
    targets.forEach((target) => target.classList.add("kb-reveal", "kb-in-view", "in-view"));
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    targets.forEach((target) => target.classList.remove("kb-in-view", "in-view"));
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("kb-in-view", "in-view");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -8% 0px" });
    targets.forEach((target) => observer.observe(target));
  }

  function enhanceBackTop() {
    const button = document.createElement("button");
    button.className = "kb-back-top";
    button.type = "button";
    button.textContent = "↑";
    button.setAttribute("aria-label", "回到顶部");
    button.addEventListener("click", () => {
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      window.scrollTo({ top: 0, behavior });
    });
    document.body.appendChild(button);
    window.addEventListener("scroll", () => {
      button.classList.toggle("is-visible", window.scrollY > 500);
    }, { passive: true });
  }

  function bindScrollProgress() {
    const bar = document.querySelector(".kb-progress");
    if (!bar) return;
    const update = () => {
      const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      bar.style.transform = `scaleX(${Math.min(1, window.scrollY / max)})`;
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
  }
})();
