(function () {
  function sectionLabel(section) {
    const tag = section.querySelector(".section-tag");
    if (tag && tag.textContent.trim()) return tag.textContent.trim();

    const heading = section.querySelector("h2");
    if (heading && heading.textContent.trim()) return heading.textContent.trim();

    return section.id.replace(/-/g, " ");
  }

  function initializeHandbookLayout() {
    const host = document.querySelector("main") || document.body;
    if (host.querySelector(":scope > .handbook-layout")) return;

    const sections = Array.from(host.children).filter((node) => {
      return node.matches && node.matches("section[id]");
    });
    if (!sections.length) return;

    const layout = document.createElement("div");
    layout.className = "handbook-layout";

    const index = document.createElement("nav");
    index.className = "handbook-index";
    index.setAttribute("aria-label", "On this page");

    const indexTitle = document.createElement("div");
    indexTitle.className = "handbook-index-title";
    indexTitle.textContent = "In this guide";

    const list = document.createElement("ol");
    list.className = "handbook-index-list";

    const content = document.createElement("div");
    content.className = "handbook-content";

    host.insertBefore(layout, sections[0]);

    sections.forEach((section, position) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = "#" + section.id;
      link.dataset.index = String(position + 1).padStart(2, "0");
      link.textContent = sectionLabel(section);
      if (position === 0) link.setAttribute("aria-current", "location");
      item.appendChild(link);
      list.appendChild(item);
      content.appendChild(section);
    });

    index.appendChild(indexTitle);
    index.appendChild(list);
    layout.appendChild(index);
    layout.appendChild(content);
    host.classList.add("handbook-page");

    if (!("IntersectionObserver" in window)) return;

    const links = Array.from(list.querySelectorAll("a"));
    const byId = new Map(links.map((link) => [link.hash.slice(1), link]));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top);
      if (!visible.length) return;

      links.forEach((link) => link.removeAttribute("aria-current"));
      const active = byId.get(visible[0].target.id);
      if (active) active.setAttribute("aria-current", "location");
    }, {
      rootMargin: "-18% 0px -68% 0px",
      threshold: 0
    });

    sections.forEach((section) => observer.observe(section));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeHandbookLayout);
  } else {
    initializeHandbookLayout();
  }
})();
