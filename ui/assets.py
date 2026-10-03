"""Original SVG illustrations (pastel), embedded as data URIs - no external images."""

import base64

_BG = '<circle cx="100" cy="82" r="70" fill="#F1EFEA" opacity="0.75"/>'
_SPARKLES = (
    '<path d="M0 -8 L2.2 -2.2 L8 0 L2.2 2.2 L0 8 L-2.2 2.2 L-8 0 L-2.2 -2.2 Z" transform="translate(40 26)" fill="#C9B79C"/>'
    '<path d="M0 -6 L1.7 -1.7 L6 0 L1.7 1.7 L0 6 L-1.7 1.7 L-6 0 L-1.7 -1.7 Z" transform="translate(172 40)" fill="#B8C9BE"/>'
    '<path d="M0 -5 L1.4 -1.4 L5 0 L1.4 1.4 L0 5 L-1.4 1.4 L-5 0 L-1.4 -1.4 Z" transform="translate(28 124)" fill="#B9C3D3"/>'
)

_ART = {
    "docs": """
<g transform="rotate(-9 80 80)"><rect x="38" y="32" width="80" height="100" rx="12" fill="#F7F4EE" stroke="#E3DACB"/>
<rect x="50" y="50" width="40" height="5" rx="2.5" fill="#D3C7B3"/><rect x="50" y="62" width="54" height="5" rx="2.5" fill="#E1D8C8"/>
<rect x="50" y="74" width="48" height="5" rx="2.5" fill="#E1D8C8"/></g>
<rect x="70" y="24" width="80" height="104" rx="12" fill="#fff" stroke="#E2DED6"/>
<rect x="82" y="40" width="44" height="8" rx="4" fill="#2A2F45" opacity="0.8"/>
<rect x="82" y="56" width="56" height="5" rx="2.5" fill="#D9D6CF"/><rect x="82" y="67" width="50" height="5" rx="2.5" fill="#D9D6CF"/>
<rect x="82" y="78" width="54" height="5" rx="2.5" fill="#D9D6CF"/><rect x="82" y="96" width="30" height="13" rx="6.5" fill="#E7EFE9"/>
<circle cx="142" cy="104" r="20" fill="#EBEFF5" stroke="#2A2F45" stroke-width="4"/>
<line x1="156" y1="118" x2="172" y2="134" stroke="#2A2F45" stroke-width="6" stroke-linecap="round"/>""",
    "chat": """
<rect x="30" y="34" width="100" height="54" rx="18" fill="#fff" stroke="#E2DED6"/>
<path d="M50 87 L44 104 L66 87 Z" fill="#fff" stroke="#E2DED6" stroke-linejoin="round"/>
<rect x="46" y="50" width="62" height="6" rx="3" fill="#D9D6CF"/><rect x="46" y="63" width="44" height="6" rx="3" fill="#D9D6CF"/>
<rect x="80" y="76" width="92" height="48" rx="18" fill="#2A2F45"/>
<path d="M150 123 L160 138 L136 123 Z" fill="#2A2F45"/>
<rect x="95" y="91" width="60" height="6" rx="3" fill="#fff" opacity="0.9"/><rect x="95" y="103" width="40" height="6" rx="3" fill="#fff" opacity="0.6"/>""",
    "scales": """
<rect x="97" y="40" width="6" height="84" rx="3" fill="#2A2F45"/><rect x="70" y="122" width="60" height="8" rx="4" fill="#2A2F45"/>
<rect x="42" y="44" width="116" height="5" rx="2.5" fill="#2A2F45"/><circle cx="100" cy="40" r="7" fill="#C9B79C"/>
<line x1="50" y1="49" x2="34" y2="88" stroke="#C9C4BA" stroke-width="2"/><line x1="50" y1="49" x2="66" y2="88" stroke="#C9C4BA" stroke-width="2"/>
<path d="M28 88 Q50 108 72 88 Z" fill="#F3EEE6" stroke="#C9B79C" stroke-width="1.5"/>
<line x1="150" y1="49" x2="134" y2="88" stroke="#C9C4BA" stroke-width="2"/><line x1="150" y1="49" x2="166" y2="88" stroke="#C9C4BA" stroke-width="2"/>
<path d="M128 88 Q150 108 172 88 Z" fill="#E7EFE9" stroke="#9FB8A8" stroke-width="1.5"/>""",
    "checklist": """
<rect x="58" y="28" width="84" height="108" rx="12" fill="#fff" stroke="#E2DED6"/>
<rect x="83" y="20" width="34" height="15" rx="7" fill="#2A2F45"/>
<circle cx="78" cy="58" r="8" fill="#E7EFE9"/><path d="M74 58 l3 3 l6 -6" stroke="#4F6F5F" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="93" y="55" width="36" height="6" rx="3" fill="#D9D6CF"/>
<circle cx="78" cy="84" r="8" fill="#E7EFE9"/><path d="M74 84 l3 3 l6 -6" stroke="#4F6F5F" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="93" y="81" width="30" height="6" rx="3" fill="#D9D6CF"/>
<circle cx="78" cy="110" r="8" fill="#F6ECEE"/><path d="M75 107 l6 6 M81 107 l-6 6" stroke="#8C4F5C" stroke-width="2.4" stroke-linecap="round"/>
<rect x="93" y="107" width="34" height="6" rx="3" fill="#D9D6CF"/>""",
    "chart": """
<rect x="38" y="34" width="124" height="94" rx="14" fill="#fff" stroke="#E2DED6"/>
<rect x="56" y="94" width="16" height="20" rx="4" fill="#E7EFE9"/><rect x="80" y="78" width="16" height="36" rx="4" fill="#EBEFF5"/>
<rect x="104" y="62" width="16" height="52" rx="4" fill="#F1EFEA" stroke="#C9C4BA"/><rect x="128" y="84" width="16" height="30" rx="4" fill="#F3EEE6"/>
<polyline points="64,86 88,70 112,54 136,76" fill="none" stroke="#2A2F45" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="112" cy="54" r="4" fill="#2A2F45"/>
<circle cx="164" cy="34" r="13" fill="#F3EEE6" stroke="#C9B79C" stroke-width="2"/>
<text x="164" y="39.5" text-anchor="middle" font-size="15" font-family="sans-serif" font-weight="700" fill="#7A6A55">$</text>""",
}


def art(name: str) -> str:
    """Data URI for an illustration: 'docs', 'chat', 'scales', 'checklist' or 'chart'."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 160">{_BG}'
        f"{_ART[name]}{_SPARKLES}</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
