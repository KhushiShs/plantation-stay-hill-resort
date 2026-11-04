/* enquire.js - Double submission prevention for enquiry form */
(function() {
  'use strict';

  function initEnquiryForm() {
    const form = document.getElementById('enquiry-form');
    if (!form) return;

    form.addEventListener('submit', function() {
      const btn = document.getElementById('submit-btn');
      if (btn) {
        btn.disabled = true;
        btn.innerText = 'Submitting...';
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEnquiryForm);
  } else {
    initEnquiryForm();
  }
})();

