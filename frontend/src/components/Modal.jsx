import React, { useEffect, useRef } from 'react';

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Accessible modal shell: role="dialog", aria-modal, labelled by `labelId`,
 * Escape closes, Tab/Shift+Tab are trapped inside, and focus returns to the
 * element that opened it. Children render inside the dialog node.
 */
const Modal = ({ labelId, onClose, className = '', children }) => {
    const ref = useRef(null);
    const closeRef = useRef(onClose);
    useEffect(() => { closeRef.current = onClose; });

    useEffect(() => {
        const opener = document.activeElement;
        const node = ref.current;
        (node.querySelector(FOCUSABLE) || node).focus();

        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                closeRef.current();
                return;
            }
            if (e.key !== 'Tab') return;
            const items = [...node.querySelectorAll(FOCUSABLE)];
            if (items.length === 0) { e.preventDefault(); return; }
            const first = items[0];
            const last = items[items.length - 1];
            if (e.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
                e.preventDefault(); first.focus();
            }
        };
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('keydown', onKey);
            if (opener && opener.focus) opener.focus();
        };
    }, []);

    return (
        <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={labelId} tabIndex={-1} className={className}>
            {children}
        </div>
    );
};

export default Modal;
