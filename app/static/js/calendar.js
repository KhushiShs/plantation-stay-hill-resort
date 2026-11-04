/* calendar.js - Interactive tariff calendar date picker with month navigation */
(function() {
  'use strict';

  function initRoomCalendar() {
    const calendarRoot = document.getElementById('tariff-calendar');
    const checkInInput = document.getElementById('check_in');
    const checkOutInput = document.getElementById('check_out');
    const quoteForm = document.getElementById('quote-form');
    const calendarMsg = document.getElementById('calendar-range-msg');
    const clearBtn = document.getElementById('clear-dates-btn');
    const prevBtn = document.getElementById('cal-prev-btn');
    const nextBtn = document.getElementById('cal-next-btn');
    const currentMonthLabel = document.getElementById('cal-current-month-label');

    if (!calendarRoot || !checkInInput || !checkOutInput || !quoteForm) {
      return;
    }

    // Month sections
    const monthSections = Array.from(calendarRoot.querySelectorAll('section.cal-month'));
    let currentMonthIndex = 0;

    function updateMonthDisplay() {
      monthSections.forEach((section, idx) => {
        if (idx === currentMonthIndex) {
          section.removeAttribute('hidden');
          if (currentMonthLabel) {
            currentMonthLabel.innerText = section.getAttribute('data-month-name') || '';
          }
        } else {
          section.setAttribute('hidden', '');
        }
      });

      if (prevBtn) {
        prevBtn.disabled = (currentMonthIndex === 0);
      }
      if (nextBtn) {
        nextBtn.disabled = (currentMonthIndex >= monthSections.length - 1);
      }
    }

    if (prevBtn) {
      prevBtn.addEventListener('click', function(e) {
        e.preventDefault();
        if (currentMonthIndex > 0) {
          currentMonthIndex--;
          updateMonthDisplay();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', function(e) {
        e.preventDefault();
        if (currentMonthIndex < monthSections.length - 1) {
          currentMonthIndex++;
          updateMonthDisplay();
        }
      });
    }

    // Range selection state
    let selectedCheckIn = checkInInput.value || null;
    let selectedCheckOut = checkOutInput.value || null;

    function showRangeWarning(text) {
      if (calendarMsg) {
        if (text) {
          calendarMsg.innerText = text;
          calendarMsg.style.display = 'block';
        } else {
          calendarMsg.innerText = '';
          calendarMsg.style.display = 'none';
        }
      }
    }

    function getAllDateButtons() {
      return calendarRoot.querySelectorAll('button[data-date]');
    }

    function getButtonForDate(isoDate) {
      return calendarRoot.querySelector(`button[data-date="${isoDate}"]`);
    }

    function updateVisualHighlight() {
      const allButtons = getAllDateButtons();
      allButtons.forEach(btn => {
        btn.classList.remove('cal-selected-in', 'cal-selected-out', 'in-range');
        btn.removeAttribute('aria-selected');
      });

      if (!selectedCheckIn) {
        showRangeWarning('');
        return;
      }

      const inBtn = getButtonForDate(selectedCheckIn);
      if (inBtn) {
        inBtn.classList.add('cal-selected-in');
        inBtn.setAttribute('aria-selected', 'true');
      }

      if (selectedCheckOut && selectedCheckOut > selectedCheckIn) {
        const outBtn = getButtonForDate(selectedCheckOut);
        if (outBtn) {
          outBtn.classList.add('cal-selected-out');
          outBtn.setAttribute('aria-selected', 'true');
        }

        // Check if range contains any unavailable night in between
        let hasTakenNight = false;
        const cur = new Date(selectedCheckIn + 'T00:00:00');
        const end = new Date(selectedCheckOut + 'T00:00:00');

        while (cur < end) {
          const iso = cur.toISOString().split('T')[0];
          const btn = getButtonForDate(iso);
          if (btn) {
            const isAvail = btn.getAttribute('data-available') === 'true';
            if (!isAvail) {
              hasTakenNight = true;
            }
            if (iso !== selectedCheckIn && iso !== selectedCheckOut) {
              btn.classList.add('in-range');
            }
          }
          cur.setDate(cur.getDate() + 1);
        }

        if (hasTakenNight) {
          showRangeWarning("Those dates include a night that is taken.");
        } else {
          showRangeWarning('');
        }
      } else {
        showRangeWarning('');
      }
    }

    function syncInputsAndTriggerQuote() {
      checkInInput.value = selectedCheckIn || '';
      checkOutInput.value = selectedCheckOut || '';

      if (selectedCheckIn && selectedCheckOut && selectedCheckOut > selectedCheckIn) {
        if (window.htmx) {
          window.htmx.trigger(quoteForm, 'change');
        } else {
          quoteForm.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }

    // Event delegation on calendarRoot for all date buttons
    calendarRoot.addEventListener('click', function(e) {
      const btn = e.target.closest('button[data-date]');
      if (!btn) return;

      e.preventDefault();
      const clickedDate = btn.getAttribute('data-date');
      const isAvailable = btn.getAttribute('data-available') === 'true';

      // State 1: No check-in or both dates already selected -> Start fresh with check-in
      if (!selectedCheckIn || (selectedCheckIn && selectedCheckOut)) {
        if (!isAvailable) {
          return; // Unavailable dates cannot be check-in
        }
        selectedCheckIn = clickedDate;
        selectedCheckOut = null;
        checkInInput.value = selectedCheckIn;
        checkOutInput.value = '';
        showRangeWarning('');
        updateVisualHighlight();
        return;
      }

      // State 2: Check-in selected, choosing check-out
      if (selectedCheckIn && !selectedCheckOut) {
        if (clickedDate <= selectedCheckIn) {
          // Clicked earlier date or same date: restart check-in
          if (!isAvailable) {
            return;
          }
          selectedCheckIn = clickedDate;
          selectedCheckOut = null;
          checkInInput.value = selectedCheckIn;
          checkOutInput.value = '';
          showRangeWarning('');
          updateVisualHighlight();
          return;
        }

        // Clicked a later date -> Check-out candidate!
        // Check if any intermediate night is taken/sold out
        let hasTakenNight = false;
        const cur = new Date(selectedCheckIn + 'T00:00:00');
        const end = new Date(clickedDate + 'T00:00:00');

        while (cur < end) {
          const iso = cur.toISOString().split('T')[0];
          const checkBtn = getButtonForDate(iso);
          if (checkBtn && checkBtn.getAttribute('data-available') !== 'true') {
            hasTakenNight = true;
            break;
          }
          cur.setDate(cur.getDate() + 1);
        }

        if (hasTakenNight) {
          showRangeWarning("Those dates include a night that is taken.");
          // Do not set invalid range
          return;
        }

        // Range is valid! Check-out day itself is allowed even if sold out
        selectedCheckOut = clickedDate;
        showRangeWarning('');
        updateVisualHighlight();
        syncInputsAndTriggerQuote();
      }
    });

    // Clear dates handler
    if (clearBtn) {
      clearBtn.addEventListener('click', function(e) {
        e.preventDefault();
        selectedCheckIn = null;
        selectedCheckOut = null;
        checkInInput.value = '';
        checkOutInput.value = '';
        showRangeWarning('');
        updateVisualHighlight();
        // Trigger quote reset
        if (window.htmx) {
          window.htmx.trigger(quoteForm, 'change');
        } else {
          quoteForm.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    }

    // Bidirectional sync when typing in native date inputs
    function onManualInputChange() {
      selectedCheckIn = checkInInput.value || null;
      selectedCheckOut = checkOutInput.value || null;
      updateVisualHighlight();
    }
    checkInInput.addEventListener('change', onManualInputChange);
    checkOutInput.addEventListener('change', onManualInputChange);
    checkInInput.addEventListener('input', onManualInputChange);
    checkOutInput.addEventListener('input', onManualInputChange);

    // Initial view
    updateMonthDisplay();
    updateVisualHighlight();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRoomCalendar);
  } else {
    initRoomCalendar();
  }
})();

