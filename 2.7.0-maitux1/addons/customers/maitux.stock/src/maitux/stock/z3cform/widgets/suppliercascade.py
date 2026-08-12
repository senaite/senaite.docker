# -*- coding: utf-8 -*-
from z3c.form.browser.select import SelectWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope.interface import implementer


class StockSupplierCascadeWidget(SelectWidget):
    def render(self):
        html = super(StockSupplierCascadeWidget, self).render()
        script = u"""
<script type="text/javascript">
(function () {
  if (window.__senaite_stock_po_supplier_cascade) return;
  window.__senaite_stock_po_supplier_cascade = true;

  var registry = [];
  var pollStarted = false;

  function asUid(value) {
    if (!value) return "";
    value = String(value);
    var parts = value.split(/\\r?\\n/);
    return parts[0] || "";
  }

  function escapeAttrValue(value) {
    return String(value).replace(/"/g, '\\"');
  }

  function fetchJSON(url, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status < 200 || xhr.status >= 300) return cb([]);
      try {
        cb(JSON.parse(xhr.responseText));
      } catch (e) {
        cb([]);
      }
    };
    xhr.send(null);
  }

  function getPortalUrl() {
    var body = document.body;
    var url = "";
    if (body) {
      url = body.getAttribute("data-portal-url") || "";
      if (!url && body.dataset && body.dataset.portalUrl) {
        url = body.dataset.portalUrl;
      }
    }
    if (!url && window.portal_url) {
      url = window.portal_url;
    }
    return String(url || "").replace(/\\/$/, "");
  }

  function refreshBootstrapSelect(selectEl) {
    if (!selectEl) return;
    if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.selectpicker) return;
    try {
      window.jQuery(selectEl).selectpicker("refresh");
    } catch (e) {}
  }

  function updateSupplierOptions(selectEl, suppliers) {
    var current = selectEl.value || "";
    while (selectEl.options.length > 0) {
      selectEl.remove(0);
    }
    var empty = document.createElement("option");
    empty.value = "";
    empty.text = "";
    selectEl.appendChild(empty);
    suppliers.forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = s.uid;
      opt.text = s.title;
      selectEl.appendChild(opt);
    });
    if (current) {
      for (var i = 0; i < selectEl.options.length; i++) {
        if (selectEl.options[i].value === current) {
          selectEl.value = current;
          refreshBootstrapSelect(selectEl);
          return;
        }
      }
      selectEl.value = "";
    }
    refreshBootstrapSelect(selectEl);
  }

  function getStockNameForSupplier(selectEl) {
    var supplierName = selectEl.name || "";
    supplierName = supplierName.replace(/:list$/, "");
    if (!supplierName || supplierName.indexOf(".supplier") === -1) return null;
    var stockName = supplierName.replace(/\\.supplier$/, ".stock");
    if (!stockName || stockName === supplierName) return null;
    return stockName;
  }

  function parseJSONAttr(el, attr, fallback) {
    if (!el || !el.getAttribute) return fallback;
    var raw = el.getAttribute(attr);
    if (!raw) return fallback;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function findStockWidgetEl(selectEl, stockName) {
    if (!stockName) return null;
    var row = selectEl.closest ? selectEl.closest("tr") : null;
    if (!row) {
      row = selectEl.closest ? selectEl.closest(".datagridwidget-row") : null;
    }
    var scope = row || document;
    var widgets = scope.querySelectorAll(".senaite-uidreference-widget-input,.senaite-queryselect-widget-input,[data-name][data-values],[data-name][data-records]");
    for (var i = 0; i < widgets.length; i++) {
      var w = widgets[i];
      var dn = parseJSONAttr(w, "data-name", null);
      if (!dn) continue;
      if (dn === stockName) return w;
    }
    return null;
  }

  function getStockUid(entry) {
    if (!entry) return "";
    var w = entry.stockWidgetEl;
    if (w) {
      var values = parseJSONAttr(w, "data-values", null);
      if (values && values.length) {
        return asUid(values[0]);
      }
      var records = parseJSONAttr(w, "data-records", null);
      if (records && typeof records === "object") {
        for (var k in records) {
          if (records.hasOwnProperty(k) && k) {
            return asUid(k);
          }
        }
      }
      var fieldEl = w.querySelector('[name="' + escapeAttrValue(entry.stockName) + '"]');
      if (fieldEl) {
        var raw = fieldEl.value || "";
        if (!raw && fieldEl.getAttribute) {
          raw = fieldEl.getAttribute("value") || "";
        }
        if (!raw && fieldEl.tagName && fieldEl.tagName.toLowerCase() === "textarea") {
          raw = fieldEl.textContent || "";
        }
        return asUid(raw);
      }
    }
    return "";
  }

  function refreshEntry(entry) {
    if (!document.contains(entry.selectEl) || !document.contains(entry.stockWidgetEl)) {
      return false;
    }
    var uid = getStockUid(entry);
    if (uid === entry.lastUid) {
      return true;
    }
    entry.lastUid = uid;
    if (!uid) {
      updateSupplierOptions(entry.selectEl, []);
      return true;
    }
    var base = getPortalUrl();
    var url = base + "/@@stock_suppliers_json?stock_uid=" + encodeURIComponent(uid);
    fetchJSON(url, function (data) {
      updateSupplierOptions(entry.selectEl, Array.isArray(data) ? data : []);
    });
    return true;
  }

  function bindSupplier(selectEl) {
    if (!selectEl || (selectEl.dataset && selectEl.dataset.senaiteStockSupplierCascade === "1")) {
      return;
    }
    var stockName = getStockNameForSupplier(selectEl);
    if (!stockName) return;
    var stockWidgetEl = findStockWidgetEl(selectEl, stockName);
    if (!stockWidgetEl) return;

    if (selectEl.dataset) {
      selectEl.dataset.senaiteStockSupplierCascade = "1";
    }
    var entry = {selectEl: selectEl, stockName: stockName, stockWidgetEl: stockWidgetEl, lastUid: null, observer: null};
    registry.push(entry);

    if (window.MutationObserver) {
      try {
        entry.observer = new MutationObserver(function () {
          refreshEntry(entry);
        });
        entry.observer.observe(stockWidgetEl, {attributes: true, attributeFilter: ["data-values", "data-records"]});
      } catch (e) {
        entry.observer = null;
      }
    }

    refreshEntry(entry);

    if (!pollStarted) {
      pollStarted = true;
      setInterval(function () {
        var next = [];
        for (var i = 0; i < registry.length; i++) {
          try {
            if (refreshEntry(registry[i])) {
              next.push(registry[i]);
            } else if (registry[i] && registry[i].observer) {
              try { registry[i].observer.disconnect(); } catch (e) {}
            }
          } catch (e2) {}
        }
        registry = next;
      }, 500);
    }
  }

  function init() {
    var selects = document.querySelectorAll('select[name$=".supplier"],select[name$=".supplier:list"]');
    for (var i = 0; i < selects.length; i++) {
      bindSupplier(selects[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  document.body.addEventListener("datagrid:row_added", function () {
    init();
  });
})();
</script>
"""
        return html + script


@implementer(IFieldWidget)
def StockSupplierCascadeWidgetFactory(field, request):
    return FieldWidget(field, StockSupplierCascadeWidget(request))
