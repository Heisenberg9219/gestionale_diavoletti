import { useEffect, useState } from "react";
import PaginationControls from "./PaginationControls";

export default function PaginatedRows({ items, resetKey, children }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));

  useEffect(() => { setPage(1); }, [resetKey, pageSize]);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);

  const first = (page - 1) * pageSize;
  return <>{children(items.slice(first, first + pageSize))}<PaginationControls page={page} pageSize={pageSize} total={items.length} onPageChange={setPage} onPageSizeChange={setPageSize} /></>;
}
