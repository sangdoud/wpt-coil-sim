from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")
post = m3d.post

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
setup = "Setup1 : LastAdaptive"

for i, wi in enumerate(w):
    row = []
    for j, wj in enumerate(w):
        expr = "L(%s,%s)" % (wi, wj)
        try:
            data = post.get_solution_data(
                expressions=expr,
                setup_sweep_name=setup,
                context={"Lmatrix": ""},
                primary_sweep_variable="Freq",
            )
            if data:
                r = data.data_real
                im = data.data_imag
                row.append((expr, r, im))
                print("%s: real=%s imag=%s" % (expr, r, im))
            else:
                row.append((expr, None, None))
                print("%s: no data" % expr)
        except Exception as e:
            row.append((expr, None, None))
            print("%s err: %s" % (expr, repr(e)))
