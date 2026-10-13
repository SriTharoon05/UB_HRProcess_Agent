export function returnPath(value: unknown, hr = false): string | null {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    // eslint-disable-next-line no-control-regex -- Reject controls in redirect URLs.
    /[\x00-\x20\x7f\\]/.test(value)
  ) return null;
  try {
    const decoded = decodeURIComponent(value.split(/[?#]/, 1)[0]);
    const parsed = new URL(value, "https://portal.invalid");
    if (
      parsed.origin !== "https://portal.invalid" ||
      // eslint-disable-next-line no-control-regex -- Encoded controls are unsafe too.
      /[\x00-\x1f\x7f\\]/.test(decoded) ||
      decoded.includes("//") ||
      decoded.split("/").some((part) => part === "." || part === "..")
    ) return null;
    const allowed = hr
      ? /^\/hr(?:\/jobs(?:\/[^/]+(?:\/candidates(?:\/[^/]+)?)?)?)?$/.test(decoded)
      : /^(?:\/|\/jobs(?:\/[^/]+(?:\/apply)?)?|\/candidate\/applications(?:\/[^/]+)?)$/.test(decoded);
    return allowed ? value : null;
  } catch {
    return null;
  }
}

export function signInHref(hr = false, destination?: unknown): string {
  const path = hr ? "/auth/hr/login" : "/auth/linkedin/login";
  const target = returnPath(destination, hr);
  return target ? `${path}?return_to=${encodeURIComponent(target)}` : path;
}
