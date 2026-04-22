import { useEffect } from "react";

/**
 * Sets document.title for the current route. Restores the previous
 * title on unmount so route transitions feel clean.
 */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
