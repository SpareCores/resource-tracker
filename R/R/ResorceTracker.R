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
    #' @field process_metrics The process metrics of the tracked process.
    process_metrics = function() {
      ls2df(py_to_r(private$py_obj$process_metrics$to_dict()))
    }
  ),
  public = list(
    #' @description
    #' Initialize the ResourceTracker object in the background.
    #' @param pid The process ID to track. Defaults to current process ID.
    #' @param children Whether to track child processes. Defaults to True.
    #' @param interval Sampling interval in seconds. Defaults to 1.
    #' @param method Multiprocessing method. Defaults to None, which tries to fork on Linux and macOS, and spawn on Windows.
    #' @param autostart Whether to start tracking immediately. Defaults to True.
    #' @param track_processes Whether to track resource usage at the process level. Defaults to True.
    #' @param track_system Whether to track system-wide resource usage. Defaults to True.
    #' @param discover_server Whether to discover the server specs in the background at startup. Defaults to True.
    #' @param discover_cloud Whether to discover the cloud environment in the background at startup. Defaults to True.
    initialize = function(
      pid = Sys.getpid(),
      children = TRUE,
      interval = 1,
      method = NULL,
      autostart = TRUE,
      track_processes = TRUE,
      track_system = TRUE,
      discover_server = TRUE,
      discover_cloud = TRUE) {
      private$py_obj <- resource_tracker$ResourceTracker(
        pid, children, interval, method, autostart,
        track_processes, track_system, discover_server, discover_cloud
      )
    }
  )
)
