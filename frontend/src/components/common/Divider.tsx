import React from "react";

export interface DividerProps {
  className?: string;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Divider({ className }: DividerProps) {
  return <hr className={cx("border-0 border-t border-rule my-6", className)} />;
}

export default Divider;
