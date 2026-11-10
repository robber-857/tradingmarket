import { useId, useRef, useEffect } from 'react';
import { CircleHelp } from 'lucide-react';

// Native popovers use the top layer, so table overflow never clips the help.
export default function FieldHelp({ label, children }) {
  const id = useId();
  const trigger = useRef(null);
  const popup = useRef(null);
  const pinned = useRef(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  function show() {
    clearTimeout(timer.current);
    const rect = trigger.current.getBoundingClientRect();
    const el = popup.current;
    el.showPopover();
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    el.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
    el.style.top = `${Math.max(8, rect.bottom + height + 8 <= window.innerHeight ? rect.bottom + 6 : rect.top - height - 6)}px`;
  }
  function leave() {
    timer.current = setTimeout(() => { if (!pinned.current) popup.current?.hidePopover(); }, 150);
  }
  return <>
    <button ref={trigger} type="button" className="field-help-button" aria-label={`${label}说明`} aria-describedby={id}
      onMouseEnter={show} onMouseLeave={leave} onFocus={show}
      onBlur={() => { pinned.current = false; leave(); }}
      onClick={() => { if (pinned.current) { pinned.current = false; popup.current.hidePopover(); } else { show(); pinned.current = true; } }}>
      <CircleHelp size={14} aria-hidden="true" />
    </button>
    <span ref={popup} id={id} popover="auto" role="tooltip" className="field-help-popup"
      onToggle={e => { if (e.newState === 'closed') pinned.current = false; }}
      onMouseEnter={() => clearTimeout(timer.current)} onMouseLeave={leave}>
      <strong>{label}</strong><span>{children}</span>
    </span>
  </>;
}
