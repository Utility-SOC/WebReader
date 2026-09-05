import { useEffect, useRef } from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Traps Tab focus inside a dialog, closes it on Escape, and restores focus to
// whatever triggered it on unmount -- the three behaviors WCAG 2.1 AA expects
// from any modal (2.1.2 No Keyboard Trap works both ways: trapped while open,
// released on close).
export default function useDialogA11y(containerRef, onClose) {
  const triggerRef = useRef(null);

  useEffect(() => {
    triggerRef.current = document.activeElement;

    const container = containerRef.current;
    const focusables = container
      ? Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR))
      : [];
    (focusables[0] || container)?.focus();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !container) return;

      const nodes = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR));
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      triggerRef.current?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);
}
