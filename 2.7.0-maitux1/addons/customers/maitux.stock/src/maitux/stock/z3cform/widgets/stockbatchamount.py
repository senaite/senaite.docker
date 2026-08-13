# -*- coding: utf-8 -*-
from z3c.form.browser.text import TextWidget
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope.interface import implementer


class StockBatchAmountWidget(TextWidget):
    def render(self):
        html = super(StockBatchAmountWidget, self).render()
        script = u"""
<script type="text/javascript">
(function () {
  if (window.__senaite_stockbatch_amount_autofill) return;
  window.__senaite_stockbatch_amount_autofill = true;

  function asUid(value) {
    if (!value) return "";
    value = String(value);
    var parts = value.split(/\\r?\\n/);
    return (parts[0] || "").trim();
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

  function fetchJSON(url, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status < 200 || xhr.status >= 300) return cb(null);
      try {
        cb(JSON.parse(xhr.responseText));
      } catch (e) {
        cb(null);
      }
    };
    xhr.send(null);
  }

  function shouldAutofill(input) {
    if (!input) return false;
    if (input.dataset && input.dataset.autofilled === "1") return true;
    var v = (input.value || "").trim();
    if (!v) return true;
    if (v === "0" || v === "0.0" || v === "0.00") return true;
    return false;
  }

  function setAutofillValue(input, value) {
    if (!input) return;
    input.value = value;
    if (input.dataset) input.dataset.autofilled = "1";
    try {
      var evt = document.createEvent("HTMLEvents");
      evt.initEvent("change", true, true);
      input.dispatchEvent(evt);
    } catch (e) {}
  }

  function init() {
    var stockField = document.querySelector('textarea[name="form.widgets.stock"],textarea[name="form.widgets.stock:list"]');
    var amountField = document.querySelector('input[name="form.widgets.current_amount"]');
    if (!stockField || !amountField) return;

    var lastUid = null;
    setInterval(function () {
      var uid = asUid(stockField.value);
      if (!uid || uid === lastUid) return;
      lastUid = uid;
      if (!shouldAutofill(amountField)) return;
      var url = getPortalUrl() + "/@@stock_quantity_json?stock_uid=" + encodeURIComponent(uid);
      fetchJSON(url, function (data) {
        if (!data || !data.quantity) return;
        if (!shouldAutofill(amountField)) return;
        setAutofillValue(amountField, String(data.quantity));
      });
    }, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
</script>
"""
        return html + script


@implementer(IFieldWidget)
def StockBatchAmountWidgetFactory(field, request):
    return FieldWidget(field, StockBatchAmountWidget(request))
