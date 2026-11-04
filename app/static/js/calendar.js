/* calendar.js - Interactive tariff calendar date picker with month navigation & clear selection states */
(function() {
  'use strict';

  function initRoomCalendar() {
    const calendarRoot = document.getElementById('tariff-calendar');
    const checkInInput = document.getElementById('check_in');
    const checkOutInput = document.getElementById('check_out');
    const quoteForm = document.getElementById('quote-form');
    const calendarMsg = document.getElementById('calendar-range-msg');
    const calendarStatus = document.getElementById('calendar-status');
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

    function formatDateFriendly(isoStr) {
      if (!isoStr) return '';
      // Parse YYYY-MM-DD safely
      const parts = isoStr.split('-');
      if (parts.length !== 3) return isoStr;
      const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      const weekdayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return weekdayNames[d.getDay()] + ' ' + d.getDate() + ' ' + monthNames[d.getMonth()];
    }

    function calculateNights(startIso, endIso) {
      const p1 = startIso.split('-');
      const p2 = endIso.split('-');
      const d1 = new Date(parseInt(p1[0], 10), parseInt(p1[1], 10) - 1, parseInt(p1[2], 10));
      const d2 = new Date(parseInt(p2[0], 10), parseInt(p2[1], 10) - 1, parseInt(p2[2], 10));
      const diffMs = d2.getTime() - d1.getTime();
      return Math.round(diffMs / (1000 * 60 * 60 * 24));
    }

    function updateStatusLine() {
      if (!calendarStatus) return;

      if (!selectedCheckIn) {
        calendarStatus.innerText = 'Select your check-in date.';
      } else if (selectedCheckIn && !selectedCheckOut) {
        calendarStatus.innerText = 'Check-in ' + formatDateFriendly(selectedCheckIn) + '. Now select check-out.';
      } else if (selectedCheckIn && selectedCheckOut) {
        const nights = calculateNights(selectedCheckIn, selectedCheckOut);
        const nightLabel = nights === 1 ? '1 night' : nights + ' nights';
        calendarStatus.innerText = formatDateFriendly(selectedCheckIn) + ' to ' + formatDateFriendly(selectedCheckOut) + ', ' + nightLabel + '.';
      }
    }

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
      return calendarRoot.querySelector('button[data-date="' + isoDate + '"]');
    }

    function removeTagBadge(btn) {
      const existing = btn.querySelector('.cal-badge-tag');
      if (existing) {
        existing.remove();
      }
    }

    function addTagBadge(btn, text) {
      removeTagBadge(btn);
      const tag = document.createElement('span');
      tag.className = 'cal-badge-tag';
      tag.innerText = text;
      btn.appendChild(tag);
    }

    function updateVisualHighlight() {
      const allButtons = getAllDateButtons();
      allButtons.forEach(btn => {
        btn.classList.remove('is-start', 'is-end', 'in-range', 'is-dimmed');
        btn.removeAttribute('aria-pressed');
        removeTagBadge(btn);
      });

      updateStatusLine();

      if (!selectedCheckIn) {
        showRangeWarning('');
        return;
      }

      // Check-in button styling (.is-start)
      const inBtn = getButtonForDate(selectedCheckIn);
      if (inBtn) {
        inBtn.classList.add('is-start');
        inBtn.setAttribute('aria-pressed', 'true');
        addTagBadge(inBtn, 'In');
      }

      // If only check-in is selected, dim earlier dates or same date
      if (selectedCheckIn && !selectedCheckOut) {
        allButtons.forEach(btn => {
          const btnDate = btn.getAttribute('data-date');
          if (btnDate && btnDate <= selectedCheckIn && btn !== inBtn) {
            btn.classList.add('is-dimmed');
          }
        });
      }

      if (selectedCheckOut && selectedCheckOut > selectedCheckIn) {
        const outBtn = getButtonForDate(selectedCheckOut);
        if (outBtn) {
          outBtn.classList.add('is-end');
          outBtn.setAttribute('aria-pressed', 'true');
          addTagBadge(outBtn, 'Out');
        }

        // Highlight in-between nights & check if any unavailable night
        let hasTakenNight = false;
        const p1 = selectedCheckIn.split('-');
        const p2 = selectedCheckOut.split('-');
        const cur = new Date(parseInt(p1[0], 10), parseInt(p1[1], 10) - 1, parseInt(p1[2], 10));
        const end = new Date(parseInt(p2[0], 10), parseInt(p2[1], 10) - 1, parseInt(p2[2], 10));

        // Advance past start
        cur.setDate(cur.getDate() + 1);

        while (cur < end) {
          const y = cur.getFullYear();
          const m = String(cur.getMonth() + 1).padStart(2, '0');
          const d = String(cur.getDate()).padStart(2, '0');
          const iso = y + '-' + m + '-' + d;
          const btn = getButtonForDate(iso);
          if (btn) {
            const isAvail = btn.getAttribute('data-available') === 'true';
            if (!isAvail) {
              hasTakenNight = true;
            }
            btn.classList.add('in-range');
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
        const p1 = selectedCheckIn.split('-');
        const p2 = clickedDate.split('-');
        const cur = new Date(parseInt(p1[0], 10), parseInt(p1[1], 10) - 1, parseInt(p1[2], 10));
        const end = new Date(parseInt(p2[0], 10), parseInt(p2[1], 10) - 1, parseInt(p2[2], 10));

        while (cur < end) {
          const y = cur.getFullYear();
          const m = String(cur.getMonth() + 1).padStart(2, '0');
          const d = String(cur.getDate()).padStart(2, '0');
          const iso = y + '-' + m + '-' + d;
          const checkBtn = getButtonForDate(iso);
          if (checkBtn && checkBtn.getAttribute('data-available') !== 'true') {
            hasTakenNight = true;
            break;
          }
          cur.setDate(cur.getDate() + 1);
        }

        if (hasTakenNight) {
          showRangeWarning("Those dates include a night that is taken.");
          return;
        }

        // Range is valid!
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
