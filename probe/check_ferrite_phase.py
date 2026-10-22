# -*- coding: utf-8 -*-
"""从 .aedt 里取出 Tx 铁氧体条的实际 x 位置，看两条 Tx 线圈是不是落在条阵列的不同相位上。"""

import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\_test_run\Projecttonight_leadsL.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

bars = {}
i = 0
while i < len(lines):
    s = lines[i].strip()
    m = re.match(r"^Name='(ferrite_(?:Tx|Rx)_\d+)'$", s)
    if m:
        name = m.group(1)
        joined = "".join(lines[i:i + 45])
        if "BoxParameters" in joined:
            def g(k):
                mm = re.search(k + r"='([^']*)'", joined)
                return mm.group(1) if mm else None
            x = g("XPosition")
            xs = g("XSize")
            if x and xs:
                x0 = float(x.replace("mm", ""))
                w = float(xs.replace("mm", ""))
                bars[name] = (x0, x0 + w)
    i += 1

tx = sorted((v for k, v in bars.items() if k.startswith("ferrite_Tx")), key=lambda z: z[0])
rx = sorted((v for k, v in bars.items() if k.startswith("ferrite_Rx")), key=lambda z: z[0])
print("Tx 铁氧体条: %d 根" % len(tx))
if tx:
    print("  x 范围: %.3f ~ %.3f" % (tx[0][0], tx[-1][1]))
    print("  中心: %.3f" % ((tx[0][0] + tx[-1][1]) / 2.0))
    print("  前 4 根:", ["%.2f~%.2f" % b for b in tx[:4]])
    period = None
    if len(tx) > 1:
        period = tx[1][0] - tx[0][0]
        print("  周期(中心距): %.3f mm   条宽 %.3f mm" % (period, tx[0][1] - tx[0][0]))
print("Rx 铁氧体条: %d 根" % len(rx))
if rx:
    print("  x 范围: %.3f ~ %.3f  中心 %.3f"
          % (rx[0][0], rx[-1][1], (rx[0][0] + rx[-1][1]) / 2.0))

# 两个 Tx 线圈的中心（tg=0 时是 +-99.45）
COIL = 198.9
tx1_c = -COIL / 2.0
tx2_c = COIL / 2.0
print("\nTx1 中心 x = %.3f,  Tx2 中心 x = %.3f" % (tx1_c, tx2_c))
if tx and period:
    lo = tx[0][0]
    for nm, c in (("Tx1", tx1_c), ("Tx2", tx2_c)):
        k = (c - lo) / period
        print("  %s 相对条阵列起点偏移 %.3f mm = %.4f 个周期  -> 相位 %.4f"
              % (nm, c - lo, k, k - int(k)))
    print("\n  两个线圈相位差 = %.4f 个周期 = %.3f mm"
          % (abs(((tx2_c - lo) / period) - ((tx1_c - lo) / period)),
             abs(((tx2_c - lo) / period) - ((tx1_c - lo) / period)) * period))
