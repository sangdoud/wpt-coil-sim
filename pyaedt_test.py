from pyaedt import Desktop

if __name__ == "__main__":
    try:
        d = Desktop(version="241", non_graphical=False, new_desktop=False)
        print("Connect AEDT success, version:", d.aedt_version_id)
        print("Ready for maxwell simulation")
        d.release_desktop(False, False)
    except Exception as e:
        print("Connect failed:", e)
        print("Tips: Please open AEDT2024R1 first and wait for ready status")