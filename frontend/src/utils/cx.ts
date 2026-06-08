/**
 * cx — tiny classnames helper for conditional Tailwind composition.
 *
 * Joins truthy class strings with a space, filtering out falsy values
 * (false, undefined, null, empty strings). Useful for conditional
 * classNames without pulling in a dependency.
 *
 * Example:
 *   cx("base", condition && "conditional", "always")
 *   // → "base conditional always" if condition is truthy
 *   // → "base always" if condition is falsy
 */
export function cx(...parts: Array<string | false | undefined | null>): string {
  return parts.filter(Boolean).join(" ");
}
