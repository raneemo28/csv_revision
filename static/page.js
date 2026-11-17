// Revision page helpers: jump-to-page dropdown and a warning before leaving with unsaved edits.
(function () {
    'use strict';

    var form = document.getElementById('page-form');
    var select = document.getElementById('page-select');
    var dirty = false;
    var submitting = false;

    if (form) {
        form.addEventListener('input', function () { dirty = true; });
        form.addEventListener('submit', function () { submitting = true; });
        window.addEventListener('beforeunload', function (e) {
            if (dirty && !submitting) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
    }

    if (select) {
        select.addEventListener('change', function () {
            window.location.href = select.dataset.base + '?page=' + encodeURIComponent(select.value);
        });
    }
})();
