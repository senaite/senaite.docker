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
  });

  root.addEventListener("change", function (event) {
    var node = event.target;
    if (!node.classList || !node.classList.contains("as-row-select")) {
      return;
    }
    syncSelectAll(node);
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
