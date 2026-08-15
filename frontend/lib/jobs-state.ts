export type PaginatedItems<T> = {
  items: T[];
  total: number;
};

export function removeItemOptimistically<
  T extends { id: number },
  TPage extends PaginatedItems<T>,
>(
  current: TPage,
  itemId: number,
): TPage {
  if (!current.items.some((item) => item.id === itemId)) return current;
  return {
    ...current,
    items: current.items.filter((item) => item.id !== itemId),
    total: Math.max(0, current.total - 1),
  } as TPage;
}
