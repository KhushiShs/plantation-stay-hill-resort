/* room-calendar.js - Interactive tariff calendar date picker */
(function() {
  'use strict';

  function initRoomCalendar() {
    const calendarRoot = document.getElementById('tariff-calendar');
    const checkInInput = document.getElementById('check_in');
    const checkOutInput = document.getElementById('check_out');
    const quoteForm = document.getElementById('quote-form');
    const calendarMsg = document.getElementById('calendar-range-msg');
    const clearBtn = document.getElementById('clear-dates-btn');

    if (!calendarRoot || !checkInInput || !checkOutInput || !quoteForm) {
      return;
    }

    let selectedCheckIn = checkInInput.value || null;
    let selectedCheckOut = checkOutInput.value || null;

    // Map of date ISO string -> { available: bool, soldOut: bool, element: HTMLElement }
    const dayButtons = calendarRoot.querySelectorAll('button[data-date]');
    const daysMap = {};
    dayButtons.forEach(btn => {
      const d = btn.getAttribute('data-date');
      const isAvail = btn.getAttribute('data-available') === 'true';
      const isSoldOut = btn.getAttribute('data-sold-out') === 'true';
      daysMap[d] = {
        element: btn,
        available: isAvail,
        soldOut: isSoldOut
      };
    });

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

    function updateVisualHighlight() {
      dayButtons.forEach(btn => {
        btn.classList.remove('cal-selected-in', 'cal-selected-out', 'cal-in-range');
        btn.removeAttribute('aria-selected');
      });

      if (!selectedCheckIn) {
        showRangeWarning('');
        return;
      }

      const inBtn = daysMap[selectedCheckIn];
      if (inBtn) {
        inBtn.element.classList.add('cal-selected-in');
        inBtn.element.setAttribute('aria-selected', 'true');
      }

      if (selectedCheckOut && selectedCheckOut > selectedCheckIn) {
        const outBtn = daysMap[selectedCheckOut];
        if (outBtn) {
          outBtn.element.classList.add('cal-selected-out');
          outBtn.element.setAttribute('aria-selected', 'true');
        }

        // Check if range has any sold out / unavailable night in between
        let hasTakenNight = false;
        const cur = new Date(selectedCheckIn + 'T00:00:00');
        const end = new Date(selectedCheckOut + 'T00:00:00');

        while (cur < end) {
          const iso = cur.toISOString().split('T')[0];
          const info = daysMap[iso];
          if (info && !info.available) {
            hasTakenNight = true;
          }
          if (info && iso !== selectedCheckIn && iso !== selectedCheckOut) {
            info.element.classList.add('cal-in-range');
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
        // Trigger HTMX on quoteForm
        if (window.htmx) {
          window.htmx.trigger(quoteForm, 'change');
        } else {
          quoteForm.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }

    function onDateButtonClick(btn) {
      const clickedDate = btn.getAttribute('data-date');
      const isAvailable = btn.getAttribute('data-available') === 'true';

      // State 1: Both dates currently selected or no date selected -> Start fresh with check-in
      if (!selectedCheckIn || (selectedCheckIn && selectedCheckOut)) {
        if (!isAvailable) {
          return; // Cannot start check-in on unavailable date
        }
        selectedCheckIn = clickedDate;
        selectedCheckOut = null;
        updateVisualHighlight();
        checkInInput.value = selectedCheckIn;
        checkOutInput.value = '';
        return;
      }

      // State 2: Check-in is selected, picking check-out
      if (selectedCheckIn && !selectedCheckOut) {
        // If clicked on or before check-in -> Restart check-in
        if (clickedDate <= selectedCheckIn) {
          if (!isAvailable) {
            return;
          }
          selectedCheckIn = clickedDate;
          selectedCheckOut = null;
          updateVisualHighlight();
          checkInInput.value = selectedCheckIn;
          checkOutInput.value = '';
          return;
        }

        // Clicked after check-in -> This is the check-out date!
        // Note: Check-out day itself is allowed even if sold out (since guests depart in the morning)
        selectedCheckOut = clickedDate;
        updateVisualHighlight();
        syncInputsAndTriggerQuote();
      }
    }

    // Attach click listeners to date buttons
    dayButtons.forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        onDateButtonClick(this);
      });
    });

    // Clear dates handler
    if (clearBtn) {
      clearBtn.addEventListener('click', function(e) {
        e.preventDefault();
        selectedCheckIn = null;
        selectedCheckOut = null;
        updateVisualHighlight();
        checkInInput.value = '';
        checkOutInput.value = '';
        showRangeWarning('');
      });
    }

    // Sync if user manually modifies native date inputs
    function onManualInputChange() {
      selectedCheckIn = checkInInput.value || null;
      selectedCheckOut = checkOutInput.value || null;
      updateVisualHighlight();
    }
    checkInInput.addEventListener('change', onManualInputChange);
    checkOutInput.addEventListener('change', onManualInputChange);

    // Initial highlight sync
    updateVisualHighlight();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRoomCalendar);
  } else {
    initRoomCalendar();
  }
})();

