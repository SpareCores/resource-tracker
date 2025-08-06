#' Raw access to the resource_tracker Python module.
#'
#' If you don't need advanced features, use \code{\link{ResourceTracker}} instead.
#' @export
resource_tracker <- NULL

.onLoad <- function(libname, pkgname) {
  reticulate::py_require("resource_tracker")
  resource_tracker <<- reticulate::import("resource_tracker", delay_load = TRUE, convert = FALSE)
}
