# Resource Tracker for R

This R package provides raw access to the 'resource-tracker' Python module via
the 'reticulate' package along with a convenience R6 wrapper for the
`ResourceTracker` class with the most common methods, such as starting and
stopping the tracker, collecting samples, and generating reports.

## Installation

This package requires Python to be installed along with the `resource-tracker`
Python module, which can be installed from R via:

```r
reticulate::py_install('resource-tracker')
```

Once the Python dependencies are resolved, you can either install the R package
from CRAN:

```r
install.packages('resource.tracker')
```

Or the most recent (development version) from GitHub:

```r
remotes::install_github('SpareCores/resource-tracker', subdir = 'R')
```

## Getting started

Load the package and start the resource tracker:

```r
library(resource.tracker)
tracker <- ResourceTracker()
```

This now runs in the background, not blocking your R session.

Let's simulate some work for a few seconds:

```r
start_time <- Sys.time()
while (Sys.time() - start_time < 3) {
  mean(runif(1e6))
}
```

And check the aggregated statistics:

```r
tracker$stats()
```

Or get recommendations on hardware requirements for the next run:

```r
tracker$recommend_resources()
tracker$recommend_server()
```

Or look at the collected samples:

```r
tracker$system_metrics
tracker$process_metrics
tracker$get_combined_metrics()
```

Note that the `system_metrics` and `process_metrics` are propertoies of the
`ResourceTracker` object, while `get_combined_metrics` is a method that returns
a data frame.

And finally, generate a report and open it in your browser:

```r
report <- tracker$report()
report$browse()
```
