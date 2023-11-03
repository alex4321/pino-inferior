if __name__ == "__main__":
    import os
    os.uname = lambda: ("Windows 10", "", "", "", "")
    import nbdev.quarto
    nbdev.quarto.nbdev_docs()