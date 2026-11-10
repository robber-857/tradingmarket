// Display the approved artwork without redrawing its lettering or star details.
const artwork = '/brand/clarora-approved.png';
export default function BrandMark({className = ''}) {
  return <svg className={className} viewBox="90 463 325 328" aria-hidden="true" focusable="false" style={{borderRadius:'50%', overflow:'hidden'}}>
    <image href={artwork} width="1254" height="1254" />
  </svg>;
}

export function BrandLogo({className = ''}) {
  return <svg className={`brand-artwork ${className}`} viewBox="80 450 1100 390" role="img" aria-label="霁明 Clarora · 云销雨霁，万象澄明。研究有据" focusable="false">
    <image href={artwork} width="1254" height="1254" />
  </svg>;
}
