# setuptools and Python packaging

## What it is

**Packaging** means turning a folder of Python code into something that `pip` can install: a **package** with a name, a version and a list of the other packages it needs. **setuptools** is the long-standing tool that does the building. In a modern project it is only named in `pyproject.toml`; you do not run it yourself, `pip` runs it for you.

## Why this repository uses it

The code is a real package called `slow_queries`, installed into the virtual environment. That is what allows `python -m slow_queries.interfaces.run_cli`, the two commands `slow-queries-run` and `slow-queries-health`, and tests that `import slow_queries.domain.plan` from any folder.

## Where it appears

| File or folder | What it does with packaging |
|---|---|
| `pyproject.toml` | `[build-system]`, `[project]`, `[project.scripts]` and `[tool.setuptools.packages.find]`. |
| `src/slow_queries/` and its sub-folders | The package. Each folder has an `__init__.py` with a one-line docstring. |
| `Makefile` | Line 25 installs the package in editable mode. |
| `Dockerfile` | Line 18 installs a regular (non-editable) copy. |

## How it works underneath

**Module and package.** A `.py` file is a **module**. A folder of modules that contains an `__init__.py` file is a **package**. You use them with `import slow_queries.domain.plan`; Python finds `slow_queries` by looking through the folders in a list called `sys.path`.

**Installing makes a package importable everywhere.** Without installation, `import slow_queries` only works when your current folder happens to contain it. `pip install` copies the package into the `site-packages` folder of the Python environment (inside `.venv/lib/python3.x/site-packages`), which is always on `sys.path`.

**Editable install** (`pip install -e .`). Instead of copying the files, pip leaves a small link file in `site-packages` that points back to the source folder, so changes to the code take effect at once.

**The build.** `pip install .` reads `[build-system]`: it first installs the listed `requires` into a temporary place, then asks the `build-backend` to produce a **wheel** (a `.whl` file, which is a zip of the files to install plus metadata). It installs the wheel. The metadata (name, version, dependencies, entry points) comes from `[project]`.

**src layout.** Putting the package in `src/` (not at the top level) forces tests to import the installed copy. That catches mistakes like a missing file in the package.

**Entry points.** `[project.scripts]` lines become small launcher programs placed in the environment's `bin/` folder; they import the named module and call the function.

**Package data.** Files that are not `.py` need extra configuration to be included in a wheel. This repository does not need that: the SQL files are read from the project folder, not from inside the installed package.

## Walkthrough of this repository's use

### The tree

```text
src/slow_queries/
├── __init__.py          the package; holds __version__
├── domain/              pure rules  (plan.py, write_cost.py, comparison.py, lesson.py, host.py, errors.py)
├── application/         use cases   (replay.py, report.py, health.py, ports.py)
├── infrastructure/      adapters    (lab_database.py, postgres.py, sql_script.py, artifacts.py, ...)
└── interfaces/          commands    (run_cli.py, health_cli.py, common.py)
```

`src/slow_queries/__init__.py`, lines 1 to 3:

```python
"""Three slow queries: read plans with real timings, change one thing, prove it with a before-and-after plan."""

__version__ = "0.1.0"
```

The package's own `__init__.py` is two statements: a docstring describing the lesson, and the variable `__version__ = "0.1.0"`, which matches `version` in `pyproject.toml`. The other `__init__.py` files contain only a one-line docstring, which also satisfies the docstring rule `D104` in ruff.

### Editable install in the Makefile

`Makefile`, lines 22 to 26:

```make
$(STAMP): requirements-dev.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --require-hashes -r requirements-dev.lock
	$(VENV)/bin/pip install -q --no-deps -e .
	touch $@
```

Line 25, `$(VENV)/bin/pip install -q --no-deps -e .`, reads `pyproject.toml` in the current folder (`.`), builds an *editable* install (`-e`) and skips dependencies (`--no-deps`), because line 24 already installed all of them from the lock file. After this line `import slow_queries` works inside `.venv` and points at `src/slow_queries`.

### Regular install in the Dockerfile

`Dockerfile`, lines 15 to 18:

```dockerfile
COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
RUN pip install --no-deps .
```

In the image there is no reason to edit code, so `pip install --no-deps .` builds a wheel from the copied files and installs it. `COPY pyproject.toml README.md ./` copies exactly what the build needs, and `COPY src ./src` the package.

### Why `src`

`pyproject.toml`, lines 29 to 30:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

With `where = ["src"]`, `find` looks for packages inside `src`. The pytest configuration adds nothing like `pythonpath`; tests import the *installed* editable package.

### Launchers

`pyproject.toml`, lines 25 to 27:

```toml
[project.scripts]
slow-queries-run = "slow_queries.interfaces.run_cli:main"
slow-queries-health = "slow_queries.interfaces.health_cli:main"
```

Installing writes two files into `.venv/bin/`. Each is a small Python script that imports `slow_queries.interfaces.run_cli` (or `health_cli`) and runs `main()`, then exits with the number that `main` returned, which is how the exit codes (0, 1, 2, 130) reach the shell.

## Try it yourself

1. `.venv/bin/python -c "import slow_queries; print(slow_queries.__version__, slow_queries.__file__)"` prints `0.1.0` and a path ending in `src/slow_queries/__init__.py`: the editable install points at the source folder.
2. `cat .venv/bin/slow-queries-run` shows the tiny launcher script that was generated.
3. `.venv/bin/pip list | grep sql-optimization` shows the project itself among the installed packages.
4. `cd /tmp && /path/to/this/repo/.venv/bin/python -c "import slow_queries"` still works from any folder, because it is installed (replace the path with your own).

## Mistakes people make

- Running a script from the wrong folder and importing the source copy by accident.
- Forgetting `__init__.py` (it has a different meaning in "namespace packages", but a plain package needs it).
- Changing `[project.scripts]` and forgetting to reinstall: the launcher programs are created at install time.
- Using `python setup.py install`, which is deprecated.
- Listing dependencies in two places (a hand-written `requirements.txt` and `pyproject.toml`).

**How this repository avoids them.** Every folder in the package has an `__init__.py`. The `src` layout means tests cannot import by accident from the project root. The launchers are generated at install time, and `make install` is rerun automatically by the stamp rule when `pyproject.toml` changes. There is a single list of dependencies, in `pyproject.toml`; the lock files are generated from it, not written by hand.

## Check yourself

1. What is the difference between a module and a package? *A module is one `.py` file; a package is a folder of modules with an `__init__.py`.*
2. What does `pip install -e .` do differently from `pip install .`? *It installs a link to the source folder instead of a copy, so edits apply without reinstalling.*
3. What is a wheel? *A zip-format file holding the files to install and the package metadata.*
4. Why is the code under `src/`? *So that tests and tools import the installed package, not the folder they happen to be in.*
5. Where does `[project.scripts]` put its programs? *In the `bin/` folder of the Python environment where the package is installed.*

## Further reading

- setuptools documentation, "Build System Support" and "Configuring setuptools using pyproject.toml": https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html (this repository requires `setuptools>=75`).
- PyPA packaging user guide, "src layout vs flat layout": https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- Python tutorial on modules and packages: https://docs.python.org/3/tutorial/modules.html
