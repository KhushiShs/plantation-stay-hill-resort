/* hold-timer.js - Countdown timer for booking hold reservation */
(function() {
  'use strict';

  function initHoldTimer() {
    const timerDisplay = document.getElementById('timer-display');
    const progressBar = document.getElementById('hold-progress');

    if (!timerDisplay || !progressBar) return;

    let totalSeconds = parseInt(timerDisplay.getAttribute('data-remaining-seconds'), 10) || 0;
    const initialSeconds = parseInt(timerDisplay.getAttribute('data-initial-seconds'), 10) || 600;

    const interval = setInterval(function() {
      if (totalSeconds <= 0) {
        clearInterval(interval);
        timerDisplay.innerText = "0:00";
        progressBar.style.width = "0%";
        window.location.reload();
        return;
      }
      totalSeconds--;
      const mins = Math.floor(totalSeconds / 60);
      const secs = totalSeconds % 60;
      timerDisplay.innerText = mins + ":" + (secs < 10 ? '0' : '') + secs;
      const pct = Math.max(0, (totalSeconds / initialSeconds) * 100);
      progressBar.style.width = pct + "%";
    }, 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHoldTimer);
  } else {
    initHoldTimer();
  }
})();

