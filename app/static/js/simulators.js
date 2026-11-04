/* simulators.js - Tabs switching for staff inbound simulators */
(function() {
  'use strict';

  function initSimulators() {
    const btnEmail = document.getElementById('btn-tab-email');
    const btnWa = document.getElementById('btn-tab-whatsapp');
    const pEmail = document.getElementById('panel-email');
    const pWa = document.getElementById('panel-whatsapp');

    if (!btnEmail || !btnWa || !pEmail || !pWa) return;

    btnEmail.addEventListener('click', function() {
      pEmail.style.display = 'block';
      pWa.style.display = 'none';
      btnEmail.style.background = '#EFE9DC';
      btnEmail.style.fontWeight = '600';
      btnWa.style.background = 'transparent';
      btnWa.style.fontWeight = 'normal';
    });

    btnWa.addEventListener('click', function() {
      pEmail.style.display = 'none';
      pWa.style.display = 'block';
      btnWa.style.background = '#EFE9DC';
      btnWa.style.fontWeight = '600';
      btnEmail.style.background = 'transparent';
      btnEmail.style.fontWeight = 'normal';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSimulators);
  } else {
    initSimulators();
  }
})();

