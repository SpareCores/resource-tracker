## devtools::install_github("daroczig/metaflow@R/track_resources", subdir = "R")
library(metaflow)

start <- function(self) {
    print("Starting")
}

do_heavy_computation <- function(self) {
    # reserve 500 MB memory
    big_array <- raw(500 * 1024 * 1024)
    # do some calcss
    total <- sum((0:(1e7 - 1))^3)
    # do nothing for bit after releasing memory
    rm(big_array)
    gc()
    Sys.sleep(1)
}

end <- function(self) {}

metaflow("MinimalFlowR") %>%
    step(step = "start", r_function = start, next_step = "do_heavy_computation") %>%
    step(step = "do_heavy_computation", decorator("track_resources", create_card = FALSE), r_function = do_heavy_computation, next_step = "end") %>%
    step(step = "end", r_function = end) %>%
    run()
