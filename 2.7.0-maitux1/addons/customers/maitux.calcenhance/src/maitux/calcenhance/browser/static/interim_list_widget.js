/**
 * maitux.calcenhance - List Interim Field Widget
 *
 * Converts list-type interim field text inputs to textareas
 * in the worksheet/results listing table.
 *
 * The listing ReactJS component renders text <input> elements for
 * interim fields without choices. This script watches the DOM and
 * replaces inputs that have data-result-type="list" with <textarea>.
 */
(function() {
  'use strict';

  var ATTR_NAME = 'data-interim-type';
  var LIST_TYPE = 'list';

  /**
   * Convert a plain text <input> to <textarea> for list-type interims.
   */
  function convertToListTextarea(input) {
    if (input.tagName !== 'INPUT' || input.type !== 'text') return;
    if (input.getAttribute(ATTR_NAME) !== LIST_TYPE) return;
    // Skip already converted
    if (input.dataset.converted === 'true') return;

    var textarea = document.createElement('textarea');
    // Copy attributes
    textarea.value = input.value || '';
    textarea.name = input.name;
    textarea.className = input.className;
    textarea.disabled = input.disabled;

    // Copy dataset attributes
    if (input.dataset.uid) textarea.dataset.uid = input.dataset.uid;
    if (input.dataset.columnKey) textarea.dataset.columnKey = input.dataset.columnKey;

    // Copy all attributes
    var attrs = input.attributes;
    for (var i = 0; i < attrs.length; i++) {
      var attr = attrs[i];
      if (attr.name.indexOf('data-') === 0) {
        textarea.setAttribute(attr.name, attr.value);
      }
    }

    // Set list-specific styling
    textarea.style.resize = 'vertical';
    textarea.rows = 3;
    textarea.setAttribute('data-converted', 'true');
    textarea.setAttribute('title', input.title || 'Enter values, one per line');
    textarea.setAttribute('wrap', 'off');

    // Replace
    input.parentNode.replaceChild(textarea, input);
  }

  /**
   * Scan the DOM for list-type interim inputs and convert them.
   */
  function scanAndConvert(root) {
    root = root || document;
    // Find all input elements (the listing renders inputs for editable fields)
    var inputs = root.querySelectorAll('input[type="text"]');
    for (var i = 0; i < inputs.length; i++) {
      convertToListTextarea(inputs[i]);
    }
  }

  /**
   * Listen for listing:after_load_table events to re-scan.
   */
  function onListingLoaded(event) {
    var table = event.target;
    if (table) {
      // Small delay to let React render
      setTimeout(function() { scanAndConvert(table); }, 100);
    }
  }

  /**
   * Listen for the save event to re-scan after AJAX save.
   */
  function onAfterSave(event) {
    setTimeout(function() { scanAndConvert(); }, 200);
  }

  // Initial scan
  document.addEventListener('DOMContentLoaded', function() {
    scanAndConvert();

    // Listen for listing events
    document.body.addEventListener('listing:after_table_render', onListingLoaded);
    document.body.addEventListener('listing:after_transition_event', onAfterSave);
    document.body.addEventListener('listing:after_save_event', onAfterSave);
  });

  // Also try to run immediately if DOM is already loaded
  if (document.readyState !== 'loading') {
    scanAndConvert();
  }

  // Listen for listing events immediately
  document.body.addEventListener('listing:after_table_render', onListingLoaded);
  document.body.addEventListener('listing:after_transition_event', onAfterSave);
  document.body.addEventListener('listing:after_save_event', onAfterSave);

  // Use MutationObserver as fallback for dynamic content
  var observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      if (mutation.addedNodes.length) {
        for (var i = 0; i < mutation.addedNodes.length; i++) {
          var node = mutation.addedNodes[i];
          if (node.nodeType === 1) {
            // Check if the added node or its children have list inputs
            if (node.querySelectorAll) {
              scanAndConvert(node);
            }
          }
        }
      }
    });
  });

  // Start observing when body exists
  function startObserving() {
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    } else {
      setTimeout(startObserving, 100);
    }
  }
  startObserving();

})();
