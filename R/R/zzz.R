#' Raw access to the resource_tracker Python module.
#'
#' If you don't need advanced features, use \code{\link{ResourceTracker}} instead.
#' @export
resource_tracker <- NULL


#' Track resource usage of processes and the system in a non-blocking way.
#'
#' This is a wrapper around the \code{resource_tracker} Python module's
#' \code{ResourceTracker} class, which is automatically starting background
#' processes to track the resource usage of processes and the system in
#' temporary CSV files, made available for analysis and reporting directly from
#' R.
#'
#' Resource tracker lifecycle methods:
#' - `start`: Start the resource usage trackers. This is automatically called when the `ResourceTracker` object is created with the default `autostart` flag.
#' - `stop`: Stop tracking resource usage.
#' - `wait_for_samples`: Wait for a certain number of samples to be collected.
#'
#' Resource tracker analysis methods:
#' - `get_combined_metrics`: Get the system and process metrics joined by timestamp into a single `data.frame`.
#' - `stats`: Get statistics of the resource usage, including the mean and max of the metrics, and the duration of the tracking.
#' - `recommend_resources`: Recommend resources (vCPUs, memory, GPUs, and VRAM) based on the current state of the resource tracker.
#' - `recommend_server`: Recommend the cheapest cloud server that can run the recommended resources (vCPUs, memory, GPUs, and VRAM) based on the current state of the resource tracker.
#' - `report`: Generate an interactive HTML report of the resource usage and recommendations.
#'
#' Utility methods:
#' - `snapshot`: Serialize the current state of the resource tracker as a list.
#' - `from_snapshot`: Load a snapshot of the resource tracker.
#' - `dumps`: Serialize the resource tracker object to a JSON blob.
#' - `loads`: Load a JSON blob representation of the resource tracker object.
#' - `dump`: Serialize the resource tracker object to a gzipped file.
#' - `load`: Load a gzipped file representation of the resource tracker object.
#'
#' Resource tracker properties:
#' - `n_samples`: Number of samples collected.
#' - `server_info`: Discovered server information, including the operating system, number of vCPUs, memory amount, GPUs and VRAM, and a guess if the server is dedicated to the tracked process(es) or shared with other processes.
#' - `cloud_info`: Discovered cloud information, including the cloud provider, instance type, and the datacenter region.
#' - `process_metrics`: Collected process metrics as a `data.frame`, including timestamp, CPU usage, memory usage, GPU and VRAM utilization, and disk usage.
#' - `system_metrics`: Collected system metrics as a `data.frame`, including timestamp, CPU usage, memory used and available, GPU and VRAM used, disk space, and network receive and send bytes.
#' - `running`: Whether the resource usage trackers are still running.
#' - `wait_for_samples`: Wait for a certain number of samples to be collected.
#'
#' For more details, consult the Python documentation via
#'
#' ```
#' reticulate::py_help(ResourceTracker)
#' ```
#'
#' @param pid The process ID to track. Defaults to current process ID.
#' @param children Whether to track child processes. Defaults to True.
#' @param interval Sampling interval in seconds. Defaults to 1.
#' @param method Multiprocessing method. Defaults to None, which tries to fork on Linux and macOS, and spawn on Windows.
#' @param autostart Whether to start tracking immediately. Defaults to True.
#' @param track_processes Whether to track resource usage at the process level. Defaults to True.
#' @param track_system Whether to track system-wide resource usage. Defaults to True.
#' @param discover_server Whether to discover the server specs in the background at startup. Defaults to True.
#' @param discover_cloud Whether to discover the cloud environment in the background at startup. Defaults to True.
#' @export
#' @usage ResourceTracker(
#'     pid = Sys.getpid(),
#'     children = TRUE,
#'     interval = 1,
#'     method = NULL,
#'     autostart = TRUE,
#'     track_processes = TRUE,
#'     track_system = TRUE,
#'     discover_server = TRUE,
#'     discover_cloud = TRUE
#' )
#' @return A \code{ResourceTracker} Python object.
#' @examples \dontrun{
#' tracker <- ResourceTracker()
#'
#' # simulate some work for a few seconds
#' start_time <- Sys.time()
#' while (Sys.time() - start_time < 3) {
#'   mean(runif(1e6))
#' }
#'
#' tracker$stop()
#' tracker$recommend_resources()
#' tracker$recommend_server()
#'
#' report <- tracker$report()
#' report$browse()
#' }
ResourceTracker <- NULL

.onLoad <- function(libname, pkgname) {
    reticulate::py_require("resource_tracker")
    resource_tracker <<- reticulate::import("resource_tracker", delay_load = TRUE, convert = FALSE)
    ResourceTracker <<- resource_tracker$ResourceTracker
}
