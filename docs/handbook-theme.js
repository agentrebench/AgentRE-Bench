(function () {
  function initializePageIndex() {
    const main = document.querySelector("main");
    if (!main || main.querySelector(".page-index")) return;

    const sections = Array.from(main.children).filter((node) => node.matches("section[id]"));
    if (sections.length < 2) return;

    const index = document.createElement("details");
    index.className = "page-index";
    const summary = document.createElement("summary");
    summary.textContent = "On this page";
    const navigation = document.createElement("nav");
    navigation.setAttribute("aria-label", "On this page");
    const list = document.createElement("ol");
    list.className = "page-index-list";

    sections.forEach((section) => {
      const label = section.querySelector(".section-tag") || section.querySelector("h2");
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = "#" + section.id;
      link.textContent = label?.textContent.trim() || section.id.replace(/-/g, " ");
      item.appendChild(link);
      list.appendChild(item);
    });

    navigation.appendChild(list);
    index.append(summary, navigation);
    main.insertBefore(index, sections[0]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePageIndex);
  } else {
    initializePageIndex();
  }
})();
