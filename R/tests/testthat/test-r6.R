test_that("ResourceTracker passing the process ID correctly", {
  tracker <- ResourceTracker$new()
  expect_equal(tracker$pid, Sys.getpid())
})
