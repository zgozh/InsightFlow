"""生成原创颗粒矢量背景；固定种子使静态资产可复现。"""

import math
import random
from pathlib import Path

random.seed(21)
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">'
    '<defs><radialGradient id="space"><stop stop-color="#30201b"/><stop offset=".5" stop-color="#101017"/>'
    '<stop offset="1" stop-color="#05060a"/></radialGradient><radialGradient id="halo">'
    '<stop stop-color="#ffa455" stop-opacity=".18"/><stop offset=".5" stop-color="#a93d19" stop-opacity=".14"/>'
    '<stop offset="1" stop-color="#703018" stop-opacity="0"/></radialGradient><filter id="glow">'
    '<feGaussianBlur stdDeviation="9"/></filter></defs><rect width="1600" height="1000" fill="url(#space)"/>'
    '<ellipse cx="1100" cy="510" rx="750" ry="490" fill="url(#halo)"/>'
]


def dot(x, y, radius, color, opacity):
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" fill="{color}" opacity="{opacity:.2f}"/>')


for _ in range(900):
    dot(random.uniform(0, 1600), random.uniform(0, 1000), random.uniform(0.3, 1.15), "#d2d4e0", random.uniform(0.05, 0.45))
parts.append('<g transform="translate(1100 510) rotate(-16.6)">')
parts.append('<ellipse rx="510" ry="133" fill="none" stroke="#ff8b32" stroke-width="34" opacity=".12" filter="url(#glow)"/>')
for radius in range(165, 470, 4):
    opacity = 0.18 * (1 - (radius - 165) / 400)
    parts.append(f'<ellipse rx="{radius}" ry="{radius * 0.25}" fill="none" stroke="#ffb45d" stroke-width=".65" opacity="{opacity:.2f}"/>')


def disk(front):
    for _ in range(8500 if not front else 6500):
        radius = 155 + random.random() ** 1.7 * 540
        angle = random.uniform(0, math.pi) if front else random.uniform(math.pi, math.pi * 2)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius * 0.25
        y += random.gauss(0, 3 + (radius - 155) * 0.014)
        heat = 1 - (radius - 155) / 540
        turbulence = 0.6 + 0.4 * math.sin(radius * 0.13 + angle * 9) ** 2
        color = random.choice(["#ffe6af", "#ffbd67", "#f98b37"]) if heat > 0.65 else random.choice(["#d96931", "#9c4229", "#ec8d46"])
        dot(x, y, random.uniform(0.4, 1.35), color, (0.22 + heat * 0.78) * turbulence * (0.65 + 0.35 * (1 - math.cos(angle)) / 2))


disk(False)
parts.append('<path d="M -145 0 A 145 154 0 0 1 145 0" fill="none" stroke="#ffc070" stroke-width="15" opacity=".3" filter="url(#glow)"/>')
for radius in range(134, 184, 2):
    parts.append(f'<path d="M {-radius} 0 A {radius} {radius * 1.08} 0 0 1 {radius} 0" fill="none" stroke="#ffd49a" stroke-width=".65" opacity="{0.3 * (1 - (radius - 134) / 60):.2f}"/>')
# 背侧盘通过透镜映成上方弧；纯艺术投影，不声称物理光线追踪。
for _ in range(6500):
    angle = random.uniform(math.pi, 2 * math.pi)
    radius = 132 + random.random() ** 2 * 76
    x, y = math.cos(angle) * radius, math.sin(angle) * radius * 1.08
    dot(x, y, random.uniform(0.3, 1), random.choice(["#ffeac4", "#ffc274", "#ed8239"]), random.uniform(0.15, 0.75) * (1 - (radius - 132) / 100))
parts.append('<circle r="132" fill="#030407"/><circle r="133" fill="none" stroke="#ffbd70" stroke-width="1.2" opacity=".65"/>')
disk(True)
for radius in range(165, 460, 4):
    parts.append(f'<path d="M {-radius} 0 A {radius} {radius * 0.25} 0 0 0 {radius} 0" fill="none" stroke="#ffd087" stroke-width=".65" opacity="{0.25 * (1 - (radius - 165) / 400):.2f}"/>')
for _ in range(1400):
    angle = random.uniform(0, math.pi * 2)
    radius = random.uniform(400, 1100)
    dot(math.cos(angle) * radius, math.sin(angle) * radius * 0.28 + random.gauss(0, 25), random.uniform(0.3, 0.8), "#d78b60", random.uniform(0.03, 0.22))
parts.append("</g></svg>")
Path(__file__).resolve().parents[1].joinpath("public/images/black-hole-scene.svg").write_text("".join(parts), encoding="utf-8")
