import { z } from 'zod';

export const paginationSchema = z.object({
  cursor: z.string().optional(),
  limit: z.coerce.number().int().min(1).max(100).default(25),
});

export type PaginationParams = z.infer<typeof paginationSchema>;

export interface PaginatedResult<T> {
  data: T[];
  pagination: {
    next_cursor: string | null;
    has_more: boolean;
    count: number;
  };
}

export function buildCursorResponse<T extends { id: number }>(
  rows: T[],
  limit: number
): PaginatedResult<T> {
  const hasMore = rows.length > limit;
  const data = hasMore ? rows.slice(0, limit) : rows;
  const nextCursor = hasMore ? String(data[data.length - 1].id) : null;

  return {
    data,
    pagination: {
      next_cursor: nextCursor,
      has_more: hasMore,
      count: data.length,
    },
  };
}
