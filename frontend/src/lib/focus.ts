/**
 * `onOpenAutoFocus` for sheets/dialogs that must not focus their first field (it would pop the phone keyboard):
 * keep focus inside the modal by focusing its container instead of leaving it on the now-hidden trigger.
 */
export function focusSheetItself(e: Event): void {
  e.preventDefault();
  const el = e.currentTarget;
  if (el instanceof HTMLElement) el.focus({ preventScroll: true });
}
