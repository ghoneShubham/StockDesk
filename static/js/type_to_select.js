/**
 * Type-to-filter native <select> lists.
 * Typing accumulates the full string (e.g. "bott" -> Bottle) and hides
 * options whose label does not contain it. Uses capture so the browser's
 * single-letter jump does not steal keys while the list is open.
 */
(function (global) {
  function enableTypeToSelect(select) {
    if (!select || select.dataset.typeSelectBound === "1") return;
    select.dataset.typeSelectBound = "1";

    let buffer = "";
    let clearTimer = null;
    let hint = select.parentElement && select.parentElement.querySelector(".sd-type-hint");
    if (!hint) {
      hint = document.createElement("div");
      hint.className = "form-text sd-type-hint";
      hint.hidden = true;
      select.insertAdjacentElement("afterend", hint);
    }

    function resetOptions() {
      Array.from(select.options).forEach(function (opt) {
        opt.hidden = false;
        opt.disabled = false;
      });
    }

    function applyBuffer() {
      const q = buffer.trim().toLowerCase();
      const options = Array.from(select.options);
      let firstMatch = null;

      options.forEach(function (opt) {
        if (!opt.value) {
          opt.hidden = false;
          opt.disabled = false;
          return;
        }
        const text = opt.text.toLowerCase();
        const ok = !q || text.includes(q);
        opt.hidden = !ok;
        opt.disabled = !ok;
        if (ok && !firstMatch) firstMatch = opt;
      });

      if (q && firstMatch) {
        if (select.value !== firstMatch.value) {
          select.value = firstMatch.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
        }
        hint.textContent = 'Filter: "' + buffer + '"';
        hint.hidden = false;
      } else if (q) {
        hint.textContent = 'No match for "' + buffer + '"';
        hint.hidden = false;
      } else {
        resetOptions();
        hint.hidden = true;
        hint.textContent = "";
      }
    }

    function clearBufferSoon() {
      clearTimeout(clearTimer);
      clearTimer = setTimeout(function () {
        buffer = "";
        resetOptions();
        hint.hidden = true;
        hint.textContent = "";
      }, 2500);
    }

    function onDocKey(e) {
      if (document.activeElement !== select) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === "Tab") {
        return;
      }
      if (e.key === "Escape") {
        buffer = "";
        applyBuffer();
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (e.key === "Backspace") {
        e.preventDefault();
        e.stopPropagation();
        buffer = buffer.slice(0, -1);
        applyBuffer();
        clearBufferSoon();
        return;
      }
      if (e.key.length !== 1) return;

      e.preventDefault();
      e.stopPropagation();
      buffer += e.key.toLowerCase();
      applyBuffer();
      clearBufferSoon();
    }

    select.addEventListener("focus", function () {
      document.addEventListener("keydown", onDocKey, true);
    });
    select.addEventListener("blur", function () {
      document.removeEventListener("keydown", onDocKey, true);
      buffer = "";
      resetOptions();
      hint.hidden = true;
      hint.textContent = "";
      clearTimeout(clearTimer);
    });
  }

  function bindMarkedSelects() {
    document.querySelectorAll("select[data-type-select]").forEach(enableTypeToSelect);
  }

  global.enableTypeToSelect = enableTypeToSelect;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindMarkedSelects);
  } else {
    bindMarkedSelects();
  }
})(window);
