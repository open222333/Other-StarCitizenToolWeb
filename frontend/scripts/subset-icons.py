"""產生 bootstrap-icons 子集（待辦 2-5）：只留前端程式碼裡真的用到的圖示。

整套約 2000 個圖示（woff2 134 kB＋woff 180 kB），網站只用到一百多個。這支程式：
  1. 掃 frontend/src 底下所有 .vue／.js 裡出現的 `bi-<名稱>`，對照 bootstrap-icons.json 留下真的存在的
  2. 用 fonttools 把 woff2 切成只有這些字的子集 → src/assets/icons/bootstrap-icons-subset.woff2
  3. 寫對應的 CSS（只有 woff2，現在的瀏覽器都吃）→ src/assets/icons/bootstrap-icons-subset.css

新增圖示後要重跑（npm run icons）；忘了跑的話 `npm test` 的 icons.test.mjs 會列出缺哪些。
需要：pip install fonttools brotli
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
PKG = ROOT / 'node_modules' / 'bootstrap-icons' / 'font'
OUT = SRC / 'assets' / 'icons'
NAME_RE = re.compile(r'\bbi-([a-z0-9]+(?:-[a-z0-9]+)*)')


def used_icons(codepoints: dict) -> list:
    names = set()
    for f in SRC.rglob('*'):
        if f.suffix in ('.vue', '.js', '.mjs') and 'assets/icons' not in str(f):
            names.update(NAME_RE.findall(f.read_text(encoding='utf-8')))
    return sorted(n for n in names if n in codepoints)


def main() -> int:
    codepoints = json.loads((PKG / 'bootstrap-icons.json').read_text())
    names = used_icons(codepoints)
    OUT.mkdir(parents=True, exist_ok=True)
    font = OUT / 'bootstrap-icons-subset.woff2'
    unicodes = ','.join(f'U+{codepoints[n]:04X}' for n in names)
    subprocess.run([sys.executable, '-m', 'fontTools.subset', str(PKG / 'fonts' / 'bootstrap-icons.woff2'),
                    f'--unicodes={unicodes}', '--flavor=woff2', f'--output-file={font}',
                    '--layout-features=', '--no-hinting', '--desubroutinize'], check=True)
    version = re.search(r'Bootstrap Icons v([\d.]+)', (PKG / 'bootstrap-icons.css').read_text()).group(1)
    rules = '\n'.join(f'.bi-{n}::before {{ content: "\\{codepoints[n]:x}"; }}' for n in names)
    css = f'''/*!
 * Bootstrap Icons v{version} 子集（{len(names)} 個，frontend/scripts/subset-icons.py 產生，不要手改）
 * Copyright 2019-2024 The Bootstrap Authors
 * Licensed under MIT (https://github.com/twbs/icons/blob/main/LICENSE)
 */

@font-face {{
  font-display: block;
  font-family: "bootstrap-icons";
  src: url("./bootstrap-icons-subset.woff2") format("woff2");
}}

.bi::before,
[class^="bi-"]::before,
[class*=" bi-"]::before {{
  display: inline-block;
  font-family: bootstrap-icons !important;
  font-style: normal;
  font-weight: normal !important;
  font-variant: normal;
  text-transform: none;
  line-height: 1;
  vertical-align: -.125em;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}

{rules}
'''
    (OUT / 'bootstrap-icons-subset.css').write_text(css, encoding='utf-8')
    print(f'{len(names)} 個圖示，字型 {font.stat().st_size / 1024:.1f} kB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
