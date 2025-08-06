#' Resource Tracker Object
#'
#' @description
#' And R-friendly wrapper around the Python `resource-tracker` package's
#' `ResourceTracker` class.
#' @export
#' @importFrom R6 R6Class
ResourceTracker <- R6Class("ResourceTracker", # nolint: object_name_linter
  private = list(
    py_obj = NULL
  ),
  active = list(
    #' @field pid The process ID of the tracked process.
    pid = function() {
      private$py_obj$pid
    },
    #' @field system_metrics The system metrics of the tracked process.
    system_metrics = function() {
      metrics <- py_to_r(private$py_obj$system_metrics$to_dict())
      metrics <- as.data.frame(do.call(rbind, metrics))
      metrics
    },
    #' @field process_metrics The process metrics of the tracked process.
    process_metrics = function() {
      private$py_obj$process_metrics
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
