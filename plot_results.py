import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv(r"C:/Users/lenovo/Desktop/zidong/scan_RxX.csv")

# 图1: 耦合系数 k 随位置变化
plt.figure(figsize=(9, 5))
plt.plot(df["dx_mm"], df["k13"], "-o", label="k13 (Tx1-Rx)", linewidth=2)
plt.plot(df["dx_mm"], df["k23"], "-s", label="k23 (Tx2-Rx)", linewidth=2)
plt.axhline(0, color="gray", lw=0.8)
plt.xlabel("Rx X offset (mm)", fontsize=12)
plt.ylabel("Coupling coefficient k", fontsize=12)
plt.title("Rx \u6cbf X \u79fb\u52a8\u65f6\u7684\u8026\u5408\u7cfb\u6570 (\u03bcr=300)", fontsize=13)
plt.legend(fontsize=11)
plt.grid(True, alpha=0.4)
plt.tight_layout()
plt.savefig(r"C:/Users/lenovo/Desktop/zidong/scan_RxX_k.png", dpi=150)
plt.close()

# 图2: 互感 M 随位置变化
plt.figure(figsize=(9, 5))
plt.plot(df["dx_mm"], df["M13_uH"], "-o", label="M13 (Tx1-Rx)", linewidth=2)
plt.plot(df["dx_mm"], df["M23_uH"], "-s", label="M23 (Tx2-Rx)", linewidth=2)
plt.axhline(0, color="gray", lw=0.8)
plt.xlabel("Rx X offset (mm)", fontsize=12)
plt.ylabel("Mutual inductance (uH)", fontsize=12)
plt.title("Rx \u6cbf X \u79fb\u52a8\u65f6\u7684\u4e92\u611f (\u03bcr=300)", fontsize=13)
plt.legend(fontsize=11)
plt.grid(True, alpha=0.4)
plt.tight_layout()
plt.savefig(r"C:/Users/lenovo/Desktop/zidong/scan_RxX_M.png", dpi=150)
plt.close()

print("PNG saved: scan_RxX_k.png, scan_RxX_M.png")
