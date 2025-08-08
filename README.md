# resource-tracker

A lightweight, zero-dependency Python package for monitoring resource usage
across processes and at the system level. Designed with batch jobs in mind (like
Python or R scripts, or Metaflow steps), it provides simple tools to track CPU,
memory, GPU, network, and disk utilization with minimal setup -- e.g. using a
step decorator in Metaflow to automatically track resource usage and generate a
card with data visualizations on historical resource usage and cloud server
recommendations for future runs.

## Installation

You can install the stable version of the package from PyPI:
[![resource-tracker on PyPI](https://img.shields.io/pypi/v/resource-tracker?color=%2332C955)](https://pypi.org/project/resource-tracker/)

```sh
pip install resource-tracker
```

Development version can be installed directly from the git repository:

```sh
pip install git+https://github.com/sparecores/resource-tracker.git
```

Note that depending on your operating system, you might need to also install
`psutil` (e.g. on MacOS and Windows). For more details, see the
[OS support section](#operating-system-support).

## Integrations

The `resource-tracker` Python package is designed to be used in a variety of
ways, even outside of Python. Find more details about how to use it directly
from Python, R, or via our framework integrations, such as Metaflow, in the
[integrations](https://sparecores.github.io/resource-tracker/integrations/)
section of the documentation.

## Operating System Support

The package was originally created to work on Linux systems (as the most
commonly used operating system on cloud servers) using `procfs` directly and
without requiring any further Python dependencies, but to support other
operating systems as well, now it can also use `psutil` when available.

To make sure the resource tracker works on non-Linux systems, install via:

```sh
pip install resource-tracker[psutil]
```

Minor inconsistencies between operating systems are expected, e.g. using PSS
(Proportional Set Size) instead of RSS (Resident Set Size) as the process-level
memory usage metric on Linux, as it is evenly divides the shared memory usage
between the processes using it, making it more representative of the memory
usage of the monitored applications. Mac OS X and Windows use USS (Unique Set
Size) instead.

CI/CD is set up to run tests on the below operating systems:

- Ubuntu latest LTS (24.04)
- MacOS latest (13)
- Windows latest (Windows Server 2022)

[![Unit tests status for each operating system](https://github-actions.40ants.com/spareCores/resource-tracker/matrix.svg?only=Unit%20tests)](https://github.com/SpareCores/resource-tracker/actions/workflows/tests.yaml)

## Python Version Support

The package supports Python 3.9 and above.

CI/CD is set up to run tests on the below Python versions on Ubuntu latest LTS, Windows Server 2022 and MacOS latest:

- 3.9
- 3.10
- 3.11
- 3.12
- 3.13

[![Unit tests status per Python version](https://github-actions.40ants.com/spareCores/resource-tracker/matrix.svg?only=Unit%20tests.pytest.ubuntu-latest)](https://github.com/SpareCores/resource-tracker/actions/workflows/tests.yaml)

## Performance

The performance of the `procfs` and the `psutil` implementations is similar, see
e.g.
[benchmark.py](https://github.com/SpareCores/resource-tracker/tree/main/examples/benchmark.py)
for a comparison of the two implementations when looking at process-level stats:

```
PSUtil implementation: 0.082130s avg (min: 0.067612s, max: 0.114606s)
ProcFS implementation: 0.084533s avg (min: 0.081533s, max: 0.111782s)
Speedup factor: 0.97x (psutil faster)
```

On a heavy application with many descendants (such as Google Chrome with
hundreds of processes and open tabs):

```
PSUtil implementation: 0.201849s avg (min: 0.193392s, max: 0.214061s)
ProcFS implementation: 0.182557s avg (min: 0.174610s, max: 0.192760s)
Speedup factor: 1.11x (procfs faster)
```

The system-level stats are much cheaper to collect, and there is no effective
difference in performance between the two implementations.

Why have both implementations then? The `psutil` implementation works on all
operating systems at the cost of the extra dependency, while the `procfs`
implementation works without any additional dependencies, but only on Linux.
This latter can be useful when deploying cloud applications in limited
environments without easy control over the dependencies (e.g. Metaflow step
decorator without explicit `@pypi` config).

## References

- PyPI: <https://pypi.org/project/resource-tracker>
- Documentation: <https://sparecores.github.io/resource-tracker>
- Source code: <https://github.com/SpareCores/resource-tracker>
- Project roadmap and feedback form: <https://sparecores.com/feedback/metaflow-resource-tracker>
