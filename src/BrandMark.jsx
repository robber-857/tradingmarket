// Open cloud, rising light: shared by navigation and footer.
export default function BrandMark({className = ''}) {
  return <svg className={className} viewBox="0 0 40 40" fill="none" aria-hidden="true" focusable="false">
    <path d="M15 21a8 8 0 1 1 15 0M23 5v2M34 11l-2 2" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    <path d="M28 27H11a5 5 0 1 1 1-9 7 7 0 0 1 12 3h7a3 3 0 0 1 0 6M12 33h16" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
