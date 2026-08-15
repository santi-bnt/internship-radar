export function isAppAccessEnabled(): boolean {
  return process.env.APP_ACCESS_ENABLED?.trim().toLowerCase() === "true";
}
