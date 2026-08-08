from ansys.aedt.core import Desktop

# 启动新的 AEDT 会话（v241，带 GUI）
d = Desktop(version="2024.1", new_desktop=True, non_graphical=False,
            close_on_exit=False)
print("AEDT started", flush=True)
try:
    print("projects:", d.project_list, flush=True)
except Exception as e:
    print("proj err:", repr(e), flush=True)
print("DONE", flush=True)
