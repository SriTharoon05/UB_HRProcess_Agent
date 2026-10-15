import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

const selectors = {
  table: ":scope > table > tbody > tr",
  cards: ":scope > .job-grid > .job-card",
  evidence: ":scope > .evidence-list > *",
};

/** Grow naturally through six records, then scroll at their measured height. */
export function RecordScroll({
  children,
  label,
  layout = "table",
  className = "",
  resetKey,
}: {
  children: ReactNode;
  label: string;
  layout?: keyof typeof selectors;
  className?: string;
  resetKey?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [maxHeight, setMaxHeight] = useState<number>();

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    let active = true;
    let frame = 0;
    let observedContent: Element | null = null;
    let resize: ResizeObserver | undefined;

    function measure() {
      if (!active || !element) return;
      const items = element.querySelectorAll<HTMLElement>(selectors[layout]);
      const sixth = items[5];
      if (items.length <= 6 || !sixth || !sixth.getBoundingClientRect().height) {
        setMaxHeight(undefined);
      } else {
        // Use content coordinates so scrolling does not change the cap. Include
        // any horizontal scrollbar, keeping the sixth record entirely visible.
        const height = Math.ceil(
          sixth.getBoundingClientRect().bottom - element.getBoundingClientRect().top +
          element.scrollTop + element.offsetHeight - element.clientHeight,
        );
        setMaxHeight((previous) => previous === height ? previous : height);
      }
      const content = element.firstElementChild;
      if (content !== observedContent) {
        if (observedContent) resize?.unobserve(observedContent);
        if (content) resize?.observe(content);
        observedContent = content;
      }
    }
    function schedule() {
      if (!active) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    }

    if (typeof ResizeObserver !== "undefined") {
      resize = new ResizeObserver(schedule);
      resize.observe(element);
    }
    const mutation = new MutationObserver(schedule);
    mutation.observe(element, { childList: true, subtree: true, characterData: true });
    window.addEventListener("resize", schedule);
    void document.fonts?.ready.then(schedule);
    measure();
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      resize?.disconnect();
      mutation.disconnect();
      window.removeEventListener("resize", schedule);
    };
  }, [layout]);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0;
  }, [resetKey]);

  return (
    <div
      ref={ref}
      className={`record-scroll ${className}`.trim()}
      style={{ maxHeight }}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      {children}
    </div>
  );
}
