function pageNumbers(totalPages, currentPage) {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const pages = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  return [...pages]
    .filter((page) => page > 0 && page <= totalPages)
    .sort((first, second) => first - second)
    .flatMap((page, index, values) => index && page - values[index - 1] > 1 ? [null, page] : [page]);
}

export default function PaginationControls({ page, pageSize, total, onPageChange, onPageSizeChange }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);

  return <nav className="table-pagination" aria-label="Paginazione risultati">
    <label>Mostra<select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select>righe</label>
    <span>{first}-{last} di {total}</span>
    <div><button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Precedente</button>{pageNumbers(totalPages, page).map((entry, index) => entry === null ? <i key={`gap-${index}`}>…</i> : <button type="button" key={entry} className={entry === page ? "active" : ""} aria-current={entry === page ? "page" : undefined} onClick={() => onPageChange(entry)}>{entry}</button>)}<button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Successiva</button></div>
  </nav>;
}
