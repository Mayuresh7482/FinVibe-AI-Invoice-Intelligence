/**
 * FinVibe — Dashboard JavaScript
 * Handles: auto-dismiss alerts, form interactions, keyboard shortcuts.
 */

document.addEventListener('DOMContentLoaded', function () {
    // ─── Auto-dismiss alerts after 5 seconds ────────────────────────
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // ─── Search auto-submit on Enter ────────────────────────────────
    const searchInput = document.getElementById('id_search');
    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                const form = document.getElementById('filter-form');
                if (form) form.submit();
            }
        });

        // Focus search on Ctrl+K
        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        });
    }

    // ─── Clickable table rows ───────────────────────────────────────
    const rows = document.querySelectorAll('.invoice-row');
    rows.forEach(function (row) {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function (e) {
            // Don't navigate if clicking a button or link
            if (e.target.closest('a, button, form')) return;
            const viewBtn = row.querySelector('a[title="View/Edit"]');
            if (viewBtn) {
                window.location.href = viewBtn.href;
            }
        });
    });

    // ─── Form submit loading state ──────────────────────────────────
    const submitBtns = document.querySelectorAll('#btn-submit, #btn-save, #btn-reparse');
    submitBtns.forEach(function (btn) {
        const form = btn.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Processing...';
            });
        }
    });

    // ─── Textarea auto-resize ───────────────────────────────────────
    const textareas = document.querySelectorAll('textarea.form-control');
    textareas.forEach(function (ta) {
        ta.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 500) + 'px';
        });
    });

    // ─── Tooltip initialization ─────────────────────────────────────
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (el) {
        new bootstrap.Tooltip(el);
    });

    // ─── Animate numbers on page load ───────────────────────────────
    const kpiValues = document.querySelectorAll('.kpi-value');
    kpiValues.forEach(function (el) {
        const text = el.textContent.trim();
        // Only animate pure numbers
        const num = parseFloat(text.replace(/[₹,%\s]/g, '').replace(/,/g, ''));
        if (!isNaN(num) && num > 0 && num < 1000000) {
            animateValue(el, 0, num, 800, text);
        }
    });
});

/**
 * Animate a numeric value from start to end.
 */
function animateValue(element, start, end, duration, originalText) {
    const prefix = originalText.match(/^[^\d]*/)[0];
    const suffix = originalText.match(/[^\d]*$/)[0];
    const hasDecimal = originalText.includes('.');
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = start + (end - start) * eased;

        if (hasDecimal) {
            element.textContent = prefix + current.toLocaleString('en-IN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }) + suffix;
        } else {
            element.textContent = prefix + Math.round(current).toLocaleString('en-IN') + suffix;
        }

        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            element.textContent = originalText;
        }
    }

    requestAnimationFrame(update);
}
