// Auto-size textarea to fit content
(function() {
    'use strict';

    function autosize(textarea) {
        if (!textarea) return;
        
        // Reset height to auto to get the correct scrollHeight
        textarea.style.height = 'auto';
        
        // Set height to scrollHeight, but respect min-height
        const minHeight = parseInt(getComputedStyle(textarea).minHeight, 10) || 38;
        const newHeight = Math.max(textarea.scrollHeight, minHeight);
        textarea.style.height = newHeight + 'px';
    }

    function init() {
        const textareas = document.querySelectorAll('textarea.autosize');
        textareas.forEach(function(textarea) {
            // Initial sizing
            autosize(textarea);
            
            // Resize on input
            textarea.addEventListener('input', function() {
                autosize(this);
            });
            
            // Also handle paste and other changes
            textarea.addEventListener('paste', function() {
                setTimeout(function() { autosize(textarea); }, 0);
            });
        });
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export for dynamic content
    window.autosize = autosize;
})();