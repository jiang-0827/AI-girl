# -*- coding: utf-8 -*-
"""一次性脚本：把项目代码从 PyQt5 迁移到 PySide6（仅改 import/信号/exec_）"""
import os
import re

ROOT = r"E:\DesktopPetAI"
SKIP = {'venv', '.git', '__pycache__', 'node_modules', '.webpack', 'out',
        'release', 'aigirl-desktop-pet', '.pip-cache'}

changed = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    for fn in filenames:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(dirpath, fn)
        try:
            with open(p, 'r', encoding='utf-8') as f:
                src = f.read()
        except Exception as e:
            print('SKIP', p, e)
            continue
        orig = src
        src = src.replace('from PySide6.', 'from PySide6.')
        src = src.replace('import PySide6.', 'import PySide6.')
        src = src.replace('Signal', 'Signal')
        src = src.replace('Slot', 'Slot')
        src = re.sub(r'\.exec_\(', '.exec(', src)
        if src != orig:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(src)
            changed.append(p)

print('changed files: %d' % len(changed))
for c in changed:
    print(' ', c)
