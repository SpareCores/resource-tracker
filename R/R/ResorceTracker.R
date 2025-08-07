#' Convert a list of lists to a data.frame
#' @param l A list of lists.
#' @return A data.frame.
#' @noRd
ls2df <- function(l) {
  # NOTE data.table::rbindlist would be much faster
  df <- do.call(rbind, lapply(l, list2DF))
  if ("timestamp" %in% names(df)) {
    df$timestamp <- as.POSIXct(df$timestamp, origin = "1970-01-01")
  }
  df
}

#' Resource Tracker Object
#'
#' @description
#' And R-friendly wrapper around the Python `resource-tracker` package's
#' `ResourceTracker` class.
#' @export
#' @importFrom R6 R6Class
#' @importFrom reticulate py_to_r
ResourceTracker <- R6Class("ResourceTracker", # nolint: object_name_linter
  private = list(
    py_obj = NULL
  ),
  active = list(
    #' @field pid The process ID of the tracked process.
    pid = function() {
      py_to_r(private$py_obj$pid)
    },
    #' @field n_samples The number of samples taken.
    n_samples = function() {
      py_to_r(private$py_obj$n_samples)
    },
    #' @field system_metrics The system metrics of the tracked process.
    system_metrics = function() {
      ls2df(py_to_r(private$py_obj$system_metrics$to_dict()))
    },
    #' @field process_metrics_df The process metrics of the tracked process.
    process_metrics = function() {
      ls2df(py_to_r(private$py_obj$process_metrics$to_dict()))
    }
  ),
  public = list(
    #' @description
    #' Initialize the ResourceTracker object.
    #' @param pid The process ID to track. Defaults to current process ID.
    initialize = function(pid = Sys.getpid()) {
      private$py_obj <- resource_tracker$ResourceTracker(pid)
    }
  )
)
