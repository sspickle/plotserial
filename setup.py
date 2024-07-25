from cx_Freeze import setup, Executable

setup(
    name="PyPlotter",
    version="1.0.0",
    description="Generic Serial Plotter",
    options={"build_exe": {"include_files": ["image.png"]}},
    executables=[Executable("graph.py")]
)
