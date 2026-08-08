import csv
from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")
post = m3d.post

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
data = post.get_solution_data(
    expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
    setup_sweep_name="Setup1 : LastAdaptive",
    context={"Lmatrix": ""},
    primary_sweep_variable="Freq",
)
real, imag = data.full_matrix_real_imag

out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix.csv"
with open(out, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["L (nH)"] + w)
    for wi in w:
        row = [wi]
        for wj in w:
            v = real["L(%s,%s)" % (wi, wj)][0][1]
            row.append("%.4f" % v)
        writer.writerow(row)
    # 单位换算到 uH
    writer.writerow([])
    writer.writerow(["L (uH)"] + w)
    for wi in w:
        row = [wi]
        for wj in w:
            v = real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0
            row.append("%.4f" % v)
        writer.writerow(row)
print("saved:", out)

# 控制台打印 uH 矩阵
print("\nL matrix (uH):")
names = {"Winding_Tx1": "Tx1", "Winding_Tx2": "Tx2", "Winding_Rx": "Rx"}
for wi in w:
    row = []
    for wj in w:
        row.append(real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0)
    print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
