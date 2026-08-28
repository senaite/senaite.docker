/* maitux.worksheet - AS-Grouped worksheet layout: save queue.
 *
 * Replicates what senaite.app.listing's ReactJS controller does for editable
 * cells, because this layout renders plain server-side HTML instead:
 *
 *   1. an edited cell goes into a pending queue and reveals the Save button
 *      (listing.coffee: saveEditableField / show_ajax_save)
 *   2. Save posts the queue to the native `set_fields` endpoint, one UID per
 *      request, sequentially, in the order the rows are displayed
 *      (listing.coffee: ajax_save)
 *   3. the returned folderitems -- which include the analyses recalculated as
 *      dependents -- are applied back onto the read-only cells
 *   4. any workflow transition flushes the queue first
 *      (listing.coffee: ajax_do_transition_for, "always save pending items")
 *
 * Sending the queue as one batch, or concurrently, would be wrong: interim
 * fields feed calculations across analyses, and the server recalculates
 * dependents on every single set_fields call.  Order is part of the contract.
 */
(function () {
  "use strict";

  var root = document.querySelector(".as-grouped-listing");
  if (!root) {
    return;
  }

  var saveUrl = root.getAttribute("data-save-url");
  var form = root.querySelector(".as-grouped-form");
  var saveButton = root.querySelector(".as-save-button");
  var status = root.querySelector(".as-save-status");

  // { uid: { keyword: value } } -- mirrors the server's `save_queue` payload
  var queue = {};
  var saving = false;

  /* --------------------------------------------------------------------- *
   * helpers
   * --------------------------------------------------------------------- */

  function getCsrfToken() {
    // plone.protect exposes the token on the #protect-script element; this is
    // where senaite.app.listing reads it from too (api.coffee: get_csrf_token).
    var el = document.querySelector("#protect-script");
    return el ? el.dataset.token : "";
  }

  function isPending() {
    return Object.keys(queue).length > 0;
  }

  function setStatus(message, isError) {
    if (!status) {
      return;
    }
    status.textContent = message || "";
    status.classList.toggle("as-error", !!isError);
  }

  function refreshSaveButton() {
    if (!saveButton) {
      return;
    }
    saveButton.hidden = !isPending();
  }

  function editableCells() {
    return root.querySelectorAll(".as-input[data-uid], .as-select[data-uid]");
  }

  /* Cells of one keyword on one analysis, ordered by their row index. A list
   * interim is spread over several rows, so its value is reassembled from all
   * of them. */
  function cellsFor(uid, keyword) {
    var selector =
      '[data-uid="' + uid + '"][data-keyword="' + keyword + '"]';
    var nodes = Array.prototype.slice.call(root.querySelectorAll(selector));
    nodes.sort(function (a, b) {
      return (
        parseInt(a.getAttribute("data-row-index") || "0", 10) -
        parseInt(b.getAttribute("data-row-index") || "0", 10)
      );
    });
    return nodes;
  }

  function isListField(node) {
    return node.hasAttribute("data-row-index");
  }

  /* Value to send for a field.
   *
   * Scalars go as a plain string.  List interims go as a real JS array -- the
   * same shape MultiValue.coffee submits: every element trimmed, empties
   * dropped.  Do not pre-stringify it; JSON.stringify of the whole payload
   * does that. */
  function valueFor(node) {
    var uid = node.getAttribute("data-uid");
    var keyword = node.getAttribute("data-keyword");

    if (!isListField(node)) {
      return node.value;
    }

    return cellsFor(uid, keyword)
      .map(function (cell) {
        return (cell.value || "").trim();
      })
      .filter(function (value) {
        return value !== "";
      });
  }

  /* A panel's "select all" reflects only that panel's rows: unticking one row
   * unticks it, re-ticking every row re-ticks it. */
  function syncSelectAll(rowCheckbox) {
    var panel = rowCheckbox.closest(".as-group-panel");
    var selectAll = panel && panel.querySelector(".as-select-all");
    if (!selectAll) {
      return;
    }
    var boxes = panel.querySelectorAll(".as-row-select");
    var checked = panel.querySelectorAll(".as-row-select:checked");
    selectAll.checked = boxes.length > 0 && boxes.length === checked.length;
  }

  /* Tick the row of an analysis, and refresh its panel's "select all".
   * Mirrors selectUID() in listing.coffee. */
  function selectUid(uid) {
    var checkbox = root.querySelector(
      '.as-row-select[data-uid="' + uid + '"]');
    if (!checkbox || checkbox.checked) {
      return;
    }
    checkbox.checked = true;
    syncSelectAll(checkbox);
    // Only when the row was not selected yet, exactly like
    // listing.coffee's updateEditableField (`if not @is_uid_selected uid`):
    // typing in an already-selected row must not cost a round trip.
    scheduleTransitionsRefresh();
  }

  function enqueue(node) {
    var uid = node.getAttribute("data-uid");
    var keyword = node.getAttribute("data-keyword");
    if (!uid || !keyword) {
      return;
    }
    queue[uid] = queue[uid] || {};
    queue[uid][keyword] = valueFor(node);

    // Editing a field selects its row, exactly like the native listing:
    // "Select the whole row if an editable field changed its value"
    // (listing.coffee, updateEditableField).  Rows start unselected, so
    // without this a transition right after an edit would act on nothing.
    selectUid(uid);

    node.classList.add("as-dirty");
    refreshSaveButton();
    setStatus("");
  }

  /* UIDs in display order: the server recalculates dependents on every call,
   * so a later analysis must be saved after the one it depends on. */
  function queuedUidsInDisplayOrder() {
    var seen = {};
    var ordered = [];
    Array.prototype.forEach.call(editableCells(), function (node) {
      var uid = node.getAttribute("data-uid");
      if (uid && queue[uid] && !seen[uid]) {
        seen[uid] = true;
        ordered.push(uid);
      }
    });
    return ordered;
  }

  function rowsOf(uid) {
    var nodes = root.querySelectorAll('[data-uid="' + uid + '"]');
    var rows = [];
    Array.prototype.forEach.call(nodes, function (node) {
      var row = node.closest("tr");
      if (row && rows.indexOf(row) === -1) {
        rows.push(row);
      }
    });
    return rows;
  }

  function markSaving(uid, on) {
    rowsOf(uid).forEach(function (row) {
      row.classList.toggle("as-row-saving", on);
    });
  }

  /* --------------------------------------------------------------------- *
   * applying the server response
   * --------------------------------------------------------------------- */

  /* maitux.calcenhance wraps interim values in a dict; scalars arrive bare.
   * Mirrors AnalysesGroupedView._get_item_field_value(). */
  function itemValue(item, keyword) {
    var raw = item[keyword];
    if (raw === null || raw === undefined) {
      return "";
    }
    if (typeof raw === "object" && !Array.isArray(raw)) {
      var value = raw.value;
      return value === null || value === undefined ? "" : value;
    }
    return raw;
  }

  /* Decode a list interim value coming back from the server.
   *
   * folderitems hands list/calculatedlist values over as a JSON *string*
   * ('["1", "2"]'), not as an array, so the refresh has to parse it before
   * spreading it over the rows.  Writing the string straight into the inputs
   * puts the raw JSON text in front of the analyst, and the next save then
   * collects that text back as a single element -- each round trip nesting the
   * value one level deeper.  Mirrors _to_array() in views.py. */
  var MAX_UNWRAP_DEPTH = 8;

  function decodeList(value, depth) {
    depth = depth || 0;
    if (Array.isArray(value)) {
      return depth >= MAX_UNWRAP_DEPTH ? value : flattenEncoded(value, depth);
    }
    if (value === null || value === undefined || value === "") {
      return [];
    }
    if (typeof value !== "string" || depth >= MAX_UNWRAP_DEPTH) {
      return [value];
    }
    var text = value.trim();
    var parsed;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      return [value]; // a plain typed value such as "24.351"
    }
    if (typeof parsed === "string") {
      return decodeList(parsed, depth + 1); // '"[]"' decodes to the string "[]"
    }
    if (!Array.isArray(parsed)) {
      return [parsed];
    }
    return flattenEncoded(parsed, depth);
  }

  /* Replace elements that are themselves encoded lists by their contents, so
   * values already mangled by the bug above are recovered on refresh.  Only
   * bracket-shaped text is decoded: a solvent named "[control]" must survive. */
  function flattenEncoded(items, depth) {
    if (depth >= MAX_UNWRAP_DEPTH) {
      return items;
    }
    var out = [];
    items.forEach(function (element) {
      if (typeof element === "string") {
        var text = element.trim();
        if (text.charAt(0) === "[" && text.charAt(text.length - 1) === "]") {
          try {
            var sub = JSON.parse(text);
            if (Array.isArray(sub)) {
              out = out.concat(flattenEncoded(sub, depth + 1));
              return;
            }
          } catch (e) {
            /* not encoded after all: fall through and keep the text */
          }
        }
      }
      out.push(element);
    });
    return out;
  }

  function applyToCell(node, value) {
    if (node.tagName === "INPUT" || node.tagName === "SELECT") {
      // Never clobber a field the user is typing in, and never revert a value
      // that is still queued for saving.
      if (node === document.activeElement) {
        return;
      }
      var uid = node.getAttribute("data-uid");
      var keyword = node.getAttribute("data-keyword");
      if (queue[uid] && queue[uid][keyword] !== undefined) {
        return;
      }
      node.value = value;
      return;
    }
    if (node.textContent === String(value)) {
      return;
    }
    node.textContent = value;
    node.classList.remove("as-refreshed");
    // restart the highlight animation
    void node.offsetWidth;
    node.classList.add("as-refreshed");
  }

  /* Incremental update -- the grouped tables are never re-rendered, so focus
   * and not-yet-sent input stay intact. */
  function applyFolderitems(folderitems) {
    (folderitems || []).forEach(function (item) {
      var uid = item.uid;
      if (!uid) {
        return;
      }
      var nodes = root.querySelectorAll('[data-uid="' + uid + '"][data-keyword]');
      var byKeyword = {};
      Array.prototype.forEach.call(nodes, function (node) {
        var keyword = node.getAttribute("data-keyword");
        (byKeyword[keyword] = byKeyword[keyword] || []).push(node);
      });

      Object.keys(byKeyword).forEach(function (keyword) {
        if (!(keyword in item)) {
          return;
        }
        var value = itemValue(item, keyword);
        var cells = cellsFor(uid, keyword);

        // A list interim occupies one cell per row; anything else has a single
        // cell (rowspanned).  Deciding by the cells rather than by the value
        // type matters: the server sends the list as a JSON string, so an
        // Array.isArray() test would silently take the scalar path.
        if (cells.length && isListField(cells[0])) {
          var values = decodeList(value);
          cells.forEach(function (cell, index) {
            applyToCell(cell, index < values.length ? values[index] : "");
          });
          return;
        }
        cells.forEach(function (cell) {
          applyToCell(cell, value);
        });
      });
    });
  }

  /* --------------------------------------------------------------------- *
   * saving
   * --------------------------------------------------------------------- */

  function postOne(uid, payload) {
    var saveQueue = {};
    saveQueue[uid] = payload;

    markSaving(uid, true);
    return fetch(saveUrl, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": getCsrfToken()
      },
      body: JSON.stringify({ save_queue: saveQueue })
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        // Drop the entry *before* applying the response: applyToCell skips
        // fields that are still queued, so leaving it in would prevent the
        // just-saved cells from picking up the server-normalised values.
        delete queue[uid];
        applyFolderitems(data.folderitems);
        rowsOf(uid).forEach(function (row) {
          Array.prototype.forEach.call(
            row.querySelectorAll(".as-dirty"),
            function (node) {
              node.classList.remove("as-dirty");
            }
          );
        });
        return data;
      })
      .then(
        function (data) {
          markSaving(uid, false);
          return data;
        },
        function (error) {
          markSaving(uid, false);
          throw error;
        }
      );
  }

  /* Resolves once everything queued has been persisted. Rejects on the first
   * failure, leaving the remaining edits queued so nothing is silently lost. */
  function flush() {
    if (saving) {
      return Promise.reject(new Error("A save is already running"));
    }
    if (!isPending()) {
      return Promise.resolve();
    }

    saving = true;
    setStatus("Saving…");

    var uids = queuedUidsInDisplayOrder();
    var chain = Promise.resolve();

    uids.forEach(function (uid) {
      chain = chain.then(function () {
        var payload = queue[uid];
        if (!payload) {
          return null; // already flushed
        }
        return postOne(uid, payload);
      });
    });

    return chain.then(
      function () {
        saving = false;
        refreshSaveButton();
        setStatus("Saved.");
        // A saved value can flip a guard: guard_submit refuses an analysis
        // whose interims are still empty, so Submit only becomes available
        // once they are persisted.  The native listing refetches transitions
        // at the very same point (listing.coffee, end of ajax_save).
        scheduleTransitionsRefresh();
        return true;
      },
      function (error) {
        saving = false;
        refreshSaveButton();
        setStatus("Save failed: " + error.message + " — changes kept.", true);
        throw error;
      }
    );
  }

  /* --------------------------------------------------------------------- *
   * wiring
   * --------------------------------------------------------------------- */

  /* ------------------------------------------------------------------- *
   * growing a list
   *
   * The native MultiValue widget always keeps one empty input at the end of a
   * list so the next element can be typed straight away.  Here list elements
   * are rows, so the equivalent is: as soon as the last row of a sample block
   * gets a value, append a fresh empty row.  Without this the list stops
   * growing after the single spare row the server rendered, and the analyst
   * has to save once per element.
   * ------------------------------------------------------------------- */

  /* Rows of the same sample block. Walks the siblings rather than building a
   * selector: the block id is built from a keyword and a sample id, so it can
   * contain characters that would need escaping. */
  function blockRows(row) {
    var rows = [];
    var block = row.getAttribute("data-block");
    var tbody = row.parentNode;
    if (!block || !tbody) {
      return rows;
    }
    Array.prototype.forEach.call(tbody.children, function (tr) {
      if (tr.getAttribute && tr.getAttribute("data-block") === block) {
        rows.push(tr);
      }
    });
    return rows;
  }

  function appendListRow(node) {
    var row = node.closest("tr");
    if (!row || !row.getAttribute("data-block")) {
      return;
    }
    var rows = blockRows(row);
    if (rows[rows.length - 1] !== row) {
      return; // not the last row: there is already somewhere to type
    }

    var fresh = row.cloneNode(true);

    // Keep the list cells only.  Sub-rows already contain nothing else, but a
    // block that is still one row long is its *first* row, which also carries
    // the rowspanned scalar cells (sample id, Result, Method, Instrument).
    // Cloning those would duplicate them and shift every later column right.
    Array.prototype.slice.call(fresh.children).forEach(function (cell) {
      if (!cell.querySelector("[data-row-index]")) {
        fresh.removeChild(cell);
      }
    });

    var index = null;
    Array.prototype.forEach.call(
      fresh.querySelectorAll("[data-row-index]"), function (cell) {
        index = parseInt(cell.getAttribute("data-row-index") || "0", 10) + 1;
        cell.setAttribute("data-row-index", String(index));
        cell.classList.remove("as-dirty", "as-refreshed");
        if (cell.tagName === "INPUT") {
          cell.value = "";
        } else {
          cell.textContent = "";
        }
      });
    if (index === null) {
      return; // no list cell to grow
    }

    // Every rowspanned cell of this block now covers one more row
    rows.forEach(function (r) {
      Array.prototype.forEach.call(
        r.querySelectorAll("[rowspan]"), function (cell) {
          cell.rowSpan = (parseInt(cell.getAttribute("rowspan"), 10) || 1) + 1;
        });
    });

    fresh.classList.remove("as-row-first");
    fresh.classList.add("as-row-sub");
    row.parentNode.insertBefore(fresh, row.nextSibling);
  }

  root.addEventListener("input", function (event) {
    var node = event.target;
    if (!node.hasAttribute || !node.hasAttribute("data-row-index")) {
      return;
    }
    if (node.tagName !== "INPUT" || !node.value.trim()) {
      return;
    }
    appendListRow(node);
  });

  /* Queue on `input`, not on `change`.
   *
   * The native listing binds React's onChange, which for a text input fires on
   * every keystroke -- NumericField.coffee calls update_editable_field() from
   * it, so the row gets selected and queued while typing.  The DOM `change`
   * event only fires on blur, which made the row tick one step late: the
   * analyst had to click elsewhere before the checkbox came on.
   *
   * A <select> fires `input` on selection too, so one listener covers both. */
  root.addEventListener("input", function (event) {
    var node = event.target;
    if (!node.hasAttribute || !node.hasAttribute("data-uid")) {
      return;
    }
    if (!node.classList.contains("as-input") &&
        !node.classList.contains("as-select")) {
      return;
    }
    enqueue(node);
  });

  /* ------------------------------------------------------------------- *
   * row selection
   *
   * Gates which analyses Submit/Unassign/Reject act on -- the same thing
   * the checkbox column drives in Classic (native `uids` param on
   * workflow_action).  It does not gate Save: editing a cell queues it
   * regardless of selection, exactly like the native listing.
   * ------------------------------------------------------------------- */

  function selectedUidsInDisplayOrder() {
    var seen = {};
    var ordered = [];
    Array.prototype.forEach.call(
      root.querySelectorAll(".as-row-select:checked"),
      function (checkbox) {
        var uid = checkbox.getAttribute("data-uid");
        if (uid && !seen[uid]) {
          seen[uid] = true;
          ordered.push(uid);
        }
      }
    );
    return ordered;
  }

  /* The hidden `uids` field is rendered once with every analysis (see
   * get_all_uids() in views.py); this overwrites it with the current
   * checkbox selection right before the form actually submits. */
  function syncSelectedUidsField() {
    var field = form && form.querySelector('input[name="uids"]');
    if (field) {
      field.value = selectedUidsInDisplayOrder().join(",");
    }
  }

  /* ------------------------------------------------------------------- *
   * workflow transition buttons
   *
   * Which transitions may be fired is a property of the *selected* analyses,
   * never of the layout: their workflow state, the roles of the current user,
   * every guard_handler() of the analysis workflow, and -- when several rows
   * are selected -- only what all of them have in common.  All of that is
   * already computed server-side by senaite.app.listing's ListingTransitions
   * adapter, so the buttons are fetched rather than written down here.
   *
   * Mirrors listing.coffee fetch_transitions() + ButtonBar.coffee.
   * ------------------------------------------------------------------- */

  var transitionsUrl = root.getAttribute("data-transitions-url");
  var transitionsBar = root.querySelector(".as-transitions");
  var modalRoot = document.querySelector(".as-grouped-modal");

  var confirmMessages = (function () {
    try {
      return JSON.parse(root.getAttribute("data-confirm-messages") || "{}");
    } catch (error) {
      return {};
    }
  })();

  /* senaite.core installs the i18n helper globally (senaite.core.js sets
   * window._t).  The transitions endpoint returns untranslated workflow
   * titles -- ajax_transitions carries no @translate decorator -- exactly as
   * ButtonBar.coffee receives them, and translates them the same way. */
  function translate(text) {
    if (typeof window._t === "function") {
      return window._t(text);
    }
    return text;
  }

  /* Copied from ButtonBar.coffee so that a Submit button looks the same
   * whichever layout renders it. */
  var TRANSITION_CSS = {
    "reassign": "btn-secondary",
    "duplicate": "btn-secondary",
    "close": "btn-secondary",
    "assign": "btn-secondary",
    "receive": "btn-primary",
    "open": "btn-primary",
    "verify": "btn-primary",
    "retest": "btn-primary",
    "activate": "btn-success",
    "prepublish": "btn-success",
    "publish": "btn-success",
    "republish": "btn-success",
    "submit": "btn-success",
    "unassign": "btn-warning",
    "cancel": "btn-danger",
    "deactivate": "btn-danger",
    "invalidate": "btn-danger",
    "reject": "btn-danger",
    "retract": "btn-danger",
    "remove": "btn-danger"
  };

  /* Transitions the native listing always asks to confirm, whatever the
   * review state declares (Constants.js: CONFIRM_TRANSITION_IDS). */
  var CONFIRM_TRANSITION_IDS = [
    "cancel", "close", "deactivate", "reinstate", "reject", "remove",
    "retest", "retract", "unassign"
  ];

  function transitionCss(transition) {
    var cls = "btn btn-sm mr-1 mb-1";
    if (TRANSITION_CSS[transition.id]) {
      return cls + " " + TRANSITION_CSS[transition.id];
    }
    if (transition.css_class) {
      return cls + " " + transition.css_class;
    }
    return cls + " btn-outline-secondary";
  }

  /* A custom transition that opens a modal instead of firing a workflow
   * transition; the native listing recognises them by their id alone
   * (listing.coffee doAction).  `modal_set_analysis_remarks` -- the batch
   * "Set remarks" of the worksheet listing -- is currently the only one. */
  function isModalTransition(transition) {
    var id = transition.id || "";
    return id.indexOf("modal") === 0 || /modal_transition$/.test(id);
  }

  function buildTransitionButton(transition, count) {
    var button = document.createElement("button");
    var title = translate(transition.title || transition.id);

    button.className = transitionCss(transition);
    button.setAttribute("data-transition-id", transition.id);
    button.title = transition.help ? translate(transition.help) : title;

    if (isModalTransition(transition)) {
      // Must not submit the form: the modal brings its own.
      button.type = "button";
      button.setAttribute("data-transition-url", transition.url || "");
    } else {
      // A plain submit button, so the existing submit handler keeps doing the
      // work it already does for transitions: flush pending edits first, then
      // post `uids` + `workflow_action_id` to the native workflow_action.
      button.type = "submit";
      button.name = "workflow_action_id";
      button.value = transition.id;
    }

    var label = document.createElement("span");
    label.textContent = title;
    button.appendChild(label);

    if (count) {
      var badge = document.createElement("span");
      badge.className = "badge badge-light";
      badge.style.marginLeft = "0.25em";
      badge.textContent = String(count);
      button.appendChild(badge);
    }

    var confirmMessage = confirmMessages[transition.id];
    if (CONFIRM_TRANSITION_IDS.indexOf(transition.id) !== -1 || confirmMessage) {
      button.setAttribute("data-toggle", "confirmation");
      button.setAttribute("data-title", title + "?");
      if (confirmMessage) {
        button.setAttribute("data-content", confirmMessage);
      }
    }
    return button;
  }

  function buildClearButton() {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-secondary btn-sm mb-1 mr-1";
    button.setAttribute("data-transition-id", "clear_selection");
    button.title = translate("Clear selection");
    button.innerHTML = '<i class="fas fa-circle-notch"></i>';
    return button;
  }

  function clearTransitions() {
    if (transitionsBar) {
      transitionsBar.innerHTML = "";
    }
  }

  function renderTransitions(transitions, count) {
    if (!transitionsBar) {
      return;
    }
    clearTransitions();
    if (!transitions || !transitions.length) {
      return;
    }
    transitionsBar.appendChild(buildClearButton());
    transitions.forEach(function (transition) {
      transitionsBar.appendChild(buildTransitionButton(transition, count));
    });

    // bootstrap-confirmation2 is loaded globally by senaite.core
    // (webpack/app/resources.pt), same as for the ReactJS listing.  Re-bound
    // on every render because the buttons are recreated each time, which is
    // what ButtonBar.coffee does from componentDidUpdate().
    if (window.jQuery && window.jQuery.fn.confirmation) {
      window.jQuery(transitionsBar).find("[data-toggle=confirmation]")
        .confirmation({
          rootSelector: "[data-toggle=confirmation]",
          btnOkLabel: translate("Yes"),
          btnOkClass: "btn btn-outline-primary",
          btnOkIconClass: "fas fa-check-circle mr-1",
          btnCancelLabel: translate("No"),
          btnCancelClass: "btn btn-outline-secondary",
          btnCancelIconClass: "fas fa-circle mr-1",
          container: "body",
          singleton: true
        });
    }
  }

  function fetchTransitions() {
    var uids = selectedUidsInDisplayOrder();

    // Nothing selected: no request, no buttons.  ButtonBar.coffee returns
    // null in that case, and fetch_transitions() short-circuits the same way.
    if (!uids.length || !transitionsUrl) {
      clearTransitions();
      return Promise.resolve([]);
    }

    // IMPORTANT: the payload carries the selection and NOTHING else.
    //
    // maitux.esignature's guard adapter keeps a signature-gated transition
    // *visible* while it is merely being listed, and only enforces the
    // signature on the execution request; it tells the two apart by looking
    // for `workflow_action_id` / `execute_transition` in the request
    // (services/context.py: is_transition_execution_request).  Sending
    // `workflow_action_id` here would make this request look like an
    // execution, the guard would find no verified signature context and
    // return False, and the button would silently never appear.
    return fetch(transitionsUrl, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": getCsrfToken()
      },
      body: JSON.stringify({ selected_uids: uids })
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        var transitions = (data && data.transitions) || [];
        // The selection may have moved on while the request was in flight.
        renderTransitions(transitions, selectedUidsInDisplayOrder().length);
        return transitions;
      })
      .catch(function (error) {
        clearTransitions();
        setStatus("Could not load actions: " + error.message, true);
        throw error;
      });
  }

  /* Debounced: ticking a panel's "select all" flips every row at once, and
   * each flip would otherwise cost a round trip that wakes every selected
   * analysis to evaluate its guards. */
  var transitionsTimer = null;
  function scheduleTransitionsRefresh() {
    if (transitionsTimer) {
      window.clearTimeout(transitionsTimer);
    }
    transitionsTimer = window.setTimeout(function () {
      transitionsTimer = null;
      fetchTransitions().catch(function () {
        /* status line already reports it */
      });
    }, 250);
  }

  /* Load a custom transition that opens in a modal, mirroring
   * listing.coffee loadModal(): the uids ride on the URL, the returned markup
   * is injected as-is, and its form is posted with fetch. */
  function loadTransitionModal(url) {
    if (!url || !modalRoot || !window.jQuery) {
      return;
    }
    var uids = selectedUidsInDisplayOrder();
    var target = new URL(url, window.location.href);
    target.searchParams.append("uids", uids.join(","));

    var el = window.jQuery(modalRoot);
    fetch(target.toString(), { credentials: "include" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        el.empty();
        el.append(html);
        el.one("submit", function (event) {
          event.preventDefault();
          var modalForm = event.target;
          if (!modalForm.action) {
            return;
          }
          fetch(modalForm.action, {
            method: "POST",
            credentials: "include",
            body: new FormData(modalForm)
          })
            .then(function (response) {
              if (!response.ok) {
                throw new Error("HTTP " + response.status);
              }
              return response.text();
            })
            .then(function (text) {
              // The modal may answer with a redirect target instead of markup
              if (text.indexOf("http") === 0) {
                window.location = text;
              } else {
                window.location.reload();
              }
            })
            .catch(function (error) {
              setStatus("Action failed: " + error.message, true);
            })
            .then(function () {
              el.modal("hide");
            });
        });
        el.modal("show");
      })
      .catch(function (error) {
        setStatus("Could not open dialog: " + error.message, true);
      });
  }

  if (transitionsBar) {
    transitionsBar.addEventListener("click", function (event) {
      var button = event.target.closest
        ? event.target.closest("[data-transition-id]")
        : null;
      if (!button) {
        return;
      }
      var id = button.getAttribute("data-transition-id");

      if (id === "clear_selection") {
        event.preventDefault();
        Array.prototype.forEach.call(
          root.querySelectorAll(".as-row-select:checked, .as-select-all:checked"),
          function (checkbox) {
            checkbox.checked = false;
          }
        );
        clearTransitions();
        return;
      }

      if (button.type === "button") {
        event.preventDefault();
        loadTransitionModal(button.getAttribute("data-transition-url"));
      }
      // Anything else is a submit button; the form handler takes over.
    });
  }

  root.addEventListener("change", function (event) {
    var node = event.target;
    if (!node.classList || !node.classList.contains("as-select-all")) {
      return;
    }
    var panel = node.closest(".as-group-panel");
    if (!panel) {
      return;
    }
    Array.prototype.forEach.call(
      panel.querySelectorAll(".as-row-select"),
      function (checkbox) {
        checkbox.checked = node.checked;
      }
    );
    scheduleTransitionsRefresh();
  });

  root.addEventListener("change", function (event) {
    var node = event.target;
    if (!node.classList || !node.classList.contains("as-row-select")) {
      return;
    }
    syncSelectAll(node);
    scheduleTransitionsRefresh();
  });

  if (saveButton) {
    saveButton.addEventListener("click", function () {
      flush().catch(function () {
        /* status line already reports it */
      });
    });
  }

  // event.submitter is not available in every supported browser, so remember
  // which button was pressed. Without it a deferred submit would lose the
  // workflow_action_id and the handler would bail out with "No action defined".
  var lastSubmitter = null;
  root.addEventListener("click", function (event) {
    var button = event.target.closest
      ? event.target.closest("button[type='submit'], input[type='submit']")
      : null;
    if (button && form && form.contains(button)) {
      lastSubmitter = button;
    }
  });

  /* Flush before any transition, exactly like the native listing does. The
   * form is only submitted once every pending edit is persisted. */
  if (form) {
    form.addEventListener("submit", function (event) {
      // Always sync, whether or not a save is pending below: an untouched
      // page must still submit only the checked rows, not every analysis.
      syncSelectedUidsField();

      // Never post a transition with an empty selection.  WorkflowActionHandler
      // .get_uids() falls back to the UID of the *context* when `uids` is
      // empty, so an empty submit from a worksheet asks to transition the
      // worksheet itself rather than any analysis.  Buttons are already hidden
      // while nothing is selected; this is the belt to that pair of braces.
      if (!selectedUidsInDisplayOrder().length) {
        event.preventDefault();
        clearTransitions();
        return;
      }

      if (!isPending()) {
        return; // nothing queued: let it through
      }
      event.preventDefault();

      var submitter = event.submitter || lastSubmitter;
      flush()
        .then(function () {
          if (submitter && submitter.name) {
            // preserve which workflow action was clicked
            var hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = submitter.name;
            hidden.value = submitter.value;
            form.appendChild(hidden);
          }
          form.submit(); // native submit: does not re-fire this handler
        })
        .catch(function () {
          /* keep the user on the page with the edits still queued */
        });
    });
  }

  refreshSaveButton();
})();
