/* Confirmation dialogs for destructive / bulk actions (Phase 15).
   Forms declare  data-confirm="Question?"  instead of an inline onsubmit
   handler, so the page can use a Content-Security-Policy that blocks inline
   event handlers. Runs in the capture phase so a cancelled confirmation stops
   every other submit handler (for example the "Recording..." loading state). */
document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute && event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
    }
}, true);
