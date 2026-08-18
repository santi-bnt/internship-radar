export function isAppAccessEnabled(): boolean {
  return process.env.APP_ACCESS_ENABLED?.trim().toLowerCase() === "true";
}

export function isPublicDemoMode(): boolean {
  return (
    process.env.PUBLIC_DEMO_MODE?.trim().toLowerCase() === "true" ||
    process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE?.trim().toLowerCase() === "true"
  );
}
